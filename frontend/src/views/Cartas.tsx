import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Carta } from "../api/schemas";
import { CATEGORIA_LABEL, LABELS } from "../util";

export function Cartas() {
  const [cartas, setCartas] = useState<Carta[]>([]);
  const [corr, setCorr] = useState<{ campo: string; n: number; conf: number | null }[]>([]);
  const [sel, setSel] = useState<Carta | null>(null);

  useEffect(() => {
    api.cartas().then(setCartas).catch(() => undefined);
    api.correcciones().then(setCorr).catch(() => undefined);
  }, []);

  return (
    <div className="cartas-view">
      <section className="card">
        <header className="card-h"><span>Cartas derivadas ({cartas.length})</span></header>
        {cartas.length === 0 && <p className="muted pad">Todavía no se derivó ninguna carta.</p>}
        <table className="cartas-table">
          <tbody>
            {cartas.map((c) => (
              <tr key={c.numero} onClick={() => setSel(c)} className={sel?.numero === c.numero ? "sel" : ""}>
                <td><span className={`prio-chip ${(c.prioridad ?? "").toLowerCase()}`}>{c.prioridad ?? "?"}</span></td>
                <td className="mono">{c.numero}</td>
                <td>{CATEGORIA_LABEL[c.categoria ?? ""] ?? "—"}</td>
                <td>{c.direccion}</td>
                <td>{c.completa ? "" : <span className="tag warn">incompleta</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {sel && <pre className="carta-text">{sel.texto_plano}</pre>}
      </section>
      <section className="card">
        <header className="card-h"><span>Correcciones del operador (dataset de mejora)</span></header>
        <p className="muted pad">
          Cada vez que el operador corrige un dato sugerido se guarda el par (sugerido → final). Es la base para recalibrar
          la confianza y re-entrenar el extractor.
        </p>
        <table className="cartas-table">
          <thead><tr><th>Campo</th><th>Correcciones</th><th>Confianza media al sugerir</th></tr></thead>
          <tbody>
            {corr.map((c) => (
              <tr key={c.campo}>
                <td>{LABELS[c.campo as keyof typeof LABELS] ?? c.campo}</td>
                <td>{c.n}</td>
                <td>{c.conf != null ? `${Math.round(c.conf * 100)}%` : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
