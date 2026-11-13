import type { FieldKey } from "./api/schemas";

export const LABELS: Record<FieldKey, string> = {
  "ubicacion.calle": "Calle",
  "ubicacion.altura": "Altura",
  "ubicacion.interseccion": "Esquina",
  "ubicacion.entre_calles": "Entre calles",
  "ubicacion.piso_depto": "Piso / Depto",
  "ubicacion.referencia": "Referencia",
  "ubicacion.barrio": "Barrio",
  "suceso.categoria": "Tipo",
  "suceso.subcategoria": "Subtipo",
  "suceso.descripcion": "Relato",
  prioridad: "Prioridad",
  "personas.cantidad": "Cantidad",
  "personas.victimas": "Quiénes",
  "personas.estado": "Estado",
  "personas.atrapados": "Atrapados",
  "llamante.rol": "Llamante",
  riesgos: "Riesgos",
};

export const CATEGORIA_LABEL: Record<string, string> = {
  INCENDIO_RESCATE: "Incendio / Rescate",
  ACCIDENTE_VIAL: "Accidente vial",
  EMERGENCIA_MEDICA: "Emergencia médica",
  DEFENSA_CIVIL: "Defensa civil",
  SERVICIOS_PUBLICOS: "Servicios públicos",
  CONVIVENCIA_SEGURIDAD: "Convivencia / Seguridad",
};

export const PRIORIDAD_LABEL: Record<string, string> = {
  P1: "Riesgo de vida inminente",
  P2: "Riesgo potencial / urgente",
  P3: "Urgencia sin riesgo de vida",
  P4: "No urgente / informativo",
};

export const pct = (x: number) => `${Math.round(x * 100)}%`;

export function fmtDuration(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

export function isTyping(e: KeyboardEvent): boolean {
  const el = e.target as HTMLElement | null;
  if (!el) return false;
  return el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT" || el.isContentEditable;
}
