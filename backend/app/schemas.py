"""Contratos de datos (Pydantic v2). Son la única fuente de verdad del API;
el frontend los replica con Zod en `frontend/src/api/schemas.ts`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Speaker = Literal["operador", "llamante"]
Categoria = Literal[
    "INCENDIO_RESCATE",
    "ACCIDENTE_VIAL",
    "EMERGENCIA_MEDICA",
    "DEFENSA_CIVIL",
    "SERVICIOS_PUBLICOS",
    "CONVIVENCIA_SEGURIDAD",
]
CATEGORIAS: tuple[Categoria, ...] = (
    "INCENDIO_RESCATE",
    "ACCIDENTE_VIAL",
    "EMERGENCIA_MEDICA",
    "DEFENSA_CIVIL",
    "SERVICIOS_PUBLICOS",
    "CONVIVENCIA_SEGURIDAD",
)
Prioridad = Literal["P1", "P2", "P3", "P4"]
PRIORIDADES: tuple[Prioridad, ...] = ("P1", "P2", "P3", "P4")
Fuente = Literal["dicho", "inferido", "operador"]
Nivel = Literal["alta", "media", "baja"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Turn(StrictModel):
    speaker: Speaker
    text: str = Field(min_length=1, max_length=5000)


class Evidence(StrictModel):
    turn: int
    start: int
    end: int
    text: str


class Campo(StrictModel):
    """Un dato de la ficha con trazabilidad completa."""

    value: str | None = None
    confidence: float = 0.0  # 0..1, calculada a partir de evidencia (no autodeclarada por el LLM)
    level: Nivel = "baja"
    source: Fuente = "dicho"
    method: str = ""  # cómo se obtuvo: "callejero exacto", "llm + evidencia", ...
    evidence: list[Evidence] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)


class Ubicacion(StrictModel):
    calle: Campo = Field(default_factory=Campo)
    altura: Campo = Field(default_factory=Campo)
    interseccion: Campo = Field(default_factory=Campo)
    entre_calles: Campo = Field(default_factory=Campo)
    piso_depto: Campo = Field(default_factory=Campo)
    referencia: Campo = Field(default_factory=Campo)
    barrio: Campo = Field(default_factory=Campo)


class Suceso(StrictModel):
    categoria: Campo = Field(default_factory=Campo)
    subcategoria: Campo = Field(default_factory=Campo)
    descripcion: Campo = Field(default_factory=Campo)


class Personas(StrictModel):
    cantidad: Campo = Field(default_factory=Campo)
    victimas: Campo = Field(default_factory=Campo)
    estado: Campo = Field(default_factory=Campo)
    atrapados: Campo = Field(default_factory=Campo)


class Llamante(StrictModel):
    rol: Campo = Field(default_factory=Campo)


class Ficha(StrictModel):
    ubicacion: Ubicacion = Field(default_factory=Ubicacion)
    suceso: Suceso = Field(default_factory=Suceso)
    prioridad: Campo = Field(default_factory=Campo)
    personas: Personas = Field(default_factory=Personas)
    llamante: Llamante = Field(default_factory=Llamante)
    riesgos: Campo = Field(default_factory=Campo)


class GeoValidacion(StrictModel):
    estado: Literal["validada", "parcial", "no_validada", "sin_datos"] = "sin_datos"
    direccion_normalizada: str | None = None
    calle_oficial: str | None = None
    calle_existe: bool | None = None
    altura_en_rango: bool | None = None
    rangos_altura: list[tuple[int, int]] = Field(default_factory=list)
    cruce_valido: bool | None = None
    lat: float | None = None
    lon: float | None = None
    barrio: str | None = None
    comuna: str | None = None
    comisaria_vecinal: str | None = None
    fuente_coordenadas: Literal["usig", "cache"] | None = None
    verificaciones: list[str] = Field(default_factory=list)


class PasoProtocolo(StrictModel):
    numero: int
    nombre: str
    objetivo: str
    estado: Literal["completo", "parcial", "pendiente"]
    faltantes: list[str] = Field(default_factory=list)


class ChecklistItem(StrictModel):
    id: str
    pregunta: str
    origen: Literal["base", "categoria", "subcategoria"]
    critica: bool = False
    estado: Literal["pendiente", "respondida_sugerida"] = "pendiente"
    confianza: float = 0.0
    evidencia: Evidence | None = None


class Instruccion(StrictModel):
    id: str
    texto: str
    critica: bool = False
    fuente: str
    confianza: float


class AlertaCritica(StrictModel):
    id: str
    texto: str
    motivo: str
    evidencia: Evidence | None = None


class CasoSimilar(StrictModel):
    id: str
    categoria: str
    subcategoria: str
    prioridad: str
    similitud: float
    nota_despacho: str
    recursos: str


class RecursoSugerido(StrictModel):
    texto: str
    fuente: str  # "catálogo SFX-..." | "regla"
    motivo: str


class Inconsistencia(StrictModel):
    id: str
    tipo: str
    severidad: Literal["alta", "media", "baja"]
    mensaje: str
    sugerencia: str | None = None
    evidencia: Evidence | None = None


class Analisis(StrictModel):
    fase: Literal["rapida", "final"]
    proveedor: str
    modelo: str | None = None
    latencia_ms: int
    turnos: list[Turn]
    ficha: Ficha
    geo: GeoValidacion
    pasos: list[PasoProtocolo]
    paso_sugerido: int
    checklist: list[ChecklistItem]
    instrucciones: list[Instruccion]
    alertas_criticas: list[AlertaCritica]
    casos_similares: list[CasoSimilar]
    inconsistencias: list[Inconsistencia]
    recursos_sugeridos: list[RecursoSugerido] = Field(default_factory=list)
    nota_operativa: str = ""
    notas: list[str] = Field(default_factory=list)


class AnalisisRequest(StrictModel):
    turnos: list[Turn] | None = None
    texto: str | None = Field(default=None, max_length=20000)
    timestamp: str | None = None  # ISO-8601 de la llamada (para chequeos de coherencia)
    caso_ref: str | None = None  # id del dataset, para excluirlo del retrieval (leave-one-out)
    usar_llm: bool = True


# ---------- Carta de llamada ----------


class ChecklistEstado(StrictModel):
    pregunta: str
    estado: Literal["pendiente", "respondida_sugerida", "confirmada", "no_aplica"]
    evidencia: str | None = None


class CartaRequest(StrictModel):
    turnos: list[Turn]
    valores_finales: dict[str, str | None]  # "ubicacion.calle" -> valor validado por el operador
    valores_sugeridos: dict[str, str | None] = Field(default_factory=dict)
    confianzas: dict[str, float] = Field(default_factory=dict)
    campos_validados: list[str] = Field(default_factory=list)
    checklist: list[ChecklistEstado] = Field(default_factory=list)
    instrucciones_transmitidas: list[str] = Field(default_factory=list)
    alertas_criticas: list[str] = Field(default_factory=list)
    recursos_sugeridos: list[str] = Field(default_factory=list)
    geo: GeoValidacion | None = None
    notas_operador: str | None = Field(default=None, max_length=2000)
    nota_operativa: str | None = Field(default=None, max_length=2000)  # si el operador la editó
    origen: str = "TELEFONIA_911"
    caso_ref: str | None = None
    timestamp_llamada: str | None = None
    duracion_segundos: int | None = None
    proveedor: str | None = None


class Carta(StrictModel):
    numero: str
    creada: str
    estado: Literal["DERIVADA"] = "DERIVADA"
    completa: bool
    advertencias: list[str]
    origen: str
    prioridad: str | None
    categoria: str | None
    subcategoria: str | None
    direccion: str
    direccion_validada: bool
    lat: float | None
    lon: float | None
    barrio: str | None
    comisaria_vecinal: str | None
    resumen: str
    nota_operativa: str
    recursos_detalle: list[RecursoSugerido]
    personas: str | None
    riesgos: str | None
    preguntas_respondidas: list[str]
    preguntas_pendientes: list[str]
    instrucciones_transmitidas: list[str]
    alertas_criticas: list[str]
    recursos_sugeridos: list[str]
    notas_operador: str | None
    correcciones_operador: int
    duracion_segundos: int | None
    texto_plano: str


# ---------- Simulacro ----------


class SimulacroCaso(StrictModel):
    caso_id: str
    turnos: list[Turn]
    timestamp: str
    origen: str
    dificultad: Literal["normal", "ruidosa"]


class SimulacroRespuesta(StrictModel):
    caso_id: str
    dificultad: Literal["normal", "ruidosa"] = "normal"
    calle: str | None = None
    altura: str | None = None
    interseccion: str | None = None
    categoria: str | None = None
    prioridad: str | None = None
    preguntas_pendientes: list[str] = Field(default_factory=list)
    instrucciones: str | None = None
    tiempo_segundos: int = 0


class SimulacroItem(StrictModel):
    criterio: str
    puntaje: float
    maximo: float
    detalle: str
    esperado: str | None = None
    respondido: str | None = None


class SimulacroResultado(StrictModel):
    caso_id: str
    puntaje: float
    maximo: float
    porcentaje: int
    items: list[SimulacroItem]
    copiloto: dict[str, str | None]
    referencia: dict[str, str]
    comentario: str
