import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { getCampo, type Evidence, type FieldKey } from "../api/schemas";
import type { CallState } from "../state/useCall";
import { CATEGORIA_LABEL, LABELS, PRIORIDAD_LABEL, pct } from "../util";
import { MapView } from "./MapView";

interface Props {
  call: CallState;
  onHover: (ev: Evidence[]) => void;
  activeStep?: number;
  onSelectStep?: (n: number) => void;
  scrollKey?: number;
}

const SELECTS: Partial<Record<FieldKey, Record<string, string>>> = {
  "suceso.categoria": CATEGORIA_LABEL,
  prioridad: PRIORIDAD_LABEL,
};

function display(key: FieldKey, v: string | null): string | null {
  if (v == null) return null;
  if (key === "suceso.categoria") return CATEGORIA_LABEL[v] ?? v;
  if (key === "prioridad") return `${v} · ${PRIORIDAD_LABEL[v] ?? ""}`;
  return v;
}

function FieldRow({ k, call, onHover, big }: { k: FieldKey; call: CallState; onHover: Props["onHover"]; big?: boolean }) {
  const campo = call.analisis ? getCampo(call.analisis.ficha, k) : null;
  const value = call.valor(k);
  const edited = k in call.overrides;
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const [sugs, setSugs] = useState<string[]>([]);

  useEffect(() => {
    if (!editing || k !== "ubicacion.calle" || text.trim().length < 2) return;
    const h = window.setTimeout(() => {
      api.calles(text).then(setSugs).catch(() => setSugs([]));
    }, 150);
    return () => window.clearTimeout(h);
  }, [text, editing, k]);

  const start = () => {
    setText(value ?? "");
    setEditing(true);
  };
  const commit = (v: string) => {
    call.setOverride(k, v);
    setEditing(false);
  };
  const options = SELECTS[k];
  const validated = call.validated.has(k);
  const prio = k === "prioridad" && value ? value.toLowerCase() : "";

  return (
    <div
      className={`field ${big ? "big" : ""} ${value ? "" : "is-empty"} ${validated ? "is-validated" : ""}`}
      onMouseEnter={() => campo && onHover(campo.evidence)}
      onMouseLeave={() => onHover([])}
    >
      <span className="f-label">{LABELS[k]}</span>
      <div className="f-value">
        {editing ? (
          options ? (
            <select
              autoFocus
              value={text}
              onChange={(e) => commit(e.target.value)}
              onBlur={() => setEditing(false)}
              onKeyDown={(e) => e.key === "Escape" && setEditing(false)}
            >
              <option value="">— sin dato —</option>
              {Object.entries(options).map(([v, l]) => (
                <option key={v} value={v}>
                  {k === "prioridad" ? `${v} · ${l}` : l}
                </option>
              ))}
            </select>
          ) : (
            <>
              <input
                autoFocus
                value={text}
                list={k === "ubicacion.calle" ? "calles-sug" : undefined}
                onChange={(e) => setText(e.target.value)}
                onBlur={() => setEditing(false)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commit(text);
                  if (e.key === "Escape") setEditing(false);
                }}
              />
              {k === "ubicacion.calle" && (
                <datalist id="calles-sug">
                  {sugs.map((s) => (
                    <option key={s} value={s} />
                  ))}
                </datalist>
              )}
            </>
          )
        ) : (
          <button type="button" className={`f-text ${prio}`} onClick={start} title="Click para corregir">
            {display(k, value) ?? <span className="hint">sin dato — preguntar</span>}
            {!edited && campo?.method.startsWith("orientativa") && <span className="tag orient"> orientativo</span>}
          </button>
        )}
      </div>
      <div className="f-meta">
        {value && campo && !edited && (
          <span
            className={`conf ${campo.level}`}
            title={`Confianza estimada ${pct(campo.confidence)} · ${campo.method}${campo.alternatives.length ? ` · alternativas: ${campo.alternatives.join(", ")}` : ""}`}
          />
        )}
        {value && (
          <span className={`src ${edited ? "operador" : campo?.source ?? ""}`}>
            {edited ? "operador" : campo?.source === "inferido" ? "inferido" : "dicho"}
          </span>
        )}
        {value && (
          <button
            type="button"
            className={`check ${validated ? "on" : ""}`}
            onClick={() => call.toggleValidated(k)}
            title={validated ? "Validado por el operador" : "Validar dato"}
          >
            ✓
          </button>
        )}
      </div>
    </div>
  );
}

