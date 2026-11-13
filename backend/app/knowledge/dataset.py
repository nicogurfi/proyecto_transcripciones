"""Carga del dataset provisto como catálogo de referencia."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from app.config import DATA_DIR


@dataclass(frozen=True, slots=True)
class CasoReferencia:
    id: str
    timestamp: str
    origen: str
    categoria: str
    subcategoria: str
    prioridad: str
    transcripcion: str
    calle: str
    altura: str
    interseccion: str
    barrio: str
    preguntas_mandatorias: tuple[str, ...]
    preguntas_respondidas: tuple[str, ...]
    preguntas_pendientes: tuple[str, ...]
    instrucciones: str
    riesgos: str
    recursos: str
    notas: str

    @property
    def caller_text(self) -> str:
        """Solo lo dicho por el llamante (lo que se indexa semánticamente)."""
        parts = re.split(r"Llamante\s*:", self.transcripcion, maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else self.transcripcion


def _split_questions(raw: str) -> tuple[str, ...]:
    return tuple(q.strip() for q in raw.split("|") if q.strip())


def strip_answer(question: str) -> str:
    """'¿Hay atrapados? (Sí, el cocinero)' -> '¿Hay atrapados?'"""
    return re.sub(r"\s*\([^)]*\)\s*$", "", question).strip()


@lru_cache(maxsize=1)
def load_dataset() -> tuple[CasoReferencia, ...]:
    path = DATA_DIR / "dataset_challenge_soflex.csv"
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    casos = [
        CasoReferencia(
            id=r["id_registro"],
            timestamp=r["timestamp_llamada"],
            origen=r["origen_reporte"],
            categoria=r["categoria"],
            subcategoria=r["subcategoria"],
            prioridad=r["prioridad_sugerida"],
            transcripcion=r["transcripcion_cruda"],
            calle=r["calle_detectada"],
            altura=r["altura_detectada"],
            interseccion=r["interseccion_detectada"],
            barrio=r["barrio_comuna"],
            preguntas_mandatorias=_split_questions(r["preguntas_protocolo_mandatorias"]),
            preguntas_respondidas=_split_questions(r["preguntas_respondidas_en_relato"]),
            preguntas_pendientes=_split_questions(r["preguntas_pendientes"]),
            instrucciones=r["instrucciones_prearribo"],
            riesgos=r["riesgos_detectados"],
            recursos=r["recursos_recomendados_despacho"],
            notas=r["notas_operativas_despacho"],
        )
        for r in rows
    ]
    return tuple(casos)


def get_caso(caso_id: str) -> CasoReferencia | None:
    return next((c for c in load_dataset() if c.id == caso_id), None)
