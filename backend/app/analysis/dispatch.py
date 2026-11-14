"""Información para el despachador: recursos sugeridos y nota operativa.

El operador no decide el despacho: todo lo que sale de acá es REFERENCIA
para el despachador CAD.

- Recursos: se copian del catálogo solo si el caso es realmente parecido
  (similitud >= SUBCATEGORIA_UMBRAL). Si no, se sugieren organismos a
  notificar con reglas auditables (categoría + riesgos del relato).
- Nota operativa: se arma con una plantilla SOLO con datos de la ficha
  (validados por evidencia o por el operador). No usa LLM, no puede inventar.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.knowledge.catalog import SUBCATEGORIA_UMBRAL, Similar
from app.schemas import GeoValidacion, RecursoSugerido

CATEGORIA_TEXTO: dict[str, str] = {
    "INCENDIO_RESCATE": "Incendio / rescate",
    "ACCIDENTE_VIAL": "Accidente vial",
    "EMERGENCIA_MEDICA": "Emergencia médica",
    "DEFENSA_CIVIL": "Emergencia de Defensa Civil",
    "SERVICIOS_PUBLICOS": "Falla de servicio público",
    "CONVIVENCIA_SEGURIDAD": "Hecho de convivencia / seguridad",
}

# (organismo, motivo, patrón sobre el texto de la ficha + relato)
_REGLAS_RIESGO: tuple[tuple[str, str, str], ...] = (
    ("Unidad de Rescate de Bomberos", "persona atrapada", r"atrapad|qued[óo] adentro|adentro qued[óo]|debajo del|no puede salir"),
    ("Dotación de Bomberos de la Ciudad", "fuego o humo", r"fuego|incendi|humo|llama"),
    ("Bomberos – Materiales Peligrosos (Hazmat)", "baterías de litio / sustancias peligrosas", r"litio|qu[íi]mic|t[óo]xic"),
    ("Alerta a Metrogas Emergencias", "pérdida de gas", r"\bgas\b"),
    ("Guardia de urgencias Edesur / Edenor", "riesgo eléctrico", r"cable|chispa|tablero|transformador|subestaci|tensi[óo]n"),
    ("AySA – cuadrilla de redes", "agua / cloacas", r"caño|agua potable|cloac|colector|socav"),
    ("Móvil de Tránsito para corte o desvío", "tránsito activo en la zona", r"tr[áa]nsito|autos siguen pasando|carril|autopista|sem[áa]foro"),
    ("Ambulancia SAME", "personas heridas o descompensadas", r"herid|sangr|fractura|desmay|inconscien|no responde|no respira|dolor|no se mueve|consciente|golpe"),
    ("Móvil policial", "armas o agresión", r"\barmas?\b|cuchillo|pelea|agresi|disturb"),
    ("Unidad de Sanidad y Protección Animal", "animal agresivo", r"perro|pitbull|dogo|animal"),
)

_BASE_CATEGORIA: dict[str, tuple[str, str]] = {
    "INCENDIO_RESCATE": ("Dotación de Bomberos de la Ciudad", "tipo de hecho"),
    "EMERGENCIA_MEDICA": ("Ambulancia SAME", "tipo de hecho"),
    "ACCIDENTE_VIAL": ("Móvil de Tránsito para corte o desvío", "tipo de hecho"),
    "DEFENSA_CIVIL": ("Defensa Civil / Guardia de Auxilio", "tipo de hecho"),
    "SERVICIOS_PUBLICOS": ("Cuadrilla de la empresa de servicio correspondiente", "tipo de hecho"),
    "CONVIVENCIA_SEGURIDAD": ("Móvil policial", "tipo de hecho"),
}


def _v(values: Mapping[str, str | None], key: str) -> str:
    return (values.get(key) or "").strip()


def recursos_sugeridos(
    values: Mapping[str, str | None], similares: list[Similar], geo: GeoValidacion | None, relato: str
) -> list[RecursoSugerido]:
    categoria = _v(values, "suceso.categoria")
    same = [s for s in similares if s.caso.categoria == categoria] if categoria else []
    if same and same[0].similitud >= SUBCATEGORIA_UMBRAL:
        best = same[0]
        return [
            RecursoSugerido(
                texto=parte.strip(),
                fuente=f"catálogo {best.caso.id}",
                motivo=f"caso equivalente ({best.caso.subcategoria}, similitud {best.similitud:.2f})",
            )
            for parte in best.caso.recursos.split("+")
            if parte.strip()
        ]

    texto = " ".join(
        [relato, *(_v(values, k) for k in ("riesgos", "personas.estado", "personas.atrapados", "suceso.descripcion"))]
    )
    if _v(values, "personas.atrapados").lower().startswith("no"):
        texto = re.sub(r"atrapad\w*|qued[óo] adentro|adentro qued[óo]", "", texto, flags=re.I)
    out: list[RecursoSugerido] = []

    def add(texto_recurso: str, motivo: str) -> None:
        if all(r.texto != texto_recurso for r in out):
            out.append(RecursoSugerido(texto=texto_recurso, fuente="regla", motivo=motivo))

    if categoria in _BASE_CATEGORIA:
        nombre, motivo = _BASE_CATEGORIA[categoria]
        if nombre == "Ambulancia SAME" and _v(values, "prioridad") == "P1":
            nombre = "Ambulancia SAME Código Rojo"
        if nombre == "Móvil policial" and geo and geo.comisaria_vecinal:
            nombre = f"Móvil policial – Comisaría vecinal {geo.comisaria_vecinal}"
        add(nombre, motivo)
    for nombre, motivo, patron in _REGLAS_RIESGO:
        if re.search(patron, texto, re.I):
            if nombre == "Ambulancia SAME" and any(r.texto.startswith("Ambulancia SAME") for r in out):
                continue
            if nombre == "Móvil policial" and any(r.texto.startswith("Móvil policial") for r in out):
                continue
            add(nombre, motivo)
    return out[:5]


def componer_direccion(values: Mapping[str, str | None]) -> str:
    calle, altura = _v(values, "ubicacion.calle"), _v(values, "ubicacion.altura")
    partes: list[str] = []
    if calle:
        partes.append(f"{calle} {altura}".strip())
    if piso := _v(values, "ubicacion.piso_depto"):
        partes.append(piso)
    if inter := _v(values, "ubicacion.interseccion"):
        partes.append(f"esq. {inter}")
    if entre := _v(values, "ubicacion.entre_calles"):
        partes.append(f"entre {entre}")
    texto = ", ".join(partes)
    if ref := _v(values, "ubicacion.referencia"):
        texto = f"{texto} ({ref})".strip()
    if barrio := _v(values, "ubicacion.barrio"):
        texto = f"{texto} – {barrio}".strip(" –")
    return texto or "SIN DIRECCIÓN"


def nota_operativa(values: Mapping[str, str | None], geo: GeoValidacion | None, alertas: list[str]) -> str:
    """Nota telegráfica para el despachador, en el estilo de las notas del dataset."""
    tipo = _v(values, "suceso.subcategoria") or CATEGORIA_TEXTO.get(_v(values, "suceso.categoria"), "Hecho a determinar")
    direccion = componer_direccion(values)
    validada = geo is not None and geo.estado == "validada"
    frases = [f"{tipo} en {direccion}{'' if validada or direccion == 'SIN DIRECCIÓN' else ' (dirección sin validar)'}."]
    if desc := _v(values, "suceso.descripcion"):
        frases.append(f"Relato: {desc.rstrip('.')}.")
    quienes = ", ".join(x for x in (_v(values, "personas.cantidad"), _v(values, "personas.victimas")) if x)
    estado = _v(values, "personas.estado")
    if quienes or estado:
        frases.append(f"Personas: {quienes or 's/d'}{f' – {estado}' if estado else ''}.")
    if (atr := _v(values, "personas.atrapados")):
        frases.append(f"Atrapados: {atr}.")
    if riesgos := _v(values, "riesgos"):
        frases.append(f"Riesgos: {riesgos}.")
    if alertas:
        frases.append("Alertas de seguridad: " + " / ".join(a.rstrip(".") for a in alertas) + ".")
    return " ".join(frases)