export function FichaView({ call, onHover, activeStep = 0, scrollKey = 0, onSelectStep }: Props) {
  const refs = [useRef<HTMLElement>(null), useRef<HTMLElement>(null), useRef<HTMLElement>(null)];
  useEffect(() => {
    // solo al navegar a mano (scrollKey cambia): no mover la pantalla mientras llega el relato
    if (scrollKey > 0 && activeStep >= 1 && activeStep <= 3) {
      refs[activeStep - 1]?.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scrollKey]);
  const act = (n: number) => (activeStep === n ? "active" : "");
  // Click en el título de la sección = seleccionar ese paso del protocolo
  const headerProps = (n: number) => ({
    className: "card-h selectable",
    role: "button",
    tabIndex: 0,
    title: `Ir al paso ${n} (Alt+Shift+${n})`,
    onClick: () => onSelectStep?.(n),
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onSelectStep?.(n);
      }
    },
  });
  const geo = call.geo;
  const geoLabel: Record<string, string> = {
    validada: "Dirección validada",
    parcial: "Validación parcial",
    no_validada: "Dirección NO válida",
    sin_datos: "Sin dirección",
  };
  return (
    <div className="ficha">
      <section ref={refs[0]} className={`card block ${act(1)}`}>
        <header {...headerProps(1)}>
          <span>1 · Ubicación</span>
          {geo && (
            <span className={`geo-badge ${geo.estado}`} title={geo.verificaciones.join("\n")}>
              {geoLabel[geo.estado]}
            </span>
          )}
        </header>
        <div className="ubic-grid">
          <div>
            <FieldRow k="ubicacion.calle" call={call} onHover={onHover} big />
            <FieldRow k="ubicacion.altura" call={call} onHover={onHover} big />
            <FieldRow k="ubicacion.interseccion" call={call} onHover={onHover} />
            <FieldRow k="ubicacion.entre_calles" call={call} onHover={onHover} />
            <FieldRow k="ubicacion.piso_depto" call={call} onHover={onHover} />
            <FieldRow k="ubicacion.referencia" call={call} onHover={onHover} />
            <FieldRow k="ubicacion.barrio" call={call} onHover={onHover} />
          </div>
          <MapView geo={geo ?? null} />
        </div>
        {geo && geo.verificaciones.length > 0 && (
          <ul className="geo-checks">
            {geo.verificaciones.map((v) => (
              <li key={v} className={/NO |FUERA/.test(v) ? "bad" : "ok"}>
                {v}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section ref={refs[1]} className={`card block ${act(2)}`}>
        <header {...headerProps(2)}>
          <span>2 · Qué pasó</span>
        </header>
        <FieldRow k="prioridad" call={call} onHover={onHover} big />
        <FieldRow k="suceso.categoria" call={call} onHover={onHover} />
        <FieldRow k="suceso.subcategoria" call={call} onHover={onHover} />
        <FieldRow k="suceso.descripcion" call={call} onHover={onHover} />
      </section>
      <section ref={refs[2]} className={`card block ${act(3)}`}>
        <header {...headerProps(3)}>
          <span>3 · Personas y riesgos</span>
        </header>
        <FieldRow k="personas.cantidad" call={call} onHover={onHover} />
        <FieldRow k="personas.victimas" call={call} onHover={onHover} />
        <FieldRow k="personas.estado" call={call} onHover={onHover} />
        <FieldRow k="personas.atrapados" call={call} onHover={onHover} />
        <FieldRow k="llamante.rol" call={call} onHover={onHover} />
        <FieldRow k="riesgos" call={call} onHover={onHover} />
      </section>
    </div>
  );
}
