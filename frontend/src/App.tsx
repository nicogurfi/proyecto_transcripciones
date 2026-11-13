import { useCallback, useEffect, useState } from "react";
import { api } from "./api/client";
import type { Health } from "./api/schemas";
import { useCall } from "./state/useCall";
import { fmtDuration } from "./util";
import { Cartas } from "./views/Cartas";
import { Operacion } from "./views/Operacion";
import { Simulacro } from "./views/Simulacro";

type View = "operacion" | "simulacro" | "cartas";

const SHORTCUTS: [string, string][] = [
  ["F1 / Alt+1", "Preguntas pendientes del protocolo"],
  ["F2 / Alt+2", "Instrucciones de pre-arribo para leer al llamante"],
  ["F3 / Alt+3", "Casos similares y recursos (referencia para despacho)"],
  ["F4 / Alt+4", "Posibles inconsistencias en el relato o la transcripción"],
  ["1 – 9", "Con un panel abierto: marcar ítem como hecho"],
  ["Ctrl+Enter", "Revisar y derivar la carta de llamada"],
  ["Alt+L", "Cargar caso / pegar transcripción"],
  ["Alt+N", "Escribir un nuevo turno de diálogo"],
  ["Tab", "En el campo de turno vacío: cambiar hablante"],
  ["Esc", "Cerrar panel o ventana"],
  ["?", "Esta ayuda"],
];

export function App() {
  const call = useCall();
  const [view, setView] = useState<View>("operacion");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);
  const [help, setHelp] = useState(false);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthError(true));
    const h = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(h);
  }, []);

  useEffect(() => {
    if (!help) return;
    const h = (e: KeyboardEvent) => (e.key === "Escape" || e.key === "?") && setHelp(false);
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [help]);

  const showHelp = useCallback(() => setHelp(true), []);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" aria-hidden>✚</span>
          <span>Copiloto de Sala</span>
        </div>
        <nav className="tabs">
          {(["operacion", "simulacro", "cartas"] as View[]).map((v) => (
            <button key={v} type="button" className={view === v ? "on" : ""} onClick={() => setView(v)}>
              {v === "operacion" ? "Operación" : v === "simulacro" ? "Simulacro" : "Cartas"}
            </button>
          ))}
        </nav>
        {view === "operacion" && (
          <div className="call-info">
            <span className="call-title">{call.meta.titulo}</span>
            <span className="timer">{call.startedAt ? fmtDuration(now - call.startedAt) : "--:--"}</span>
            <button type="button" className="ghost" onClick={call.reset} title="Cortar y empezar una nueva llamada">
              Nueva
            </button>
          </div>
        )}
        <div className="provider">
          {healthError && <span className="badge bad">backend no disponible</span>}
          {health && (
            <span className={`badge ${health.mock ? "mock" : "real"}`} title={`Embeddings: ${health.embeddings}`}>
              {health.mock ? "Modo simulado" : `${health.proveedor} · ${health.modelo}`}
            </span>
          )}
          <button type="button" className="ghost help-btn" onClick={showHelp} title="Atajos (?)">?</button>
        </div>
      </header>
      <main>
        {view === "operacion" && <Operacion call={call} showHelp={showHelp} />}
        {view === "simulacro" && <Simulacro />}
        {view === "cartas" && <Cartas />}
      </main>
      {help && (
        <div className="modal-backdrop" onMouseDown={() => setHelp(false)}>
          <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
            <header className="modal-h"><h2>Atajos de teclado</h2></header>
            <table className="help-table">
              <tbody>
                {SHORTCUTS.map(([k, d]) => (
                  <tr key={k}><td><kbd>{k}</kbd></td><td>{d}</td></tr>
                ))}
              </tbody>
            </table>
            <p className="muted">
              Las sugerencias solo aparecen cuando las pedís. Lo único que se muestra sin pedirlo son las alertas críticas de
              seguridad (barra roja).
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
