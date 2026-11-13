"""Protocolo por pasos y checklist dinámico (qué ya se respondió en el
relato y qué falta preguntar)."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import numpy as np
from rapidfuzz import fuzz

from app.extraction.draft import Draft
from app.knowledge.catalog import BASE_PREGUNTAS, PREGUNTAS_CATEGORIA, SUBCATEGORIA_UMBRAL, embed_questions
from app.knowledge.dataset import strip_answer
from app.knowledge.embeddings import get_embedder
from app.schemas import ChecklistItem, GeoValidacion, PasoProtocolo
from app.text import content_stems, split_sentences
from app.transcript import Document

SINONIMOS: dict[str, tuple[str, ...]] = {
    "ATRAP": ("ADENT", "QUEDO", "ENCER", "TRABO", "DEBAJ", "TRANC"),
    "RESPI": ("AIRE", "RESPI"),
    "CONSC": ("CONCI", "RESPO", "CONSC"),
    "HERID": ("LESIO", "GOLPE", "SANGR", "DUELE", "DOLOR", "FRACT", "RASPO", "HERID"),
    "VEHIC": ("AUTO", "AUTOS", "CAMIO", "COLEC", "TAXI", "MOTO", "RODAD", "CAMIO", "UTILI"),
    "QUEMA": ("FUEGO", "LLAMA", "INCEN", "PREND", "QUEMA"),
    "EDAD": ("ANOS",),
    "ARMAS": ("ARMA", "CUCHI", "PISTO", "BOTEL", "SILLA"),
    "INVOL": ("GRUPO", "JOVEN", "PERSO"),
    "COMBU": ("GASOI", "NAFTA", "DERRA", "PERDI"),
    "CABLE": ("CABLE", "TENDI", "CHISP"),
}
_TEL_RE = re.compile(r"\b(?:\+?54\s?9?\s?)?(?:11|15)[\s-]?\d{4}[\s-]?\d{4}\b|\b4\d{3}[\s-]?\d{4}\b")
_GENERIC_STEMS = {"HAY", "PERSO", "ALGUN", "PUEDE", "ESTA", "TIENE", "ALGUI", "OBSER", "PRESE", "SECTO", "LUGAR"}


def _qid(text: str) -> str:
    return "q_" + hashlib.md5(text.lower().encode()).hexdigest()[:8]


def _dedupe(items: list[tuple[str, str, bool]]) -> list[tuple[str, str, bool]]:
    out: list[tuple[str, str, bool]] = []
    for q, origen, crit in items:
        if any(fuzz.token_set_ratio(q.lower(), o[0].lower()) >= 78 for o in out):
            continue
        out.append((q, origen, crit))
    if len(out) > 1:
        vecs = embed_questions([o[0] for o in out])
        keep: list[int] = []
        for i in range(len(out)):
            if all(float(vecs[i] @ vecs[j]) < 0.86 for j in keep):
                keep.append(i)
        out = [out[i] for i in keep]
    return out


def build_questions(draft: Draft) -> list[tuple[str, str, bool]]:
    items: list[tuple[str, str, bool]] = [(q, "base", c) for q, c in BASE_PREGUNTAS]
    cat = draft.campos.get("suceso.categoria")
    if cat:
        items += [(q, "categoria", c) for q, c in PREGUNTAS_CATEGORIA.get(cat.value, ())]
        same = [s for s in draft.similares if s.caso.categoria == cat.value and s.similitud >= SUBCATEGORIA_UMBRAL]
        if same:
            caso = same[0].caso
            for q in caso.preguntas_mandatorias:
                items.append((strip_answer(q), "subcategoria", True))
            for q in caso.preguntas_pendientes:
                items.append((strip_answer(q), "subcategoria", False))
    return _dedupe(items)


def _expand(stems: list[str]) -> set[str]:
    out = set(stems)
    for s in stems:
        for key, syns in SINONIMOS.items():
            if s.startswith(key[:4]) or s in syns:
                out.update(syns)
                out.add(key)
    return out - _GENERIC_STEMS


def _special(question: str, draft: Draft, doc: Document) -> tuple[int, int] | None:
    """Respuestas que ya están estructuradas en la ficha (se cita el fragmento puntual)."""
    q = question.lower()
    c = draft.campos

    def span_of(key: str, pattern: str | None = None) -> tuple[int, int] | None:
        h = c.get(key)
        if h is None or not h.spans:
            return None
        if pattern is None:
            return h.spans[0]
        return next((s for s in h.spans if re.search(pattern, doc.text[s[0] : s[1]], re.I)), None)

    if "herid" in q:
        return span_of("personas.estado") or span_of("personas.victimas")
    if "atrapad" in q:
        return span_of("personas.atrapados")
    if "edad" in q:
        return span_of("personas.victimas", r"años")
    if "consciente" in q or "responde" in q:
        return span_of("personas.estado", r"conscien|concien|no responde|contesta|inconsciente")
    if "respira" in q:
        return span_of("personas.estado", r"respira|aire|roncando")
    return None


def build_checklist(doc: Document, draft: Draft) -> list[ChecklistItem]:
    questions = build_questions(draft)
    sentences: list[tuple[str, int, int]] = []
    for i, t in enumerate(doc.turns):
        if t.speaker == "llamante":
            sentences += split_sentences(t.text, doc.bases[i])
    sent_stems = [set(content_stems(s[0])) for s in sentences]
    df = Counter(st for q, _, _ in questions for st in set(_expand(content_stems(q))))
    n_q = max(len(questions), 1)
    embedder = get_embedder()
    sent_vecs = embedder.embed([s[0] for s in sentences]) if sentences else np.zeros((0, 1))
    q_vecs = embed_questions([q for q, _, _ in questions])

    items: list[ChecklistItem] = []
    for qi, (q, origen, critica) in enumerate(questions):
        item = ChecklistItem(id=_qid(q), pregunta=q, origen=origen, critica=critica)  # type: ignore[arg-type]
        span: tuple[int, int] | None = None
        conf = 0.0
        if "teléfono" in q.lower():
            for ti, t in enumerate(doc.turns):
                if t.speaker == "llamante" and (m := _TEL_RE.search(t.text)):
                    span, conf = (doc.bases[ti] + m.start(), doc.bases[ti] + m.end()), 0.9
                    break
        elif (sp := _special(q, draft, doc)) is not None:
            span, conf = sp, 0.8
        elif sentences:
            q_stems = _expand(content_stems(q))
            weights = {s: math.log(1 + n_q / df.get(s, 1)) for s in q_stems}
            total_w = sum(weights.values()) or 1.0
            best_lex, best_idx = 0.0, -1
            for si, st in enumerate(sent_stems):
                score = sum(w for s, w in weights.items() if s in st) / total_w
                if score > best_lex:
                    best_lex, best_idx = score, si
            sims = sent_vecs @ q_vecs[qi] if len(sentences) else np.zeros(0)
            best_sem_idx = int(np.argmax(sims)) if len(sims) else -1
            best_sem = float(sims[best_sem_idx]) if best_sem_idx >= 0 else 0.0
            if best_lex >= 0.45:
                span, conf = sentences[best_idx][1:], min(0.85, 0.4 + best_lex * 0.5)
            elif best_sem >= embedder.semantic_threshold + 0.1:
                span, conf = sentences[best_sem_idx][1:], min(0.75, best_sem)
        if span is not None:
            item.estado = "respondida_sugerida"
            item.confianza = round(conf, 2)
            item.evidencia = doc.evidence(*span)
        items.append(item)
    return items


def build_pasos(
    draft: Draft, geo: GeoValidacion, checklist: list[ChecklistItem], n_instrucciones: int
) -> tuple[list[PasoProtocolo], int]:
    c = draft.campos

    def has(k: str) -> bool:
        return k in c and bool(c[k].value)

    pasos: list[PasoProtocolo] = []
    # 1. Ubicación
    falt = []
    if not has("ubicacion.calle"):
        falt.append("Calle")
    if not (has("ubicacion.altura") or has("ubicacion.interseccion") or has("ubicacion.entre_calles")):
        falt.append("Altura o esquina")
    if has("ubicacion.calle") and geo.estado not in {"validada"}:
        falt.append("Dirección no validada en callejero")
    estado = "completo" if not falt else ("parcial" if has("ubicacion.calle") else "pendiente")
    pasos.append(PasoProtocolo(numero=1, nombre="Ubicación", objetivo="¿Dónde es la emergencia? Calle, altura y entre calles.", estado=estado, faltantes=falt))
    # 2. Qué pasó
    falt = [n for k, n in (("suceso.categoria", "Tipo de hecho"), ("suceso.descripcion", "Descripción"), ("prioridad", "Prioridad")) if not has(k)]
    pasos.append(PasoProtocolo(numero=2, nombre="Qué pasó", objetivo="Naturaleza del hecho y prioridad sugerida.", estado="completo" if not falt else ("parcial" if len(falt) < 3 else "pendiente"), faltantes=falt))
    # 3. Personas y riesgos
    falt = []
    if not (has("personas.cantidad") or has("personas.victimas")):
        falt.append("Personas involucradas")
    if not has("personas.estado"):
        falt.append("Estado de las personas")
    opcional = [] if has("riesgos") else ["Riesgos en el lugar (si los hay)"]
    pasos.append(PasoProtocolo(numero=3, nombre="Personas y riesgos", objetivo="Quiénes están afectados, cómo están y qué riesgos hay.", estado="completo" if not falt else ("parcial" if len(falt) < 2 else "pendiente"), faltantes=falt + opcional))
    # 4. Interrogatorio
    crit = [i for i in checklist if i.critica]
    pend = [i for i in crit if i.estado == "pendiente"]
    estado = "completo" if crit and not pend else ("parcial" if len(pend) < len(crit) else "pendiente")
    pasos.append(PasoProtocolo(numero=4, nombre="Interrogatorio", objetivo="Preguntas clave del protocolo según el tipo de hecho.", estado=estado, faltantes=[i.pregunta for i in pend[:4]]))
    # 5. Pre-arribo
    pasos.append(PasoProtocolo(numero=5, nombre="Pre-arribo", objetivo="Leer al llamante las instrucciones de seguridad.", estado="pendiente", faltantes=[f"{n_instrucciones} instrucciones disponibles (F2)"] if n_instrucciones else []))
    # 6. Carta
    pasos.append(PasoProtocolo(numero=6, nombre="Carta de llamada", objetivo="Validar la ficha y derivar a despacho.", estado="pendiente", faltantes=[]))
    sugerido = next((p.numero for p in pasos if p.estado != "completo"), 6)
    return pasos, sugerido

