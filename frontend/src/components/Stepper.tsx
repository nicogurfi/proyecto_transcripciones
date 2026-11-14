import type { PasoProtocolo } from "../api/schemas";

export type EstadoPaso = PasoProtocolo["estado"];

export const DEFAULT_PASOS: PasoProtocolo[] = [
  { numero: 1, nombre: "Ubicación", objetivo: "¿Dónde es la emergencia? Calle, altura y entre calles.", estado: "pendiente", faltantes: [] },
  { numero: 2, nombre: "Qué pasó", objetivo: "Naturaleza del hecho y prioridad sugerida.", estado: "pendiente", faltantes: [] },
  { numero: 3, nombre: "Personas y riesgos", objetivo: "Quiénes están afectados, cómo están y qué riesgos hay.", estado: "pendiente", faltantes: [] },
  { numero: 4, nombre: "Interrogatorio", objetivo: "Preguntas clave del protocolo según el tipo de hecho.", estado: "pendiente", faltantes: [] },
  { numero: 5, nombre: "Pre-arribo", objetivo: "Leer al llamante las instrucciones de seguridad.", estado: "pendiente", faltantes: [] },
  { numero: 6, nombre: "Carta de llamada", objetivo: "Validar la ficha y derivar a despacho.", estado: "pendiente", faltantes: [] },
];

interface Props {
  pasos: PasoProtocolo[]; // con el estado efectivo ya resuelto (auto + overrides + tildes manuales)
  manualTicks: Partial<Record<number, boolean>>;
  selected: number;
  auto: boolean;
  onSelect: (n: number) => void;
  onToggleTick: (n: number) => void;
  onAuto: () => void;
}

export function Stepper({ pasos, manualTicks, selected, auto, onSelect, onToggleTick, onAuto }: Props) {
  const actual = pasos.find((p) => p.numero === selected) ?? pasos[0];
  return (
    <nav className="stepper" aria-label="Protocolo">
      <ol>
        {pasos.map((p) => (
          <li
            key={p.numero}
            className={`step ${p.estado} ${p.numero === selected ? "current" : ""}`}
            title={p.faltantes.length ? `Falta: ${p.faltantes.join(" · ")}` : p.objetivo}
          >
            <button
              type="button"
              className="n"
              aria-label={p.estado === "completo" ? `Destildar paso ${p.numero}` : `Tildar paso ${p.numero}`}
              title={`${p.estado === "completo" ? "Destildar" : "Tildar"} (Alt+T sobre el paso actual)`}
              onClick={() => onToggleTick(p.numero)}
            >
              {p.estado === "completo" ? "✓" : p.numero}
              {manualTicks[p.numero] !== undefined && <i className="manual-dot" />}
            </button>
            <button type="button" className="name" onClick={() => onSelect(p.numero)} title={`Ir al paso (Alt+Shift+${p.numero})`}>
              {p.nombre}
            </button>
          </li>
        ))}
      </ol>
      {actual && (
        <div className="step-goal">
          <span className={`mode ${auto ? "auto" : "manual"}`}>
            {auto ? "AUTO" : "MANUAL"}
          </span>
          <strong>Paso {actual.numero}:</strong> {actual.objetivo}
          {actual.faltantes.length > 0 && actual.estado !== "completo" && (
            <span className="falta"> · Falta: {actual.faltantes.slice(0, 3).join(" · ")}</span>
          )}
          {actual.numero === 4 && <span className="muted"> · <kbd>F1</kbd> ver preguntas</span>}
          {actual.numero === 5 && <span className="muted"> · <kbd>F2</kbd> ver instrucciones</span>}
          {actual.numero === 6 && <span className="muted"> · <kbd>Ctrl+Enter</kbd> revisar y derivar</span>}
          <span className="step-keys">
            <kbd>Alt+↑↓</kbd> moverse · <kbd>Alt+T</kbd> tildar
            {!auto && (
              <>
                {" · "}
                <button type="button" className="link" onClick={onAuto}>
                  <kbd>Alt+0</kbd> volver a automático
                </button>
              </>
            )}
          </span>
        </div>
      )}
    </nav>
  );
}
