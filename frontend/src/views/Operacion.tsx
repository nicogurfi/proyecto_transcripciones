import { useCallback, useEffect, useRef, useState } from "react";
import type { Evidence, FieldKey, PasoProtocolo } from "../api/schemas";
import { CartaModal } from "../components/CartaModal";
import { FichaView } from "../components/FichaView";
import { LoadModal } from "../components/LoadModal";
import { PANELS, SidePanel, type PanelId } from "../components/Panels";
import { DEFAULT_PASOS, Stepper, type EstadoPaso } from "../components/Stepper";
import { Transcript } from "../components/Transcript";
import type { CallState } from "../state/useCall";
import { isTyping } from "../util";

interface Props {
  call: CallState;
  showHelp: () => void;
}

function pasosDesdeFicha(call: CallState): Partial<Record<number, Pick<PasoProtocolo, "estado" | "faltantes">>> {
  const v = (k: FieldKey) => Boolean(call.valor(k));
  const estado = (falt: number, total: number): EstadoPaso => (falt === 0 ? "completo" : falt < total ? "parcial" : "pendiente");
  const f1: string[] = [];
  if (!v("ubicacion.calle")) f1.push("Calle");
  if (!(v("ubicacion.altura") || v("ubicacion.interseccion") || v("ubicacion.entre_calles"))) f1.push("Altura o esquina");
  if (v("ubicacion.calle") && call.geo?.estado !== "validada") f1.push("Dirección no validada en callejero");
  const e1: EstadoPaso = f1.length === 0 ? "completo" : v("ubicacion.calle") ? "parcial" : "pendiente";
  const f2 = (
    [["suceso.categoria", "Tipo de hecho"], ["suceso.descripcion", "Descripción"], ["prioridad", "Prioridad"]] as [FieldKey, string][]
  ).filter(([k]) => !v(k)).map(([, n]) => n);
  const f3: string[] = [];
  if (!(v("personas.cantidad") || v("personas.victimas"))) f3.push("Personas involucradas");
  if (!v("personas.estado")) f3.push("Estado de las personas");
  const opcional = v("riesgos") ? [] : ["Riesgos en el lugar (si los hay)"];
  return {
    1: { estado: e1, faltantes: f1 },
    2: { estado: estado(f2.length, 3), faltantes: f2 },
    3: { estado: estado(f3.length, 2), faltantes: [...f3, ...opcional] },
  };
}

