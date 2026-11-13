"""Detector de posibles inconsistencias: datos que pueden estar mal porque
el llamante se equivocó o porque se transcribió mal. Cada hallazgo apunta
al fragmento que lo origina. Se consulta a demanda (F4)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime

from app.extraction.draft import Draft
from app.extraction.rules import _CANTIDAD_RE
from app.geo.callejero import display_name
from app.schemas import Evidence, GeoValidacion, Inconsistencia
from app.text import word_to_int
from app.transcript import Document

_SALUDOS: tuple[tuple[str, str, tuple[int, int]], ...] = (
    # (regex, etiqueta, rango horario válido [desde, hasta))
    (r"buen(?:os)? d[íi]as?", "buen día", (5, 13)),
    (r"buenas tardes", "buenas tardes", (12, 21)),
    (r"buenas noches", "buenas noches", (19, 30)),  # 30 = 06 del día siguiente
)


def _hour(ts: str | None) -> int | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts).hour
    except ValueError:
        return None


def detectar(
    doc: Document,
    draft: Draft,
    geo: GeoValidacion,
    timestamp: str | None,
    llm_hallazgos: list[tuple[str, Evidence | None]] | None = None,
) -> list[Inconsistencia]:
    out: list[Inconsistencia] = []

    def add(tipo: str, sev: str, msg: str, sug: str | None = None, ev: Evidence | None = None) -> None:
        out.append(Inconsistencia(id=f"inc{len(out) + 1}", tipo=tipo, severidad=sev, mensaje=msg, sugerencia=sug, evidencia=ev))  # type: ignore[arg-type]

    d = draft.direccion
    # 1. Posible error de transcripción en nombres de calles
    for m in [d.calle, *d.cruces, *d.entre]:
        if m is not None and m.match != "exacto":
            oficial = display_name(m.tramos[0])
            add("transcripcion", "media",
                f"Se entendió '{m.surface}': se asumió {oficial} (coincidencia {m.match}).",
                f"Confirmar con el llamante: ¿{oficial}?", doc.evidence(m.start, m.end))
    # 2-4. Validación del callejero
    if geo.calle_existe is False:
        add("direccion", "alta", geo.verificaciones[-1] if geo.verificaciones else "Calle inexistente",
            "Pedir que deletree la calle o una referencia cercana.")
    if geo.altura_en_rango is False:
        alt = draft.campos.get("ubicacion.altura")
        rangos = ", ".join(f"{a}-{b}" for a, b in geo.rangos_altura)
        add("direccion", "alta", f"La altura {alt.value if alt else ''} no existe en {geo.calle_oficial} (rangos: {rangos}).",
            "Repreguntar la altura o la esquina más cercana.",
            doc.evidence(*alt.spans[0]) if alt and alt.spans else None)
    if geo.cruce_valido is False:
        malos = [v for v in geo.verificaciones if "NO cruza" in v]
        add("direccion", "alta", "; ".join(malos) or "Las calles mencionadas no se cruzan.",
            "Verificar la esquina: puede ser otra calle con nombre parecido.")
    # 5. Dirección imprecisa
    if d.calle is not None and d.altura is None and not d.cruces and not d.entre:
        add("direccion", "media", f"Solo se mencionó la calle ({display_name(d.calle_tramos[0])}) sin altura ni esquina.",
            "Preguntar altura o entre qué calles.", doc.evidence(d.calle.start, d.calle.end))
    if d.casi and d.altura is None:
        add("direccion", "baja", "Dirección aproximada ('casi' una esquina) sin altura exacta.", "Pedir número de puerta.")
    alturas_dichas = {int(x) for x in re.findall(r"\bal (\d{2,5})\b", doc.caller_text)}
    if d.altura is not None and len(alturas_dichas - {d.altura}) > 0:
        add("direccion", "alta", f"Se mencionaron alturas distintas: {sorted(alturas_dichas | {d.altura})}.",
            "Confirmar cuál es la altura correcta.")
    # 6. Saludo incompatible con la hora de la llamada
    hour = _hour(timestamp)
    if hour is not None:
        for i, t in enumerate(doc.turns):
            for pat, label, (a, b) in _SALUDOS:
                m = re.search(pat, t.text, re.I)
                h = hour if hour >= a or b <= 24 else hour + 24
                if m and not (a <= h < b):
                    base = doc.bases[i]
                    add("coherencia", "baja",
                        f"Saludo '{label}' a las {hour:02d} h: no coincide con la hora registrada.",
                        "Verificar hora del evento (¿llamada diferida o hecho anterior?).",
                        doc.evidence(base + m.start(), base + m.end()))
                    break
    # 7. Cantidades contradictorias para el mismo sustantivo
    por_sust: dict[str, set[int]] = defaultdict(set)
    for m in _CANTIDAD_RE.finditer(doc.caller_text):
        n = word_to_int(m.group("n"))
        if n is not None:
            por_sust[m.group("what").lower()].add(n)
    for what, ns in por_sust.items():
        if len(ns) > 1:
            add("coherencia", "media", f"Cantidades distintas de {what}: {sorted(ns)}.", "Confirmar cuántos son.")
    # 8. Dudas y autocorrecciones del llamante
    for texto, s, e in draft.dudas[:4]:
        low = texto.lower()
        if any(w in low for w in ("perdón", "perdon", "mejor dicho", "digo")):
            add("autocorreccion", "media", f"El llamante se corrigió ('{texto}').", "Confirmar el dato final.", doc.evidence(s, e))
        elif " o " in low:
            add("incertidumbre", "baja", f"Dato con alternativas: '{texto}'.", "Precisar cuál de las dos opciones es.", doc.evidence(s, e))
        else:
            add("incertidumbre", "baja", f"Dato incierto: '{texto}'.", None, doc.evidence(s, e))
    # 9. Tipología ambigua
    ranked = sorted(draft.categoria_scores.items(), key=lambda kv: -kv[1])
    if len(ranked) > 1 and ranked[0][1] > 0 and ranked[0][1] - ranked[1][1] < 0.12:
        add("tipologia", "media", f"Tipología ambigua entre {ranked[0][0]} y {ranked[1][0]}.",
            "Validar el tipo de hecho antes de derivar.")
    # 10. Prioridad sin evidencia suficiente
    pr = draft.campos.get("prioridad")
    if pr and "verificar" in pr.method:
        add("prioridad", "media", "Los casos similares sugieren P1, pero el relato no tiene señales explícitas de riesgo de vida.",
            "Preguntar por personas atrapadas, inconscientes o con dificultad respiratoria.")
    # 11. Hallazgos del LLM (solo con evidencia verificada)
    for texto, ev in llm_hallazgos or []:
        add("modelo", "media", texto, None, ev)
    sev_order = {"alta": 0, "media": 1, "baja": 2}
    out.sort(key=lambda x: sev_order[x.severidad])
    for i, inc in enumerate(out):
        inc.id = f"inc{i + 1}"
    return out
