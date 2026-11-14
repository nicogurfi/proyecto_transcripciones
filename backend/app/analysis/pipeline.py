"""Orquestación en dos fases:

1. RÁPIDA (<100 ms): reglas + callejero offline + catálogo. Se emite enseguida.
2. FINAL: proveedor (LLM real o mock) con validación/verificación + fusión
   con las reglas + doble chequeo USIG online. Si el LLM falla o tarda más
   que LLM_TIMEOUT_SECONDS, se mantiene el resultado de reglas.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import time
from collections.abc import AsyncIterator

from pydantic import ValidationError

from app.analysis import dispatch, inconsistencies, protocol, safety
from app.config import get_settings
from app.extraction import llm as llm_ext
from app.extraction.draft import FIELD_KEYS, Draft, Hallazgo
from app.extraction.rules import run_rules
from app.geo.service import validar
from app.providers.base import ExtractionRequest, LLMError
from app.providers.factory import get_provider
from app.schemas import (
    Analisis,
    AnalisisRequest,
    Campo,
    CasoSimilar,
    ChecklistItem,
    Evidence,
    Ficha,
    GeoValidacion,
    Nivel,
)
from app.text import norm
from app.transcript import Document, parse_raw_transcript

log = logging.getLogger(__name__)


def nivel(conf: float) -> Nivel:
    return "alta" if conf >= 0.8 else ("media" if conf >= 0.55 else "baja")


def _same(a: str, b: str) -> bool:
    from rapidfuzz import fuzz

    na, nb = norm(a), norm(b)
    return na == nb or fuzz.token_set_ratio(na, nb) >= 85


_SEVERIDAD = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


def merge(rules: Draft, llm_campos: dict[str, Hallazgo], notas: list[str]) -> Draft:
    """Fusión campo a campo. Coincidencia => sube la confianza; discrepancia
    => se elige con criterio de seguridad y se deja la alternativa visible."""
    merged = copy.copy(rules)
    merged.campos = dict(rules.campos)
    for key in FIELD_KEYS:
        r, m = rules.campos.get(key), llm_campos.get(key)
        if m is None:
            continue
        if r is None:
            merged.campos[key] = m
            continue
        if r.method.startswith("orientativa"):
            # subtipo de parecido bajo: que el LLM lo repita no lo vuelve confiable
            merged.campos[key] = m if m.confidence > r.confidence and not _same(r.value, m.value) else r
            continue
        if _same(r.value, m.value):
            r2 = copy.copy(r)
            r2.confidence = min(0.97, max(r.confidence, m.confidence) + 0.1)
            r2.method = f"{r.method} + LLM coinciden"
            merged.campos[key] = r2
            continue
        if key == "prioridad":
            grave, otra = (m, r) if _SEVERIDAD[m.value] <= _SEVERIDAD[r.value] else (r, m)
            merged.campos[key] = Hallazgo(
                grave.value, grave.spans or otra.spans, f"discrepancia reglas/LLM: se toma la más grave ({grave.method})",
                0.6, source="inferido", alternatives=[otra.value],
            )
            notas.append(f"Prioridad: reglas={r.value}, LLM={m.value}. Se propone la más grave.")
        elif key == "ubicacion.calle" and r.method.endswith("(exacto)"):
            # El callejero exacto es más confiable que el LLM para el nombre;
            # el LLM suele acertar mejor cuál es la calle principal.
            merged.campos[key] = Hallazgo(m.value, m.spans, "LLM (calle principal) + callejero", 0.7, alternatives=[r.value])
        else:
            merged.campos[key] = Hallazgo(m.value, m.spans or r.spans, m.method, min(m.confidence, 0.7), m.source, alternatives=[r.value])
    return merged


def _ajustar_confianza(draft: Draft, geo: GeoValidacion) -> None:
    c = draft.campos
    if geo.estado == "validada":
        for k in ("ubicacion.calle", "ubicacion.altura", "ubicacion.interseccion", "ubicacion.entre_calles"):
            if k in c:
                c[k].confidence = min(0.97, c[k].confidence + 0.07)
    if geo.altura_en_rango is False and "ubicacion.altura" in c:
        c["ubicacion.altura"].confidence = min(c["ubicacion.altura"].confidence, 0.3)
    if geo.cruce_valido is False:
        for k in ("ubicacion.interseccion", "ubicacion.entre_calles"):
            if k in c:
                c[k].confidence = min(c[k].confidence, 0.3)
    for _, s, e in draft.dudas:
        for h in c.values():
            if any(a <= s < b or s <= a < e for a, b in h.spans):
                h.confidence = max(0.2, h.confidence - 0.15)


def to_ficha(doc: Document, draft: Draft, geo: GeoValidacion) -> Ficha:
    ficha = Ficha()
    for key in FIELD_KEYS:
        h = draft.campos.get(key)
        if h is None:
            continue
        campo = Campo(
            value=h.value,
            confidence=round(h.confidence, 2),
            level=nivel(h.confidence),
            source=h.source,
            method=h.method,
            evidence=[doc.evidence(s, e) for s, e in h.spans],
            alternatives=h.alternatives,
        )
        _set(ficha, key, campo)
    if ficha.ubicacion.barrio.value is None and geo.barrio:
        ficha.ubicacion.barrio = Campo(
            value=f"{geo.barrio.title()}" + (f" ({geo.comuna})" if geo.comuna else ""),
            confidence=0.9, level="alta", source="inferido", method="USIG (datos útiles)",
        )
    return ficha


def _set(ficha: Ficha, key: str, campo: Campo) -> None:
    if "." in key:
        section, attr = key.split(".", 1)
        setattr(getattr(ficha, section), attr, campo)
    else:
        setattr(ficha, key, campo)


def _similares(draft: Draft) -> list[CasoSimilar]:
    return [
        CasoSimilar(
            id=s.caso.id, categoria=s.caso.categoria, subcategoria=s.caso.subcategoria, prioridad=s.caso.prioridad,
            similitud=round(s.similitud, 2), nota_despacho=s.caso.notas, recursos=s.caso.recursos,
        )
        for s in draft.similares[:3]
    ]


def build(
    fase: str, t0: float, doc: Document, draft: Draft, geo: GeoValidacion, req: AnalisisRequest,
    notas: list[str], llm_answers: dict[str, Evidence] | None = None,
    llm_incs: list[tuple[str, Evidence | None]] | None = None,
) -> Analisis:
    provider = get_provider()
    _ajustar_confianza(draft, geo)
    alertas = safety.alertas_criticas(doc)
    instr = safety.instrucciones(draft, alertas)
    checklist: list[ChecklistItem] = protocol.build_checklist(doc, draft)
    for item in checklist:
        if llm_answers and item.id in llm_answers and item.estado == "pendiente":
            item.estado, item.confianza, item.evidencia = "respondida_sugerida", 0.7, llm_answers[item.id]
    pasos, sugerido = protocol.build_pasos(draft, geo, checklist, len(instr))
    # El subtipo "orientativo" (parecido bajo) no va a la nota: sería afirmar algo no sustentado.
    valores = {k: h.value for k, h in draft.campos.items() if not h.method.startswith("orientativa")}
    if geo.barrio and not valores.get("ubicacion.barrio"):
        valores["ubicacion.barrio"] = geo.barrio.title()
    alertas_txt = [x.texto for x in alertas]
    return Analisis(
        fase=fase,  # type: ignore[arg-type]
        proveedor=provider.name,
        modelo=provider.model,
        latencia_ms=int((time.perf_counter() - t0) * 1000),
        turnos=doc.turns,
        ficha=to_ficha(doc, draft, geo),
        geo=geo,
        pasos=pasos,
        paso_sugerido=sugerido,
        checklist=checklist,
        instrucciones=instr,
        alertas_criticas=alertas,
        casos_similares=_similares(draft),
        inconsistencias=inconsistencies.detectar(doc, draft, geo, req.timestamp, llm_incs),
        recursos_sugeridos=dispatch.recursos_sugeridos(valores, draft.similares, geo, doc.caller_text),
        nota_operativa=dispatch.nota_operativa(valores, geo, alertas_txt),
        notas=notas,
    )


async def _llm_phase(doc: Document, draft: Draft, notas: list[str]) -> tuple[Draft, dict[str, Evidence], list[tuple[str, Evidence | None]]]:
    provider = get_provider()
    checklist = protocol.build_checklist(doc, draft)
    req = ExtractionRequest(
        system=llm_ext.SYSTEM_PROMPT,
        user=llm_ext.build_user_prompt(doc, draft, checklist),
        mock_response=llm_ext.draft_to_llm_json(draft, doc),
    )
    ext = None
    for attempt in range(2):
        raw = await provider.complete_json(req)
        try:
            ext = llm_ext.validate_extraction(raw)
            break
        except (ValueError, ValidationError) as exc:
            msg = str(exc)[:400]
            notas.append(f"Respuesta malformada del modelo (intento {attempt + 1}): {msg[:120]}")
            req = ExtractionRequest(req.system, req.user, req.mock_response, retry_error=msg)
    if ext is None:
        notas.append("Se descartó la salida del modelo: se usan las reglas.")
        return draft, {}, []
    llm_campos = llm_ext.to_campos(ext, doc, notas)
    if provider.is_mock:
        # El mock repite las reglas: "coincidir" con ellas no es evidencia independiente,
        # así que no se fusiona (no se infla la confianza). El parseo/validación sí se ejercitó.
        return draft, {}, []
    merged = merge(draft, llm_campos, notas)
    if "ubicacion.calle" in llm_campos:
        llm_ext.address_from_llm(merged, merged.campos)
    answers = llm_ext.verified_respuestas(ext, doc, {q.id for q in checklist})
    incs = llm_ext.verified_inconsistencias(ext, doc)
    return merged, answers, incs


async def analizar(req: AnalisisRequest) -> AsyncIterator[Analisis]:
    t0 = time.perf_counter()
    turns = req.turnos if req.turnos else parse_raw_transcript(req.texto or "")
    doc = Document.from_turns(turns)
    notas: list[str] = []
    draft = await asyncio.to_thread(run_rules, doc, req.caso_ref)
    geo = await validar(draft, online=False)
    yield build("rapida", t0, doc, copy.deepcopy(draft), geo, req, list(notas))

    provider = get_provider()
    llm_answers: dict[str, Evidence] = {}
    llm_incs: list[tuple[str, Evidence | None]] = []
    if req.usar_llm and doc.turns:
        try:
            draft, llm_answers, llm_incs = await asyncio.wait_for(
                _llm_phase(doc, draft, notas), timeout=get_settings().llm_timeout_s + 2
            )
        except (TimeoutError, asyncio.TimeoutError):
            notas.append(f"El modelo ({provider.name}) superó el tiempo máximo: se mantienen las reglas.")
        except LLMError as exc:
            notas.append(f"Proveedor LLM no disponible ({exc}): se mantienen las reglas.")
    geo = await validar(draft, online=True)
    yield build("final", t0, doc, draft, geo, req, notas, llm_answers, llm_incs)
