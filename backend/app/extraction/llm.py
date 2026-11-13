"""Extracción con LLM: prompt, parseo resiliente, validación con Pydantic
y verificación de evidencia contra la transcripción (anti-alucinación).

Reglas de control:
1. Cada dato "dicho" debe venir con una cita textual que exista en la
   transcripción (coincidencia aproximada >= 85). Si no, se descarta.
2. Calles y alturas además deben aparecer en el texto: el modelo no puede
   "completar" una esquina que el llamante no dijo.
3. JSON malformado -> 1 reintento con el error de validación -> fallback a reglas.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from rapidfuzz import fuzz

from app.extraction.draft import Draft, Hallazgo
from app.geo.callejero import display_name, get_callejero
from app.knowledge.catalog import DESCRIPCION_PRIORIDAD
from app.schemas import CATEGORIAS, ChecklistItem, Evidence
from app.text import norm
from app.transcript import Document

# ---------------------------------------------------------------- esquema de salida del LLM


class _Lenient(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Dato(_Lenient):
    valor: str | None = None
    evidencia: str | None = None

    @field_validator("valor", mode="before")
    @classmethod
    def _coerce(cls, v: Any) -> str | None:
        if v is None or (isinstance(v, str) and v.strip().lower() in {"", "null", "none", "desconocido", "n/a"}):
            return None
        if isinstance(v, list):
            return "; ".join(str(x) for x in v) or None
        return str(v).strip()


class UbicacionLLM(_Lenient):
    calle: Dato = Field(default_factory=Dato)
    altura: Dato = Field(default_factory=Dato)
    interseccion: Dato = Field(default_factory=Dato)
    entre_calles: Dato = Field(default_factory=Dato)
    piso_depto: Dato = Field(default_factory=Dato)
    referencia: Dato = Field(default_factory=Dato)
    barrio: Dato = Field(default_factory=Dato)


class SucesoLLM(_Lenient):
    categoria: str | None = None
    subcategoria: str | None = None
    descripcion: Dato = Field(default_factory=Dato)

    @field_validator("categoria", mode="before")
    @classmethod
    def _cat(cls, v: Any) -> str | None:
        if not v:
            return None
        v = str(v).strip().upper().replace(" ", "_")
        return v if v in CATEGORIAS else None  # categoría inventada => se ignora


class PrioridadLLM(_Lenient):
    valor: str | None = None
    justificacion: str | None = None

    @field_validator("valor", mode="before")
    @classmethod
    def _p(cls, v: Any) -> str | None:
        m = re.search(r"P?\s*([1-4])", str(v or "").upper())
        return f"P{m.group(1)}" if m else None


class PersonasLLM(_Lenient):
    cantidad: Dato = Field(default_factory=Dato)
    victimas: Dato = Field(default_factory=Dato)
    estado: Dato = Field(default_factory=Dato)
    atrapados: Dato = Field(default_factory=Dato)


class LlamanteLLM(_Lenient):
    rol: Dato = Field(default_factory=Dato)


class HallazgoLLM(_Lenient):
    descripcion: str
    evidencia: str | None = None


class RespuestaLLM(_Lenient):
    id: str
    evidencia: str | None = None


class LLMExtraction(_Lenient):
    ubicacion: UbicacionLLM = Field(default_factory=UbicacionLLM)
    suceso: SucesoLLM = Field(default_factory=SucesoLLM)
    prioridad: PrioridadLLM = Field(default_factory=PrioridadLLM)
    personas: PersonasLLM = Field(default_factory=PersonasLLM)
    llamante: LlamanteLLM = Field(default_factory=LlamanteLLM)
    riesgos: list[Dato] = Field(default_factory=list)
    posibles_inconsistencias: list[HallazgoLLM] = Field(default_factory=list)
    preguntas_respondidas: list[RespuestaLLM] = Field(default_factory=list)

    @field_validator("riesgos", mode="before")
    @classmethod
    def _riesgos(cls, v: Any) -> list[Any]:
        if isinstance(v, str):
            return [{"valor": v}]
        if isinstance(v, list):
            return [x if isinstance(x, dict) else {"valor": x} for x in v]
        return []


# ---------------------------------------------------------------- prompts

SYSTEM_PROMPT = f"""Sos un copiloto para operadores de un centro de atención de emergencias (911/103/107/147) de la Ciudad de Buenos Aires.
Tu tarea es EXTRAER datos de la transcripción de una llamada. No decidís despacho: solo estructurás lo que dijo el llamante.

