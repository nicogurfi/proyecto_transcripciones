"""Capa de seguridad determinista: contraindicaciones críticas y
instrucciones de pre-arribo.

Las alertas críticas NUNCA dependen del LLM ni del retrieval: se disparan
por reglas auditables con evidencia en el relato. Es la única información
que se muestra sin que el operador la pida.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.extraction.draft import Draft
from app.knowledge.catalog import INSTRUCCIONES_CATEGORIA, SUBCATEGORIA_UMBRAL
from app.schemas import AlertaCritica, Instruccion
from app.transcript import Document


@dataclass(frozen=True, slots=True)
class ReglaCritica:
    id: str
    requiere: tuple[str, ...]  # todas las expresiones deben aparecer
    texto: str
    motivo: str


REGLAS: tuple[ReglaCritica, ...] = (
    ReglaCritica("casco", (r"\bmoto|motociclista|delivery", r"casco"),
                 "NO retirar el casco del motociclista ni moverlo.", "Posible lesión cervical"),
    ReglaCritica("litio", (r"litio|bater[íi]a", r"fuego|explot|llama|humo"),
                 "NO usar agua: fuego de baterías de litio. Evacuar y cerrar el local.", "Reacción violenta del litio con agua"),
    ReglaCritica("electrico_agua", (r"tablero|transformador|subestaci|el[ée]ctric", r"fuego|humo|chispa|explosi"),
                 "NO arrojar agua sobre equipos eléctricos.", "Riesgo de electrocución"),
    ReglaCritica("cables", (r"cables?", r"chispe|cortad|ca[íi]d|arranc[óo]"),
                 "Considerar los cables energizados: mantener a todos a más de 15 metros.", "Tensión de paso / electrocución"),
    ReglaCritica("gas", (r"\bgas\b",), "NO accionar interruptores, timbres ni encender fuego. Evacuar.", "Riesgo de explosión"),
    ReglaCritica("convulsion", (r"convuls",), "NUNCA introducir dedos ni objetos en la boca.", "Riesgo de lesión y asfixia"),
    ReglaCritica("respiratorio", (r"no le entra el aire|asma|broncoespasmo|ahog",),
                 "Mantener a la persona sentada y erguida. NO acostarla.", "Dificultad respiratoria"),
    ReglaCritica("reingreso", (r"atrapad|qued[óo] adentro|adentro qued[óo]", r"fuego|humo|incendi|llama"),
                 "NO reingresar al lugar por ningún motivo.", "Incendio con personas atrapadas"),
    ReglaCritica("anafilaxia", (r"al[ée]rgic|anafilax", r"garganta|hinch|tragar|respir"),
                 "Si tiene autoinyector de adrenalina, aplicarlo YA en la cara externa del muslo.", "Anafilaxia"),
    ReglaCritica("agua_vehiculos", (r"inund|anegad|agua llega", r"auto|techo|veh[íi]culo"),
                 "NO intentar cruzar ni nadar en el agua: permanecer sobre los vehículos.", "Succión por sumideros"),
    ReglaCritica("combustible", (r"gasoil|nafta|combustible|derrame",),
                 "Prohibido fumar o encender fuego cerca del derrame.", "Inflamabilidad"),
    ReglaCritica("atrapado_vehiculo", (r"atrapad|debajo del|no puede abrir", r"auto|colectivo|veh[íi]culo|cintur[óo]n|estribo"),
                 "NO tirar de la víctima ni moverla. Apagar el motor si es seguro.", "Lesión de columna / atrapamiento"),
)


def alertas_criticas(doc: Document) -> list[AlertaCritica]:
    caller_turns = [(i, t) for i, t in enumerate(doc.turns) if t.speaker == "llamante"]
    text = " ".join(t.text for _, t in caller_turns)
    out: list[AlertaCritica] = []
    for regla in REGLAS:
        if all(re.search(p, text, re.I) for p in regla.requiere):
            ev = None
            for i, t in caller_turns:
                m = re.search(regla.requiere[0], t.text, re.I)
                if m:
                    base = doc.bases[i]
                    ev = doc.evidence(base + m.start(), base + m.end())
                    break
            out.append(AlertaCritica(id=regla.id, texto=regla.texto, motivo=regla.motivo, evidencia=ev))
    return out[:3]  # más de 3 alertas fijas dejaría de ser una alerta


def _split_instrucciones(raw: str) -> list[str]:
    parts = re.split(r"(?<=[.!])\s+", raw.strip())
    return [p.strip() for p in parts if len(p.strip()) > 8]


def instrucciones(draft: Draft, alertas: list[AlertaCritica]) -> list[Instruccion]:
    out: list[Instruccion] = []
    seen: set[str] = set()

    def add(texto: str, critica: bool, fuente: str, conf: float) -> None:
        key = texto.lower()[:60]
        if key in seen:
            return
        seen.add(key)
        out.append(Instruccion(id=f"i{len(out) + 1}", texto=texto, critica=critica, fuente=fuente, confianza=round(conf, 2)))

    for a in alertas:
        add(a.texto, True, "regla de seguridad", 0.95)
    cat = draft.campos.get("suceso.categoria")
    same = [s for s in draft.similares if cat is None or s.caso.categoria == cat.value]
    if same and same[0].similitud >= SUBCATEGORIA_UMBRAL:
        best = same[0]
        for txt in _split_instrucciones(best.caso.instrucciones):
            critica = bool(re.search(r"\bNO\b|NUNCA|PROHIBIDO|BAJO NINGUNA", txt))
            add(txt, critica, f"caso similar {best.caso.id}", min(0.9, best.similitud))
    if cat is not None:
        for txt in INSTRUCCIONES_CATEGORIA.get(cat.value, ()):
            add(txt, False, f"protocolo {cat.value}", 0.7)
    return out