export function Operacion({ call, showHelp }: Props) {
  const [panel, setPanel] = useState<PanelId | null>(null);
  const [hover, setHover] = useState<Evidence[]>([]);
  const [loadOpen, setLoadOpen] = useState(false);
  const [cartaOpen, setCartaOpen] = useState(false);
  // Alertas críticas: son reglas con margen de error, se despliegan a pedido (Alt+5 / Alt+A)
  const [alertsOpen, setAlertsOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const a = call.analisis;
  // Paso elegido a mano (null = automático: el primer paso sin tildar)
  const [manualStep, setManualStep] = useState<number | null>(null);
  // Tildes manuales del operador: pisan el estado calculado por el copiloto
  const [manualTicks, setManualTicks] = useState<Partial<Record<number, boolean>>>({});
  const [scrollKey, setScrollKey] = useState(0);

  // Nueva llamada => vuelve al modo automático
  useEffect(() => {
    setManualStep(null);
    setManualTicks({});
    setAlertsOpen(false);
  }, [call.startedAt]);

  const pasoOverrides: Record<number, EstadoPaso> = {};
  if (a) {
    const crit = a.instrucciones.filter((i) => i.critica);
    if (a.instrucciones.length) {
      const leidas = a.instrucciones.filter((i) => call.instrMarks.has(i.id)).length;
      pasoOverrides[5] = crit.every((i) => call.instrMarks.has(i.id)) && leidas > 0 ? "completo" : leidas > 0 ? "parcial" : "pendiente";
    }
    const critPend = call.pendientes.filter((p) => p.critica).length;
    const critTotal = a.checklist.filter((c) => c.critica).length;
    pasoOverrides[4] = critPend === 0 && critTotal > 0 ? "completo" : critPend < critTotal ? "parcial" : "pendiente";
    if (call.carta) pasoOverrides[6] = "completo";
  }
  // Pasos 1-3 con los valores FINALES (correcciones del operador > sugerencia del copiloto),
  // así el protocolo reacciona tanto a la transcripción como a las ediciones manuales.
  const base13 = pasosDesdeFicha(call);
  const pasos: PasoProtocolo[] = (a?.pasos.length ? a.pasos : DEFAULT_PASOS).map((p0) => {
    const p = base13[p0.numero] && (a || call.turns.length) ? { ...p0, ...base13[p0.numero] } : p0;
    const tick = manualTicks[p.numero];
    const calc = pasoOverrides[p.numero] ?? p.estado;
    const estado: EstadoPaso = tick === true ? "completo" : tick === false && calc === "completo" ? "parcial" : calc;
    return { ...p, estado };
  });
  const autoStep = pasos.find((p) => p.estado !== "completo")?.numero ?? 6;
  const selected = manualStep ?? autoStep;
  const pasosKey = pasos.map((p) => p.estado).join();

  const goTo = useCallback((n: number) => {
    const step = Math.min(6, Math.max(1, n));
    setManualStep(step);
    setScrollKey((k) => k + 1);
    // Cambiar de paso nunca abre paneles: las sugerencias solo aparecen con su atajo (F1–F4).
  }, []);

  const toggleTick = useCallback(
    (n: number) => {
      setManualTicks((t) => {
        const next = { ...t };
        if (next[n] !== undefined) delete next[n];
        else next[n] = (pasos.find((p) => p.numero === n)?.estado ?? "pendiente") !== "completo";
        return next;
      });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pasosKey],
  );

  const backToAuto = useCallback(() => {
    setManualStep(null);
  }, []);

  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (loadOpen || cartaOpen) return;
      const fIdx = ["F1", "F2", "F3", "F4"].indexOf(e.key);
      const altIdx = e.altKey && !e.shiftKey ? ["Digit1", "Digit2", "Digit3", "Digit4"].indexOf(e.code) : -1;
      const idx = fIdx >= 0 ? fIdx : altIdx;
      if (idx >= 0) {
        e.preventDefault();
        const id = PANELS[idx]!.id;
        setPanel((p) => (p === id ? null : id));
        return;
      }
      if (e.key === "Escape") {
        setPanel(null);
        return;
      }
      // ---- navegación libre entre pasos
      if ((e.altKey && e.key === "ArrowDown") || (e.altKey && e.key === "ArrowRight") || e.key === "PageDown") {
        e.preventDefault();
        goTo(selected + 1);
        return;
      }
      if ((e.altKey && e.key === "ArrowUp") || (e.altKey && e.key === "ArrowLeft") || e.key === "PageUp") {
        e.preventDefault();
        goTo(selected - 1);
        return;
      }
      const jump = e.altKey && e.shiftKey ? ["Digit1", "Digit2", "Digit3", "Digit4", "Digit5", "Digit6"].indexOf(e.code) : -1;
      if (jump >= 0) {
        e.preventDefault();
        goTo(jump + 1);
        return;
      }
      if (e.altKey && e.code === "KeyT") {
        e.preventDefault();
        toggleTick(selected);
        return;
      }
      if (e.altKey && e.code === "Digit0") {
        e.preventDefault();
        backToAuto();
        return;
      }
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        if (a) setCartaOpen(true);
        return;
      }
      if (e.altKey && !e.shiftKey && (e.code === "Digit5" || e.code === "KeyA")) {
        e.preventDefault();
        setAlertsOpen((o) => !o);
        return;
      }
      if (e.altKey && e.code === "KeyL") {
        e.preventDefault();
        setLoadOpen(true);
        return;
      }
      if (e.altKey && e.code === "KeyN") {
        e.preventDefault();
        inputRef.current?.focus();
        return;
      }
      if (!isTyping(e) && e.key === "?") showHelp();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [loadOpen, cartaOpen, a, showHelp, selected, goTo, toggleTick, backToAuto]);

  const counts: Record<PanelId, number> = {
    preguntas: call.pendientes.length,
    instrucciones: a ? a.instrucciones.filter((i) => !call.instrMarks.has(i.id)).length : 0,
    similares: a?.casos_similares.length ?? 0,
    inconsistencias: call.inconsistencias.length,
  };
  const altaInc = call.inconsistencias.some((i) => i.severidad === "alta");

  return (
    <div className="operacion">
      <Stepper
        pasos={pasos}
        manualTicks={manualTicks}
        selected={selected}
        auto={manualStep === null}
        onSelect={goTo}
        onToggleTick={toggleTick}
        onAuto={backToAuto}
      />
      {alertsOpen && a && (
        <div className="critical-bar" role="alert">
          {a.alertas_criticas.length === 0 && <span className="none">Sin alertas críticas para este relato.</span>}
          {a.alertas_criticas.map((al) => (
            <span
              key={al.id}
              title={`${al.motivo}${al.evidencia ? ` · disparada por: "${al.evidencia.text}"` : ""}`}
              onMouseEnter={() => al.evidencia && setHover([al.evidencia])}
              onMouseLeave={() => setHover([])}
            >
              ⚠ {al.texto}
              {al.evidencia && <q> “{al.evidencia.text}”</q>}
            </span>
          ))}
          <small className="disclaimer">Regla automática por palabras clave: puede dispararse de más (p. ej. con negaciones). Confirmar con el llamante.</small>
        </div>
      )}
      <div className="workspace">
        <Transcript turns={call.turns} highlight={hover} live={call.live} onAddTurn={call.addTurn} inputRef={inputRef} />
        <div className="right">
          <FichaView call={call} onHover={setHover} activeStep={selected} scrollKey={scrollKey} onSelectStep={goTo} />
          {panel && <SidePanel panel={panel} call={call} onClose={() => setPanel(null)} onHover={setHover} />}
        </div>
      </div>
      <footer className="action-bar">
        <div className="chips">
          {PANELS.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`chip ${panel === p.id ? "on" : ""} ${p.id === "inconsistencias" && altaInc ? "alert" : ""}`}
              onClick={() => setPanel((cur) => (cur === p.id ? null : p.id))}
              title={`${p.title} (${p.key} / ${p.alt})`}
            >
              <kbd>{p.key}</kbd> {p.short} <b>{counts[p.id]}</b>
            </button>
          ))}
          <button
            type="button"
            className={`chip ${alertsOpen ? "on" : ""} ${a && a.alertas_criticas.length > 0 ? "alert" : ""}`}
            onClick={() => setAlertsOpen((o) => !o)}
            title="Alertas críticas de seguridad (Alt+5 / Alt+A)"
          >
            <kbd>Alt+5</kbd> Alertas <b>{a?.alertas_criticas.length ?? 0}</b>
          </button>
          <button type="button" className="chip" onClick={() => setLoadOpen(true)} title="Cargar caso (Alt+L)">
            <kbd>Alt+L</kbd> Cargar
          </button>
        </div>
        <div className="status">
          {call.analyzing && <span className="spinner" />}
          {a && (
            <span className="muted">
              {a.fase === "rapida" ? "reglas" : a.proveedor} · {a.latencia_ms} ms
            </span>
          )}
          {call.error && <span className="error">{call.error}</span>}
        </div>
        <button type="button" className={`primary danger ${selected === 6 ? "pulse" : ""}`} disabled={!a} onClick={() => setCartaOpen(true)}>
          Derivar carta <kbd>Ctrl+Enter</kbd>
        </button>
      </footer>
      {loadOpen && <LoadModal onClose={() => setLoadOpen(false)} onLoad={call.load} />}
      {cartaOpen && <CartaModal call={call} onClose={() => setCartaOpen(false)} />}
    </div>
  );
}