Reglas estrictas:
- Usá SOLO información dicha explícitamente en la transcripción. Si un dato no fue dicho, devolvé null. Nunca completes esquinas, alturas ni barrios que no se mencionaron.
- Para cada dato con "evidencia", copiá TEXTUALMENTE el fragmento de la transcripción que lo respalda (máx. 15 palabras).
- Interpretá modismos rioplatenses: "al 800" = altura 800; "casi X" = cerca de la esquina con X; "entre X y Z" = entre calles.
- Calles: nombre tal como existe en CABA (ej. "Av. Corrientes"). La intersección va en "interseccion" (solo si se dijo "X y Z" o "casi Z"), las calles laterales en "entre_calles".
- categoria: una de {", ".join(CATEGORIAS)}.
- prioridad: {"; ".join(f"{k} = {v}" for k, v in DESCRIPCION_PRIORIDAD.items())}. Ante la duda entre dos, elegí la más grave y justificá.
- posibles_inconsistencias: datos que podrían estar mal transcriptos o ser contradictorios (con evidencia).
- preguntas_respondidas: ids de las preguntas del checklist que YA tienen respuesta en el relato, con la evidencia.
Respondé ÚNICAMENTE con un objeto JSON válido, sin texto adicional."""

_SCHEMA_HINT = """{
  "ubicacion": {"calle": {"valor": str|null, "evidencia": str|null}, "altura": {...}, "interseccion": {...}, "entre_calles": {...}, "piso_depto": {...}, "referencia": {...}, "barrio": {...}},
  "suceso": {"categoria": str|null, "subcategoria": str|null, "descripcion": {"valor": str|null, "evidencia": str|null}},
  "prioridad": {"valor": "P1"|"P2"|"P3"|"P4", "justificacion": str},
  "personas": {"cantidad": {...}, "victimas": {...}, "estado": {...}, "atrapados": {...}},
  "llamante": {"rol": {...}},
  "riesgos": [{"valor": str, "evidencia": str}],
  "posibles_inconsistencias": [{"descripcion": str, "evidencia": str}],
  "preguntas_respondidas": [{"id": str, "evidencia": str}]
}"""


def build_user_prompt(doc: Document, draft: Draft, checklist: list[ChecklistItem]) -> str:
    turns = "\n".join(f"[{i}] {t.speaker.upper()}: {t.text}" for i, t in enumerate(doc.turns))
    # Few-shot SOLO de clasificación: los campos del dataset incluyen datos inferidos
    # (esquinas no dichas), usarlos como ejemplo de extracción enseñaría a alucinar.
    refs = "\n".join(
        f"- \"{s.caso.caller_text[:220]}\" => {s.caso.categoria} / {s.caso.subcategoria} / {s.caso.prioridad}"
        for s in draft.similares[:3]
    )
    preguntas = "\n".join(f"- {q.id}: {q.pregunta}" for q in checklist)
    return (
        f"TRANSCRIPCIÓN:\n{turns}\n\n"
        f"CASOS DE REFERENCIA (solo para orientar la clasificación):\n{refs or '- (sin casos)'}\n\n"
        f"CHECKLIST DE PREGUNTAS:\n{preguntas or '- (vacío)'}\n\n"
        f"ESQUEMA DE SALIDA:\n{_SCHEMA_HINT}"
    )


# ---------------------------------------------------------------- parseo resiliente


def parse_llm_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("la respuesta no contiene un objeto JSON")
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r",\s*([}\]])", r"\1", candidate)  # comas colgantes
        repaired = re.sub(r"(?<=[{,\s])'([^']+)'\s*:", r'"\1":', repaired)  # claves con comillas simples
        data = json.loads(repaired)
    if not isinstance(data, dict):
        raise ValueError("el JSON raíz no es un objeto")
    return data


def validate_extraction(raw: str) -> LLMExtraction:
    """Lanza ValueError/ValidationError con un mensaje usable para el reintento."""
    return LLMExtraction.model_validate(parse_llm_json(raw))


# ---------------------------------------------------------------- verificación de evidencia


def locate(doc: Document, quote: str | None) -> tuple[int, int] | None:
    if not quote or len(quote.strip()) < 2:
        return None
    q = quote.strip().strip('"“”')
    pos = doc.text.lower().find(q.lower())
    if pos >= 0:
        return pos, pos + len(q)
    al = fuzz.partial_ratio_alignment(q.lower(), doc.text.lower(), score_cutoff=85)
    if al is None:
        return None
    return al.dest_start, al.dest_end


def _in_text(doc: Document, value: str) -> bool:
    v = norm(re.sub(r"^(av\.?|avenida)\s+", "", value, flags=re.I))
    if not v:
        return False
    t = norm(doc.text)
    return v in t or fuzz.partial_ratio(v, t) >= 85


def _mentioned_cods(doc: Document) -> set[int]:
    return {t.cod for m in get_callejero().find_mentions(doc.text) for t in m.tramos}


def _street_said(doc: Document, part: str, cods: set[int]) -> bool:
    """La calle propuesta fue dicha (literal, o con error de transcripción que el callejero resuelve)."""
    if _in_text(doc, part):
        return True
    found = get_callejero().lookup(part)
    return bool(found and {t.cod for t in found[1]} & cods)


def to_campos(ext: LLMExtraction, doc: Document, notas: list[str]) -> dict[str, Hallazgo]:
    campos: dict[str, Hallazgo] = {}
    cods = _mentioned_cods(doc)

    def put(key: str, dato: Dato, *, address: bool = False) -> None:
        if dato.valor is None:
            return
        span = locate(doc, dato.evidencia) or (locate(doc, dato.valor) if address else None)
        if span is None:
            notas.append(f"LLM: '{key}' descartado por falta de evidencia textual ('{dato.valor}').")
            return
        if address:
            parts = [p for p in re.split(r"\s+y\s+|\s*/\s*|,\s*", dato.valor) if p.strip()]
            missing = [p for p in parts if not _street_said(doc, p, cods)]
            if missing:
                notas.append(f"LLM: '{key}' descartado: {', '.join(missing)} no fue dicho por el llamante.")
                return
        campos[key] = Hallazgo(dato.valor, [span], "LLM + evidencia verificada", 0.78)

    u = ext.ubicacion
    for k in ("calle", "altura", "interseccion", "entre_calles", "piso_depto"):
        put(f"ubicacion.{k}", getattr(u, k), address=k in {"calle", "altura", "interseccion", "entre_calles"})
    put("ubicacion.referencia", u.referencia)
    put("ubicacion.barrio", u.barrio, address=True)
    if (alt := campos.get("ubicacion.altura")) is not None:
        digits = re.sub(r"\D", "", alt.value)
        if not digits:
            del campos["ubicacion.altura"]
        else:
            alt.value = digits
    put("suceso.descripcion", ext.suceso.descripcion)
    if ext.suceso.categoria:
        campos["suceso.categoria"] = Hallazgo(ext.suceso.categoria, [], "LLM", 0.75, source="inferido")
    if ext.suceso.subcategoria:
        campos["suceso.subcategoria"] = Hallazgo(ext.suceso.subcategoria, [], "LLM", 0.65, source="inferido")
    if ext.prioridad.valor:
        campos["prioridad"] = Hallazgo(
            ext.prioridad.valor, [], f"LLM: {ext.prioridad.justificacion or 'sin justificación'}", 0.7, source="inferido"
        )
    for k in ("cantidad", "victimas", "estado", "atrapados"):
        put(f"personas.{k}", getattr(ext.personas, k))
    put("llamante.rol", ext.llamante.rol)
    riesgos = [(r.valor, locate(doc, r.evidencia)) for r in ext.riesgos if r.valor]
    riesgos_ok = [(v, s) for v, s in riesgos if s is not None]
    if riesgos_ok:
        campos["riesgos"] = Hallazgo("; ".join(v for v, _ in riesgos_ok[:6]), [s for _, s in riesgos_ok[:6]], "LLM + evidencia verificada", 0.75)
    return campos


def verified_inconsistencias(ext: LLMExtraction, doc: Document) -> list[tuple[str, Evidence | None]]:
    out: list[tuple[str, Evidence | None]] = []
    for h in ext.posibles_inconsistencias[:4]:
        span = locate(doc, h.evidencia)
        if span is not None:
            out.append((h.descripcion, doc.evidence(*span)))
    return out


def verified_respuestas(ext: LLMExtraction, doc: Document, ids: set[str]) -> dict[str, Evidence]:
    out: dict[str, Evidence] = {}
    for r in ext.preguntas_respondidas:
        if r.id in ids and (span := locate(doc, r.evidencia)) is not None and doc.is_caller(span[0]):
            out[r.id] = doc.evidence(*span)
    return out


# ---------------------------------------------------------------- mock determinista


def draft_to_llm_json(draft: Draft, doc: Document) -> str:
    """El proveedor mock responde con el mismo esquema que un LLM, construido
    a partir de las reglas. Así el pipeline completo (parseo, validación,
    verificación, fusión) se ejercita offline y de forma determinista."""

    def dato(key: str) -> dict[str, str | None]:
        h = draft.campos.get(key)
        if h is None:
            return {"valor": None, "evidencia": None}
        ev = doc.text[h.spans[0][0] : h.spans[0][1]] if h.spans else None
        return {"valor": h.value, "evidencia": ev}

    c = draft.campos
    riesgos = []
    if (r := c.get("riesgos")) is not None:
        for label, span in zip(r.value.split("; "), r.spans, strict=False):
            riesgos.append({"valor": label, "evidencia": doc.text[span[0] : span[1]]})
    payload = {
        "ubicacion": {k: dato(f"ubicacion.{k}") for k in ("calle", "altura", "interseccion", "entre_calles", "piso_depto", "referencia", "barrio")},
        "suceso": {
            "categoria": c["suceso.categoria"].value if "suceso.categoria" in c else None,
            "subcategoria": c["suceso.subcategoria"].value if "suceso.subcategoria" in c else None,
            "descripcion": dato("suceso.descripcion"),
        },
        "prioridad": {"valor": c["prioridad"].value if "prioridad" in c else None, "justificacion": c["prioridad"].method if "prioridad" in c else None},
        "personas": {k: dato(f"personas.{k}") for k in ("cantidad", "victimas", "estado", "atrapados")},
        "llamante": {"rol": dato("llamante.rol")},
        "riesgos": riesgos,
        "posibles_inconsistencias": [],
        "preguntas_respondidas": [],
    }
    return json.dumps(payload, ensure_ascii=False)


def address_from_llm(draft: Draft, campos: dict[str, Hallazgo]) -> None:
    """Si el LLM propone otra calle principal, se re-ancla la dirección al callejero."""
    calle = campos.get("ubicacion.calle")
    if calle is None:
        return
    cal = get_callejero()
    found = cal.lookup(calle.value)
    if found is None:
        return
    d = draft.direccion
    same = d.calle_tramos and {t.cod for t in d.calle_tramos} & {t.cod for t in found[1]}
    if same:
        calle.value = display_name(d.calle_tramos[0])  # se conserva el nombre oficial del callejero
    else:
        alt0 = campos.get("ubicacion.altura")
        alt_int = int(alt0.value) if alt0 and alt0.value.isdigit() else None
        calle.value = display_name(cal.pick_tramo(found[1], alt_int, prefer_av=True))
        d.calle = None
        d.calle_tramos = list(found[1])
        d.cruces, d.entre = [], []
        alt = campos.get("ubicacion.altura")
        d.altura = int(alt.value) if alt and alt.value.isdigit() else None
