import { useEffect } from "react";
import type { Evidence } from "../api/schemas";
import type { CallState } from "../state/useCall";
import { CATEGORIA_LABEL, isTyping, pct } from "../util";

export type PanelId = "preguntas" | "instrucciones" | "similares" | "inconsistencias";

export const PANELS: { id: PanelId; key: string; alt: string; title: string; short: string }[] = [
  { id: "preguntas", key: "F1", alt: "Alt+1", title: "Preguntas pendientes", short: "Preguntas" },
  { id: "instrucciones", key: "F2", alt: "Alt+2", title: "Instrucciones de pre-arribo", short: "Pre-arribo" },
  { id: "similares", key: "F3", alt: "Alt+3", title: "Casos similares y recursos", short: "Similares" },
  { id: "inconsistencias", key: "F4", alt: "Alt+4", title: "Posibles inconsistencias", short: "Inconsistencias" },
];

interface Props {
  panel: PanelId;
  call: CallState;
  onClose: () => void;
  onHover: (ev: Evidence[]) => void;
}

function useDigitToggle(enabled: boolean, ids: string[], toggle: (id: string) => void) {
  useEffect(() => {
    if (!enabled) return;
    const h = (e: KeyboardEvent) => {
      if (isTyping(e) || e.altKey || e.ctrlKey || e.metaKey) return;
      const n = Number.parseInt(e.key, 10);
      const id = ids[n - 1];
      if (n >= 1 && n <= 9 && id) {
        e.preventDefault();
        toggle(id);
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [enabled, ids, toggle]);
}

export function SidePanel({ panel, call, onClose, onHover }: Props) {
  const a = call.analisis;
  const meta = PANELS.find((p) => p.id === panel)!;

  const pendientes = [...call.pendientes].sort((x, y) => Number(y.critica) - Number(x.critica));
  const sugeridas = (a?.checklist ?? []).filter((c) => c.estado === "respondida_sugerida" && !call.checkMarks[c.id]);
  const confirmadas = (a?.checklist ?? []).filter((c) => call.checkMarks[c.id]);
  const instrucciones = a?.instrucciones ?? [];

  useDigitToggle(panel === "preguntas", pendientes.map((p) => p.id), call.toggleCheck);
  useDigitToggle(panel === "instrucciones", instrucciones.map((i) => i.id), call.toggleInstr);

  return (
    <aside className="side-panel" role="dialog" aria-label={meta.title}>
      <header>
        <div>
          <span className="kbd-chip">{meta.key}</span>
          <h2>{meta.title}</h2>
        </div>
        <button type="button" className="ghost" onClick={onClose} title="Cerrar (Esc)">
          ✕
        </button>
      </header>
      <p className="panel-note">Sugerencias del copiloto · la decisión es del operador. El % es la confianza estimada a partir de la evidencia.</p>

      {!a && <p className="muted">Sin análisis todavía.</p>}

      {a && panel === "preguntas" && (
        <div className="panel-body">
          {pendientes.length === 0 && <p className="ok-msg">No quedan preguntas pendientes.</p>}
          <ol className="items">
            {pendientes.map((c, i) => (
              <li key={c.id} className={c.critica ? "critical" : ""}>
                <button type="button" className="num" onClick={() => call.toggleCheck(c.id)} title="Marcar como preguntada">
                  {i < 9 ? i + 1 : "·"}
                </button>
                <div>
                  <p>{c.pregunta}</p>
                  <span className="tag">{c.critica ? "crítica" : c.origen}</span>
                </div>
              </li>
            ))}
          </ol>
          {sugeridas.length > 0 && (
            <details open>
              <summary>Ya respondidas en el relato ({sugeridas.length}) · confirmar</summary>
              <ul className="items answered">
                {sugeridas.map((c) => (
                  <li key={c.id} onMouseEnter={() => c.evidencia && onHover([c.evidencia])} onMouseLeave={() => onHover([])}>
                    <div>
                      <p>{c.pregunta}</p>
                      {c.evidencia && <q>{c.evidencia.text}</q>}
                      <span className="tag">{pct(c.confianza)}</span>
                    </div>
                    <div className="actions">
                      <button type="button" onClick={() => call.toggleCheck(c.id, "confirmada")}>Confirmar</button>
                    </div>
                  </li>
                ))}
              </ul>
            </details>
          )}
          {confirmadas.length > 0 && (
            <details>
              <summary>Confirmadas por el operador ({confirmadas.length})</summary>
              <ul className="items done">
                {confirmadas.map((c) => (
                  <li key={c.id}>
                    <p>{c.pregunta}</p>
                    <button type="button" className="ghost" onClick={() => call.toggleCheck(c.id, call.checkMarks[c.id])}>deshacer</button>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <p className="kbd-hint">Teclas <kbd>1</kbd>–<kbd>9</kbd>: marcar pregunta como realizada</p>
        </div>
      )}

      {a && panel === "instrucciones" && (
        <div className="panel-body">
          <ol className="items">
            {instrucciones.map((ins, i) => (
              <li key={ins.id} className={`${ins.critica ? "critical" : ""} ${call.instrMarks.has(ins.id) ? "is-done" : ""}`}>
                <button type="button" className="num" onClick={() => call.toggleInstr(ins.id)} title="Marcar como transmitida">
                  {call.instrMarks.has(ins.id) ? "✓" : i < 9 ? i + 1 : "·"}
                </button>
                <div>
                  <p className="read-aloud">{ins.texto}</p>
                  <span className="tag">{ins.fuente} · {pct(ins.confianza)}</span>
                </div>
              </li>
            ))}
          </ol>
          <p className="kbd-hint">Leer en voz alta al llamante. <kbd>1</kbd>–<kbd>9</kbd>: marcar como transmitida</p>
        </div>
      )}

      {a && panel === "similares" && (
        <div className="panel-body">
          <p className="panel-note warn">Los recursos son una referencia para el despachador CAD: el operador no decide el despacho.</p>
          <h3 className="panel-sub">Recursos sugeridos</h3>
          <ul className="items">
            {a.recursos_sugeridos.map((r) => (
              <li key={r.texto}>
                <div>
                  <p>{r.texto}</p>
                  <span className="tag">{r.fuente === "regla" ? "regla" : r.fuente} · {r.motivo}</span>
                </div>
              </li>
            ))}
          </ul>
          <h3 className="panel-sub">Casos parecidos del catálogo</h3>
          {a.casos_similares.map((c) => (
            <article key={c.id} className="similar">
              <header>
                <strong>{c.subcategoria}</strong>
                <span className={`prio-chip ${c.prioridad.toLowerCase()}`}>{c.prioridad}</span>
              </header>
              <div className="sim-bar"><span style={{ width: pct(Math.max(0, c.similitud)) }} /></div>
              <p className="muted">{c.id} · {CATEGORIA_LABEL[c.categoria] ?? c.categoria} · similitud {pct(c.similitud)}</p>
              {c.similitud < 0.75 && <p className="tag warn">Parecido bajo: solo como referencia, no se usan sus recursos.</p>}
              <p className="muted">{c.nota_despacho}</p>
            </article>
          ))}
        </div>
      )}

      {a && panel === "inconsistencias" && (
        <div className="panel-body">
          {call.inconsistencias.length === 0 && <p className="ok-msg">No se detectaron inconsistencias.</p>}
          <ul className="items">
            {call.inconsistencias.map((inc) => (
              <li
                key={inc.id}
                className={`inc ${inc.severidad}`}
                onMouseEnter={() => inc.evidencia && onHover([inc.evidencia])}
                onMouseLeave={() => onHover([])}
              >
                <div>
                  <span className={`sev ${inc.severidad}`}>{inc.severidad}</span>
                  <p>{inc.mensaje}</p>
                  {inc.evidencia && <q>{inc.evidencia.text}</q>}
                  {inc.sugerencia && <p className="sug">→ {inc.sugerencia}</p>}
                </div>
                <div className="actions">
                  <button type="button" className="ghost" onClick={() => call.dismiss(inc.id)}>descartar</button>
                </div>
              </li>
            ))}
          </ul>
          {a.notas.length > 0 && (
            <details>
              <summary>Notas del modelo ({a.notas.length})</summary>
              <ul className="notes">{a.notas.map((n) => <li key={n}>{n}</li>)}</ul>
            </details>
          )}
        </div>
      )}
    </aside>
  );
}
