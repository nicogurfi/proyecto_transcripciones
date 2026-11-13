import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { CasoResumen, Turn } from "../api/schemas";
import type { CallMeta } from "../state/useCall";
import { CATEGORIA_LABEL } from "../util";

interface Props {
  onClose: () => void;
  onLoad: (meta: CallMeta, turns: Turn[], live: boolean) => void;
}

export function LoadModal({ onClose, onLoad }: Props) {
  const [casos, setCasos] = useState<{ demo: CasoResumen[]; dataset: CasoResumen[] } | null>(null);
  const [live, setLive] = useState(true);
  const [texto, setTexto] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.casos().then(setCasos).catch((e: unknown) => setError(String(e)));
    const h = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onClose]);

  const pick = async (id: string) => {
    try {
      const c = await api.caso(id);
      onLoad({ casoId: c.id, titulo: c.titulo, timestamp: c.timestamp, origen: c.origen }, c.turnos, live);
      onClose();
    } catch (e) {
      setError(String(e));
    }
  };

  const pegar = async () => {
    if (!texto.trim()) return;
    const { turnos } = await api.parsear(texto);
    onLoad({ casoId: null, titulo: "Transcripción pegada", timestamp: new Date().toISOString().slice(0, 19), origen: "TELEFONIA_911" }, turnos, live);
    onClose();
  };

  const row = (c: CasoResumen) => (
    <button key={c.id} type="button" className="case-row" onClick={() => void pick(c.id)}>
      <span className="cid">{c.id.replace("SFX-REC-2026-", "#")}</span>
      <span className="ctitle">{c.titulo}</span>
      {c.categoria && <span className="muted">{CATEGORIA_LABEL[c.categoria]}</span>}
      {c.prioridad && <span className={`prio-chip ${c.prioridad.toLowerCase()}`}>{c.prioridad}</span>}
    </button>
  );

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal wide" role="dialog" aria-label="Cargar llamada" onMouseDown={(e) => e.stopPropagation()}>
        <header className="modal-h">
          <h2>Cargar llamada</h2>
          <label className="switch">
            <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
            Simular en vivo (oración por oración)
          </label>
        </header>
        {error && <p className="error">{error}</p>}
        <div className="load-grid">
          <div>
            <h3>Casos de demostración</h3>
            <div className="case-list">{casos?.demo.map(row)}</div>
            <h3>Pegar desgrabación</h3>
            <textarea
              rows={6}
              value={texto}
              placeholder={"Operador: 911, ¿cuál es su emergencia?\nLlamante: ..."}
              onChange={(e) => setTexto(e.target.value)}
            />
            <button type="button" className="primary" onClick={() => void pegar()} disabled={!texto.trim()}>
              Analizar transcripción
            </button>
          </div>
          <div>
            <h3>Dataset provisto ({casos?.dataset.length ?? 0})</h3>
            <div className="case-list scroll">{casos?.dataset.map(row)}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
