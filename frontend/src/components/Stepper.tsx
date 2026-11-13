import type { PasoProtocolo } from "../api/schemas";

interface Props {
  pasos: PasoProtocolo[];
  sugerido: number;
  overrides: Partial<Record<number, PasoProtocolo["estado"]>>;
}

const DEFAULT: PasoProtocolo[] = [
  { numero: 1, nombre: "Ubicación", objetivo: "¿Dónde es la emergencia?", estado: "pendiente", faltantes: [] },
  { numero: 2, nombre: "Qué pasó", objetivo: "", estado: "pendiente", faltantes: [] },
  { numero: 3, nombre: "Personas y riesgos", objetivo: "", estado: "pendiente", faltantes: [] },
  { numero: 4, nombre: "Interrogatorio", objetivo: "", estado: "pendiente", faltantes: [] },
  { numero: 5, nombre: "Pre-arribo", objetivo: "", estado: "pendiente", faltantes: [] },
  { numero: 6, nombre: "Carta de llamada", objetivo: "", estado: "pendiente", faltantes: [] },
];

export function Stepper({ pasos, sugerido, overrides }: Props) {
  const list = pasos.length ? pasos : DEFAULT;
  const actual = list.find((p) => p.numero === sugerido) ?? list[0];
  return (
    <nav className="stepper" aria-label="Protocolo">
      <ol>
        {list.map((p) => {
          const estado = overrides[p.numero] ?? p.estado;
          return (
            <li
              key={p.numero}
              className={`step ${estado} ${p.numero === sugerido ? "current" : ""}`}
              title={p.faltantes.length ? `Falta: ${p.faltantes.join(" · ")}` : p.objetivo}
            >
              <span className="n">{estado === "completo" ? "✓" : p.numero}</span>
              <span className="name">{p.nombre}</span>
            </li>
          );
        })}
      </ol>
      {actual && (
        <div className="step-goal">
          <strong>Paso {actual.numero}:</strong> {actual.objetivo}
          {actual.faltantes.length > 0 && <span className="falta"> · Falta: {actual.faltantes.slice(0, 3).join(" · ")}</span>}
        </div>
      )}
    </nav>
  );
}
