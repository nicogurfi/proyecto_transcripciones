"""Estructura intermedia de extracción (antes de convertirse en `Ficha`)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.geo.callejero import Mencion, Tramo
from app.knowledge.catalog import Similar
from app.schemas import Fuente

FIELD_KEYS: tuple[str, ...] = (
    "ubicacion.calle",
    "ubicacion.altura",
    "ubicacion.interseccion",
    "ubicacion.entre_calles",
    "ubicacion.piso_depto",
    "ubicacion.referencia",
    "ubicacion.barrio",
    "suceso.categoria",
    "suceso.subcategoria",
    "suceso.descripcion",
    "prioridad",
    "personas.cantidad",
    "personas.victimas",
    "personas.estado",
    "personas.atrapados",
    "llamante.rol",
    "riesgos",
)


@dataclass(slots=True)
class Hallazgo:
    value: str
    spans: list[tuple[int, int]]
    method: str
    confidence: float
    source: Fuente = "dicho"
    alternatives: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Direccion:
    calle: Mencion | None = None
    calle_tramos: list[Tramo] = field(default_factory=list)
    altura: int | None = None
    cruces: list[Mencion] = field(default_factory=list)
    entre: list[Mencion] = field(default_factory=list)
    otras: list[Mencion] = field(default_factory=list)
    casi: bool = False  # "casi X": cerca de la esquina, no exactamente


@dataclass(slots=True)
class Draft:
    campos: dict[str, Hallazgo] = field(default_factory=dict)
    direccion: Direccion = field(default_factory=Direccion)
    categoria_scores: dict[str, float] = field(default_factory=dict)
    similares: list[Similar] = field(default_factory=list)
    senales_p1: list[tuple[str, int, int]] = field(default_factory=list)
    dudas: list[tuple[str, int, int]] = field(default_factory=list)  # hedges / autocorrecciones
    # Evolución durante la llamada: (campo, antes, ahora, start, end) del dato más reciente
    cambios: list[tuple[str, str, str, int, int]] = field(default_factory=list)
    # Señales de riesgo de vida que parecen resolverse más adelante: (señal, evidencia, start, end)
    senales_resueltas: list[tuple[str, str, int, int]] = field(default_factory=list)
    notas: list[str] = field(default_factory=list)
