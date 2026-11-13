"""API HTTP del copiloto."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from rapidfuzz import fuzz, process

from app import carta as carta_service
from app import db, training
from app.analysis.pipeline import analizar
from app.config import DATA_DIR, get_settings
from app.geo.callejero import display_name, get_callejero
from app.geo.service import validar_valores
from app.knowledge.catalog import DESCRIPCION_PRIORIDAD, get_retriever
from app.knowledge.dataset import get_caso, load_dataset
from app.knowledge.embeddings import get_embedder
from app.providers.factory import get_provider
from app.schemas import (
    CATEGORIAS,
    AnalisisRequest,
    Carta,
    CartaRequest,
    GeoValidacion,
    SimulacroCaso,
    SimulacroRespuesta,
    SimulacroResultado,
)
from app.text import norm
from app.transcript import parse_raw_transcript

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("copiloto")


def _warmup() -> None:
    get_callejero()
    get_retriever()
    from app.analysis.protocol import build_questions  # noqa: F401  (importa y cachea módulos)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    s = get_settings()
    for w in s.warnings:
        log.warning(w)
    await asyncio.to_thread(_warmup)
    log.info("Copiloto listo · proveedor=%s modelo=%s · embeddings=%s", get_provider().name, get_provider().model, get_embedder().name)
    yield


app = FastAPI(title="Copiloto de Sala", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _demo_casos() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "demo_casos.json").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, Any]:
    p = get_provider()
    s = get_settings()
    return {
        "ok": True,
        "proveedor": p.name,
        "modelo": p.model,
        "mock": p.is_mock,
        "embeddings": get_embedder().name,
        "usig_habilitado": s.usig_enabled,
        "avisos": s.warnings,
        "categorias": list(CATEGORIAS),
        "prioridades": DESCRIPCION_PRIORIDAD,
    }


@app.get("/api/casos")
def listar_casos() -> dict[str, Any]:
    dataset = [
        {
            "id": c.id, "titulo": c.subcategoria, "categoria": c.categoria, "prioridad": c.prioridad,
            "origen": c.origen, "timestamp": c.timestamp, "fuente": "dataset",
        }
        for c in load_dataset()
    ]
    demos = [
        {"id": d["id"], "titulo": d["titulo"], "origen": d["origen"], "timestamp": d["timestamp"], "fuente": "demo"}
        for d in _demo_casos()
    ]
    return {"demo": demos, "dataset": dataset}


@app.get("/api/casos/{caso_id}")
def obtener_caso(caso_id: str) -> dict[str, Any]:
    if (c := get_caso(caso_id)) is not None:
        turnos = [t.model_dump() for t in parse_raw_transcript(c.transcripcion)]
        return {"id": c.id, "titulo": c.subcategoria, "timestamp": c.timestamp, "origen": c.origen, "turnos": turnos}
    for d in _demo_casos():
        if d["id"] == caso_id:
            return d
    raise HTTPException(404, f"Caso {caso_id} inexistente")


@app.post("/api/parsear")
def parsear(body: dict[str, str]) -> dict[str, Any]:
    """Convierte texto pegado (desgrabación) en turnos."""
    return {"turnos": [t.model_dump() for t in parse_raw_transcript(body.get("texto", ""))]}


@app.post("/api/analizar")
async def analizar_endpoint(req: AnalisisRequest) -> StreamingResponse:
    if not req.turnos and not (req.texto and req.texto.strip()):
        raise HTTPException(422, "Se requiere 'turnos' o 'texto'")

    async def stream() -> AsyncIterator[bytes]:
        try:
            async for analisis in analizar(req):
                yield (analisis.model_dump_json() + "\n").encode()
        except Exception as exc:  # noqa: BLE001 - el stream nunca debe cortar sin aviso
            log.exception("Error en análisis")
            yield (json.dumps({"error": str(exc)}) + "\n").encode()

    return StreamingResponse(stream(), media_type="application/x-ndjson", headers={"X-Accel-Buffering": "no"})


@app.get("/api/calles")
def autocompletar_calles(q: str = Query(min_length=2, max_length=60)) -> list[str]:
    cal = get_callejero()
    hits = process.extract(norm(q), cal.aliases, scorer=fuzz.WRatio, limit=12)
    out: list[str] = []
    for alias, _score, _ in hits:
        name = display_name(cal.alias_index[alias][0])
        if name not in out:
            out.append(name)
    return out[:8]


class DireccionManual(BaseModel):
    calle: str | None = None
    altura: str | None = None
    interseccion: str | None = None
    entre_calles: str | None = None


@app.post("/api/geo/validar", response_model=GeoValidacion)
async def validar_direccion(d: DireccionManual) -> GeoValidacion:
    """Revalidación de una dirección corregida por el operador."""
    return await validar_valores(d.calle, d.altura, d.interseccion, d.entre_calles)


@app.post("/api/cartas", response_model=Carta)
def derivar_carta(req: CartaRequest) -> Carta:
    return carta_service.derivar(req)


@app.get("/api/cartas")
def listar_cartas() -> list[dict[str, Any]]:
    return db.list_cartas()


@app.get("/api/correcciones")
def correcciones() -> list[dict[str, Any]]:
    return db.correcciones_stats()


@app.get("/api/simulacro/caso", response_model=SimulacroCaso)
def simulacro_caso(dificultad: str = "normal", excluir: str = "") -> SimulacroCaso:
    if dificultad not in {"normal", "ruidosa"}:
        raise HTTPException(422, "dificultad debe ser 'normal' o 'ruidosa'")
    return training.nuevo_caso(dificultad, [x for x in excluir.split(",") if x])


@app.post("/api/simulacro/evaluar", response_model=SimulacroResultado)
def simulacro_evaluar(r: SimulacroRespuesta) -> SimulacroResultado:
    try:
        return training.evaluar(r)
    except KeyError as exc:
        raise HTTPException(404, f"Caso {exc} inexistente") from exc


@app.get("/api/simulacro/stats")
def simulacro_stats() -> dict[str, Any]:
    return db.simulacro_stats()
