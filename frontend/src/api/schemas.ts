// Contratos del API validados en runtime con Zod (espejo de backend/app/schemas.py).
// Si el backend cambia el contrato, la UI falla de forma explícita en vez de mostrar datos corruptos.
import { z } from "zod";

export const Speaker = z.enum(["operador", "llamante"]);
export const Turn = z.object({ speaker: Speaker, text: z.string() });
export type Turn = z.infer<typeof Turn>;

export const Evidence = z.object({ turn: z.number(), start: z.number(), end: z.number(), text: z.string() });
export type Evidence = z.infer<typeof Evidence>;

export const Campo = z.object({
  value: z.string().nullable(),
  confidence: z.number(),
  level: z.enum(["alta", "media", "baja"]),
  source: z.enum(["dicho", "inferido", "operador"]),
  method: z.string(),
  evidence: z.array(Evidence),
  alternatives: z.array(z.string()),
});
export type Campo = z.infer<typeof Campo>;

export const Ficha = z.object({
  ubicacion: z.object({
    calle: Campo, altura: Campo, interseccion: Campo, entre_calles: Campo,
    piso_depto: Campo, referencia: Campo, barrio: Campo,
  }),
  suceso: z.object({ categoria: Campo, subcategoria: Campo, descripcion: Campo }),
  prioridad: Campo,
  personas: z.object({ cantidad: Campo, victimas: Campo, estado: Campo, atrapados: Campo }),
  llamante: z.object({ rol: Campo }),
  riesgos: Campo,
});
export type Ficha = z.infer<typeof Ficha>;

export const GeoValidacion = z.object({
  estado: z.enum(["validada", "parcial", "no_validada", "sin_datos"]),
  direccion_normalizada: z.string().nullable(),
  calle_oficial: z.string().nullable(),
  calle_existe: z.boolean().nullable(),
  altura_en_rango: z.boolean().nullable(),
  rangos_altura: z.array(z.tuple([z.number(), z.number()])),
  cruce_valido: z.boolean().nullable(),
  lat: z.number().nullable(),
  lon: z.number().nullable(),
  barrio: z.string().nullable(),
  comuna: z.string().nullable(),
  comisaria_vecinal: z.string().nullable(),
  fuente_coordenadas: z.enum(["usig", "cache"]).nullable(),
  verificaciones: z.array(z.string()),
});
export type GeoValidacion = z.infer<typeof GeoValidacion>;

export const PasoProtocolo = z.object({
  numero: z.number(), nombre: z.string(), objetivo: z.string(),
  estado: z.enum(["completo", "parcial", "pendiente"]), faltantes: z.array(z.string()),
});
export type PasoProtocolo = z.infer<typeof PasoProtocolo>;

export const ChecklistItem = z.object({
  id: z.string(), pregunta: z.string(), origen: z.enum(["base", "categoria", "subcategoria"]),
  critica: z.boolean(), estado: z.enum(["pendiente", "respondida_sugerida"]),
  confianza: z.number(), evidencia: Evidence.nullable(),
});
export type ChecklistItem = z.infer<typeof ChecklistItem>;

export const Instruccion = z.object({
  id: z.string(), texto: z.string(), critica: z.boolean(), fuente: z.string(), confianza: z.number(),
});
export type Instruccion = z.infer<typeof Instruccion>;

export const AlertaCritica = z.object({
  id: z.string(), texto: z.string(), motivo: z.string(), evidencia: Evidence.nullable(),
});
export type AlertaCritica = z.infer<typeof AlertaCritica>;

export const CasoSimilar = z.object({
  id: z.string(), categoria: z.string(), subcategoria: z.string(), prioridad: z.string(),
  similitud: z.number(), nota_despacho: z.string(), recursos: z.string(),
});
export type CasoSimilar = z.infer<typeof CasoSimilar>;

export const RecursoSugerido = z.object({ texto: z.string(), fuente: z.string(), motivo: z.string() });
export type RecursoSugerido = z.infer<typeof RecursoSugerido>;

export const Inconsistencia = z.object({
  id: z.string(), tipo: z.string(), severidad: z.enum(["alta", "media", "baja"]),
  mensaje: z.string(), sugerencia: z.string().nullable(), evidencia: Evidence.nullable(),
});
export type Inconsistencia = z.infer<typeof Inconsistencia>;

