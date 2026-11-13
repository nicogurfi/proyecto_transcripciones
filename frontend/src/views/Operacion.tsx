import { useCallback, useEffect, useRef, useState } from "react";
import type { Evidence, PasoProtocolo } from "../api/schemas";
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

export function Operacion({ call, showHelp }: Props) {
  const [panel, setPanel] = useState<PanelId | null>(null);
  const [hover, setHover] = useState<Evidence[]>([]);
  const [loadOpen, setLoadOpen] = useState(false);
  const [cartaOpen, setCartaOpen] = useState(false);
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
  const pasos: PasoProtocolo[] = (a?.pasos.length ? a.pasos : DEFAULT_PASOS).map((p) => {
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
    // Ir a un paso es pedir su ayuda: 4 abre el interrogatorio, 5 las instrucciones.
    setPanel(step === 4 ? "preguntas" : step === 5 ? "instrucciones" : null);
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
    setPanel(null);
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
      {a && a.alertas_criticas.length > 0 && (
        <div className="critical-bar" role="alert">
          {a.alertas_criticas.map((al) => (
            <span key={al.id} title={al.motivo} onMouseEnter={() => al.evidencia && setHover([al.evidencia])} onMouseLeave={() => setHover([])}>
              ⚠ {al.texto}
            </span>
          ))}
        </div>
      )}
      <div className="workspace">
        <Transcript turns={call.turns} highlight={hover} live={call.live} onAddTurn={call.addTurn} inputRef={inputRef} />
        <div className="right">
          <FichaView call={call} onHover={setHover} activeStep={selected} scrollKey={scrollKey} />
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
