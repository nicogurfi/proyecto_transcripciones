import { z } from "zod";
import {
  Analisis, Carta, CasoDetalle, CasosLista, GeoValidacion, Health, SimulacroCaso, SimulacroResultado, SimulacroStats,
  type Turn,
} from "./schemas";

export class ApiError extends Error {}

async function getJson<T>(url: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) {
    const detail = await r.text();
    throw new ApiError(`${r.status}: ${detail.slice(0, 200)}`);
  }
  const parsed = schema.safeParse(await r.json());
  if (!parsed.success) throw new ApiError(`Respuesta inválida del servidor: ${parsed.error.issues[0]?.message ?? ""}`);
  return parsed.data;
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => getJson("/api/health", Health),
  casos: () => getJson("/api/casos", CasosLista),
  caso: (id: string) => getJson(`/api/casos/${encodeURIComponent(id)}`, CasoDetalle),
  parsear: (texto: string) => getJson("/api/parsear", z.object({ turnos: z.array(z.object({ speaker: z.enum(["operador", "llamante"]), text: z.string() })) }), json({ texto })),
  calles: (q: string) => getJson(`/api/calles?q=${encodeURIComponent(q)}`, z.array(z.string())),
  validarDireccion: (body: { calle: string | null; altura: string | null; interseccion: string | null; entre_calles: string | null }) =>
    getJson("/api/geo/validar", GeoValidacion, json(body)),
  derivar: (body: unknown) => getJson("/api/cartas", Carta, json(body)),
  previsualizar: (body: unknown) => getJson("/api/cartas/previsualizar", Carta, json(body)),
  cartas: () => getJson("/api/cartas", z.array(Carta)),
  correcciones: () => getJson("/api/correcciones", z.array(z.object({ campo: z.string(), n: z.number(), conf: z.number().nullable() }))),
  simCaso: (dificultad: string, excluir: string[]) =>
    getJson(`/api/simulacro/caso?dificultad=${dificultad}&excluir=${excluir.join(",")}`, SimulacroCaso),
  simEvaluar: (body: unknown) => getJson("/api/simulacro/evaluar", SimulacroResultado, json(body)),
  simStats: () => getJson("/api/simulacro/stats", SimulacroStats),
};

/** Análisis en streaming NDJSON: primero la fase rápida (reglas), luego la final (LLM + USIG). */
export async function analizarStream(
  body: { turnos: Turn[]; timestamp?: string | null },
  onFase: (a: Analisis) => void,
  signal: AbortSignal,
): Promise<void> {
  const r = await fetch("/api/analizar", { ...json(body), signal });
  if (!r.ok || !r.body) throw new ApiError(`Error de análisis (${r.status})`);
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let nl: number;
    while ((nl = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, nl).trim();
      buffer = buffer.slice(nl + 1);
      if (!line) continue;
      const raw: unknown = JSON.parse(line);
      if (raw && typeof raw === "object" && "error" in raw) throw new ApiError(String((raw as { error: unknown }).error));
      const parsed = Analisis.safeParse(raw);
      if (!parsed.success) throw new ApiError(`Contrato inválido: ${parsed.error.issues[0]?.path.join(".")}`);
      onFase(parsed.data);
    }
  }
}