export const Analisis = z.object({
  fase: z.enum(["rapida", "final"]),
  proveedor: z.string(),
  modelo: z.string().nullable(),
  latencia_ms: z.number(),
  turnos: z.array(Turn),
  ficha: Ficha,
  geo: GeoValidacion,
  pasos: z.array(PasoProtocolo),
  paso_sugerido: z.number(),
  checklist: z.array(ChecklistItem),
  instrucciones: z.array(Instruccion),
  alertas_criticas: z.array(AlertaCritica),
  casos_similares: z.array(CasoSimilar),
  inconsistencias: z.array(Inconsistencia),
  recursos_sugeridos: z.array(RecursoSugerido),
  nota_operativa: z.string(),
  notas: z.array(z.string()),
});
export type Analisis = z.infer<typeof Analisis>;

export const Health = z.object({
  ok: z.boolean(), proveedor: z.string(), modelo: z.string().nullable(), mock: z.boolean(),
  embeddings: z.string(), usig_habilitado: z.boolean(), avisos: z.array(z.string()),
  categorias: z.array(z.string()), prioridades: z.record(z.string()),
});
export type Health = z.infer<typeof Health>;

export const CasoResumen = z.object({
  id: z.string(), titulo: z.string(), origen: z.string(), timestamp: z.string(), fuente: z.enum(["dataset", "demo"]),
  categoria: z.string().optional(), prioridad: z.string().optional(),
});
export type CasoResumen = z.infer<typeof CasoResumen>;
export const CasosLista = z.object({ demo: z.array(CasoResumen), dataset: z.array(CasoResumen) });

export const CasoDetalle = z.object({
  id: z.string(), titulo: z.string(), timestamp: z.string(), origen: z.string(), turnos: z.array(Turn),
});
export type CasoDetalle = z.infer<typeof CasoDetalle>;

export const Carta = z.object({
  numero: z.string(), creada: z.string(), estado: z.literal("DERIVADA"), completa: z.boolean(),
  advertencias: z.array(z.string()), origen: z.string(), prioridad: z.string().nullable(),
  categoria: z.string().nullable(), subcategoria: z.string().nullable(), direccion: z.string(),
  direccion_validada: z.boolean(), lat: z.number().nullable(), lon: z.number().nullable(),
  barrio: z.string().nullable(), comisaria_vecinal: z.string().nullable(), resumen: z.string(),
  nota_operativa: z.string(), recursos_detalle: z.array(RecursoSugerido),
  personas: z.string().nullable(), riesgos: z.string().nullable(),
  preguntas_respondidas: z.array(z.string()), preguntas_pendientes: z.array(z.string()),
  instrucciones_transmitidas: z.array(z.string()), alertas_criticas: z.array(z.string()),
  recursos_sugeridos: z.array(z.string()), notas_operador: z.string().nullable(),
  correcciones_operador: z.number(), duracion_segundos: z.number().nullable(), texto_plano: z.string(),
});
export type Carta = z.infer<typeof Carta>;

export const SimulacroCaso = z.object({
  caso_id: z.string(), turnos: z.array(Turn), timestamp: z.string(), origen: z.string(),
  dificultad: z.enum(["normal", "ruidosa"]),
});
export type SimulacroCaso = z.infer<typeof SimulacroCaso>;

export const SimulacroResultado = z.object({
  caso_id: z.string(), puntaje: z.number(), maximo: z.number(), porcentaje: z.number(),
  items: z.array(z.object({
    criterio: z.string(), puntaje: z.number(), maximo: z.number(), detalle: z.string(),
    esperado: z.string().nullable(), respondido: z.string().nullable(),
  })),
  copiloto: z.record(z.string().nullable()),
  referencia: z.record(z.string()),
  comentario: z.string(),
});
export type SimulacroResultado = z.infer<typeof SimulacroResultado>;

export const SimulacroStats = z.object({
  sesiones: z.number(), promedio: z.number(), tiempo_promedio: z.number(),
  ultimos: z.array(z.object({ caso_id: z.string(), porcentaje: z.number(), tiempo_segundos: z.number(), creado: z.string() })),
});
export type SimulacroStats = z.infer<typeof SimulacroStats>;

// Claves planas de la ficha (iguales a backend/app/extraction/draft.py::FIELD_KEYS)
export const FIELD_KEYS = [
  "ubicacion.calle", "ubicacion.altura", "ubicacion.interseccion", "ubicacion.entre_calles",
  "ubicacion.piso_depto", "ubicacion.referencia", "ubicacion.barrio",
  "suceso.categoria", "suceso.subcategoria", "suceso.descripcion", "prioridad",
  "personas.cantidad", "personas.victimas", "personas.estado", "personas.atrapados",
  "llamante.rol", "riesgos",
] as const;
export type FieldKey = (typeof FIELD_KEYS)[number];

export function getCampo(f: Ficha, key: FieldKey): Campo {
  const [a, b] = key.split(".") as [string, string | undefined];
  const section = (f as unknown as Record<string, unknown>)[a];
  return (b ? (section as Record<string, Campo>)[b] : section) as Campo;
}
