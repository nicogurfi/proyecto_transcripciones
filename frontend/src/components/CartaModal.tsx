import { useEffect, useState } from "react";
import type { CallState } from "../state/useCall";
import { CATEGORIA_LABEL } from "../util";

interface Props {
  call: CallState;
  onClose: () => void;
}

export function CartaModal({ call, onClose }: Props) {
  const [notas, setNotas] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const a = call.analisis;
  const carta = call.carta;

  const v = call.valor;
  const faltan: string[] = [];
  if (!v("ubicacion.calle")) faltan.push("calle");
  if (!(v("ubicacion.altura") || v("ubicacion.interseccion") || v("ubicacion.entre_calles"))) faltan.push("altura o esquina");
  if (!v("suceso.categoria")) faltan.push("tipo de hecho");
  if (!v("prioridad")) faltan.push("prioridad");
  const pendCrit = call.pendientes.filter((p) => p.critica);

  const send = async () => {
    setSending(true);
    setError(null);
    try {
      await call.derivar(notas);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && !carta && !sending) {
        e.preventDefault();
        void send();
      }
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  });

  const direccion = [
    [v("ubicacion.calle"), v("ubicacion.altura")].filter(Boolean).join(" "),
    v("ubicacion.piso_depto"),
    v("ubicacion.interseccion") && `esq. ${v("ubicacion.interseccion")}`,
    v("ubicacion.entre_calles") && `entre ${v("ubicacion.entre_calles")}`,
  ].filter(Boolean).join(", ");

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" role="dialog" aria-label="Carta de llamada" onMouseDown={(e) => e.stopPropagation()}>
        {carta ? (
          <>
            <header className="modal-h ok">
              <h2>Carta {carta.numero} derivada a despacho</h2>
            </header>
            <pre className="carta-text">{carta.texto_plano}</pre>
            <footer className="modal-f">
              <span className="muted">{carta.correcciones_operador} correcciones del operador registradas para mejora del modelo</span>
              <button type="button" className="primary" onClick={() => { call.reset(); onClose(); }}>
                Nueva llamada
              </button>
            </footer>
          </>
        ) : (
          <>
            <header className="modal-h">
              <h2>Carta de llamada · revisión final</h2>
              <span className={`prio-chip ${(v("prioridad") ?? "").toLowerCase()}`}>{v("prioridad") ?? "P?"}</span>
            </header>
            <dl className="carta-preview">
              <dt>Dirección</dt>
              <dd>
                {direccion || "—"}{" "}
                <span className={`geo-badge ${a?.geo.estado ?? "sin_datos"}`}>{a?.geo.estado === "validada" ? "validada" : "sin validar"}</span>
              </dd>
              <dt>Tipo</dt>
              <dd>{CATEGORIA_LABEL[v("suceso.categoria") ?? ""] ?? "—"} {v("suceso.subcategoria") ? `/ ${v("suceso.subcategoria")}` : ""}</dd>
              <dt>Relato</dt>
              <dd>{v("suceso.descripcion") ?? "—"}</dd>
              <dt>Personas</dt>
              <dd>{[v("personas.cantidad"), v("personas.victimas"), v("personas.estado")].filter(Boolean).join(" · ") || "—"}</dd>
              <dt>Riesgos</dt>
              <dd>{v("riesgos") ?? "—"}</dd>
              <dt>Pre-arribo</dt>
              <dd>{call.instrMarks.size} instrucciones transmitidas</dd>
            </dl>
            {(faltan.length > 0 || pendCrit.length > 0) && (
              <div className="warn-box">
                {faltan.length > 0 && <p>Falta: {faltan.join(", ")}. Se puede derivar igual (queda marcada como incompleta).</p>}
                {pendCrit.length > 0 && <p>{pendCrit.length} preguntas críticas sin realizar (F1).</p>}
              </div>
            )}
            <textarea placeholder="Notas para el despachador (opcional)" value={notas} onChange={(e) => setNotas(e.target.value)} rows={2} />
            {error && <p className="error">{error}</p>}
            <footer className="modal-f">
              <button type="button" className="ghost" onClick={onClose}>Volver (Esc)</button>
              <button type="button" className="primary danger" disabled={sending || !a} onClick={() => void send()}>
                {sending ? "Derivando…" : "Derivar a despacho (Ctrl+Enter)"}
              </button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
