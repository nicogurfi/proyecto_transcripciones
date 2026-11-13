import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { analizarStream, api } from "../api/client";
import { FIELD_KEYS, getCampo, type Analisis, type Carta, type FieldKey, type Turn } from "../api/schemas";

export interface CallMeta {
  casoId: string | null;
  titulo: string;
  timestamp: string | null;
  origen: string;
}

export type CheckMark = "confirmada" | "no_aplica";

const EMPTY_META: CallMeta = { casoId: null, titulo: "Nueva llamada", timestamp: null, origen: "TELEFONIA_911" };

/** Divide los turnos en "fotogramas" para simular la llamada en vivo (oración por oración). */
function liveFrames(turns: Turn[]): Turn[][] {
  const frames: Turn[][] = [];
  const acc: Turn[] = [];
  for (const t of turns) {
    if (t.speaker === "operador") {
      acc.push(t);
      frames.push([...acc]);
      continue;
    }
    const parts = t.text.match(/[^.!?]+[.!?]*/g) ?? [t.text];
    let text = "";
    acc.push({ speaker: "llamante", text: "" });
    for (const p of parts) {
      text = (text + " " + p.trim()).trim();
      acc[acc.length - 1] = { speaker: "llamante", text };
      frames.push([...acc]);
    }
  }
  return frames;
}

export function useCall() {
  const [meta, setMeta] = useState<CallMeta>(EMPTY_META);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [analisis, setAnalisis] = useState<Analisis | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Partial<Record<FieldKey, string | null>>>({});
  const [validated, setValidated] = useState<Set<FieldKey>>(new Set());
  const [checkMarks, setCheckMarks] = useState<Record<string, CheckMark>>({});
  const [instrMarks, setInstrMarks] = useState<Set<string>>(new Set());
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [live, setLive] = useState(false);
  const [carta, setCarta] = useState<Carta | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const liveTimer = useRef<number | null>(null);

  // ---- análisis incremental (debounce + cancelación de la request anterior)
  useEffect(() => {
    if (turns.length === 0 || turns.every((t) => !t.text.trim())) return;
    const handle = window.setTimeout(() => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setAnalyzing(true);
      setError(null);
      analizarStream({ turnos: turns.filter((t) => t.text.trim()), timestamp: meta.timestamp }, setAnalisis, ctrl.signal)
        .catch((e: unknown) => {
          if (!(e instanceof DOMException && e.name === "AbortError")) setError(e instanceof Error ? e.message : String(e));
        })
        .finally(() => {
          if (abortRef.current === ctrl) setAnalyzing(false);
        });
    }, 220);
    return () => window.clearTimeout(handle);
  }, [turns, meta.timestamp]);

  const stopLive = useCallback(() => {
    if (liveTimer.current) window.clearInterval(liveTimer.current);
    liveTimer.current = null;
    setLive(false);
  }, []);

  const reset = useCallback(() => {
    stopLive();
    abortRef.current?.abort();
    setMeta(EMPTY_META);
    setTurns([]);
    setAnalisis(null);
    setOverrides({});
    setValidated(new Set());
    setCheckMarks({});
    setInstrMarks(new Set());
    setDismissed(new Set());
    setStartedAt(null);
    setCarta(null);
    setError(null);
  }, [stopLive]);

  const load = useCallback(
    (m: CallMeta, newTurns: Turn[], asLive: boolean) => {
      reset();
      setMeta(m);
      setStartedAt(Date.now());
      if (!asLive) {
        setTurns(newTurns);
        return;
      }
      const frames = liveFrames(newTurns);
      let i = 0;
      setLive(true);
      setTurns(frames[0] ?? []);
      liveTimer.current = window.setInterval(() => {
        i += 1;
        if (i >= frames.length) {
          stopLive();
          return;
        }
        setTurns(frames[i] ?? []);
      }, 1500);
    },
    [reset, stopLive],
  );

  useEffect(() => () => stopLive(), [stopLive]);

  const addTurn = useCallback((t: Turn) => {
    setStartedAt((s) => s ?? Date.now());
    setTurns((prev) => [...prev, t]);
  }, []);

  const valor = useCallback(
    (key: FieldKey): string | null => {
      if (key in overrides) return overrides[key] ?? null;
      return analisis ? getCampo(analisis.ficha, key).value : null;
    },
    [overrides, analisis],
  );

  const setOverride = useCallback((key: FieldKey, v: string | null) => {
    setOverrides((o) => ({ ...o, [key]: v && v.trim() ? v.trim() : null }));
    setValidated((s) => new Set(s).add(key));
  }, []);

  const toggleValidated = useCallback((key: FieldKey) => {
    setValidated((s) => {
      const n = new Set(s);
      if (n.has(key)) n.delete(key);
      else n.add(key);
      return n;
    });
  }, []);

  const toggleCheck = useCallback((id: string, mark: CheckMark = "confirmada") => {
    setCheckMarks((m) => {
      const n = { ...m };
      if (n[id] === mark) delete n[id];
      else n[id] = mark;
      return n;
    });
  }, []);

  const toggleInstr = useCallback((id: string) => {
    setInstrMarks((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }, []);

  const dismiss = useCallback((id: string) => setDismissed((s) => new Set(s).add(id)), []);

  const pendientes = useMemo(
    () => (analisis?.checklist ?? []).filter((c) => !checkMarks[c.id] && c.estado === "pendiente"),
    [analisis, checkMarks],
  );
  const inconsistencias = useMemo(
    () => (analisis?.inconsistencias ?? []).filter((i) => !dismissed.has(i.id)),
    [analisis, dismissed],
  );

  const derivar = useCallback(
    async (notas: string) => {
      if (!analisis) return;
      const finales: Record<string, string | null> = {};
      const sugeridos: Record<string, string | null> = {};
      const confianzas: Record<string, number> = {};
      for (const k of FIELD_KEYS) {
        const c = getCampo(analisis.ficha, k);
        finales[k] = valor(k);
        sugeridos[k] = c.value;
        confianzas[k] = c.confidence;
      }
      const result = await api.derivar({
        turnos: turns.filter((t) => t.text.trim()),
        valores_finales: finales,
        valores_sugeridos: sugeridos,
        confianzas,
        campos_validados: [...validated],
        checklist: analisis.checklist.map((c) => ({
          pregunta: c.pregunta,
          estado: checkMarks[c.id] ?? c.estado,
          evidencia: c.evidencia?.text ?? null,
        })),
        instrucciones_transmitidas: analisis.instrucciones.filter((i) => instrMarks.has(i.id)).map((i) => i.texto),
        alertas_criticas: analisis.alertas_criticas.map((a) => a.texto),
        recursos_sugeridos: analisis.casos_similares.slice(0, 1).map((c) => c.recursos),
        geo: analisis.geo,
        notas_operador: notas || null,
        origen: meta.origen,
        caso_ref: meta.casoId,
        timestamp_llamada: meta.timestamp,
        duracion_segundos: startedAt ? Math.round((Date.now() - startedAt) / 1000) : null,
        proveedor: analisis.proveedor,
      });
      setCarta(result);
      stopLive();
      return result;
    },
    [analisis, valor, turns, validated, checkMarks, instrMarks, meta, startedAt, stopLive],
  );

  return {
    meta, turns, analisis, analyzing, error, overrides, validated, checkMarks, instrMarks, startedAt, live, carta,
    pendientes, inconsistencias,
    load, reset, addTurn, valor, setOverride, toggleValidated, toggleCheck, toggleInstr, dismiss, derivar, stopLive,
    setCarta,
  };
}

export type CallState = ReturnType<typeof useCall>;
