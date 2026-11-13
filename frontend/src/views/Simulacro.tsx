import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { SimulacroCaso, SimulacroResultado, SimulacroStats, Turn } from "../api/schemas";
import { CATEGORIA_LABEL, PRIORIDAD_LABEL, fmtDuration } from "../util";

type Fase = "inicio" | "llamada" | "resultado";

export function Simulacro() {
  const [fase, setFase] = useState<Fase>("inicio");
  const [dificultad, setDificultad] = useState<"normal" | "ruidosa">("normal");
  const [caso, setCaso] = useState<SimulacroCaso | null>(null);
  const [visible, setVisible] = useState<Turn[]>([]);
  const [t0, setT0] = useState(0);
  const [now, setNow] = useState(Date.now());
  const [form, setForm] = useState({ calle: "", altura: "", interseccion: "", categoria: "", prioridad: "", preguntas: "", instrucciones: "" });
  const [res, setRes] = useState<SimulacroResultado | null>(null);
  const [stats, setStats] = useState<SimulacroStats | null>(null);
  const [hechos, setHechos] = useState<string[]>([]);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    api.simStats().then(setStats).catch(() => undefined);
  }, [res]);

  useEffect(() => {
    if (fase !== "llamada") return;
    const h = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(h);
  }, [fase]);

  const empezar = async () => {
    const c = await api.simCaso(dificultad, hechos);
    setCaso(c);
    setRes(null);
    setForm({ calle: "", altura: "", interseccion: "", categoria: "", prioridad: "", preguntas: "", instrucciones: "" });
    setFase("llamada");
    setT0(Date.now());
    // la llamada "llega" de a poco: el operador practica con información incompleta
    const frames: Turn[][] = [];
    const acc: Turn[] = [];
    for (const t of c.turnos) {
      if (t.speaker === "operador") {
        acc.push(t);
        frames.push([...acc]);
        continue;
      }
      const parts = t.text.match(/[^.!?,]+[.!?,]*/g) ?? [t.text];
      acc.push({ speaker: "llamante", text: "" });
      let txt = "";
      for (const p of parts) {
        txt = `${txt} ${p.trim()}`.trim();
        acc[acc.length - 1] = { speaker: "llamante", text: txt };
        frames.push([...acc]);
      }
    }
    let i = 0;
    setVisible(frames[0] ?? []);
    if (timer.current) window.clearInterval(timer.current);
    timer.current = window.setInterval(() => {
      i += 1;
      if (i >= frames.length) {
        if (timer.current) window.clearInterval(timer.current);
        return;
      }
      setVisible(frames[i] ?? []);
    }, 1100);
  };

  const enviar = async () => {
    if (!caso) return;
    if (timer.current) window.clearInterval(timer.current);
    const r = await api.simEvaluar({
      caso_id: caso.caso_id,
      dificultad: caso.dificultad,
      calle: form.calle || null,
      altura: form.altura || null,
      interseccion: form.interseccion || null,
      categoria: form.categoria || null,
      prioridad: form.prioridad || null,
      preguntas_pendientes: form.preguntas.split("\n").map((x) => x.trim()).filter(Boolean),
      instrucciones: form.instrucciones || null,
      tiempo_segundos: Math.round((Date.now() - t0) / 1000),
    });
    setRes(r);
    setHechos((h) => [...h, caso.caso_id]);
    setFase("resultado");
  };

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  return (
    <div className="simulacro">
      <header className="sim-head">
        <div>
          <h1>Simulacro sin copiloto</h1>
          <p className="muted">
            Resolvé la llamada con tu propio criterio. Mantiene activas las habilidades del operador (evita la atrofia por
            dependencia del copiloto) y cada sesión queda registrada como dato de entrenamiento.
          </p>
        </div>
        {stats && (
          <div className="sim-stats">
            <div><b>{stats.sesiones}</b><span>sesiones</span></div>
            <div><b>{stats.promedio}%</b><span>promedio</span></div>
            <div><b>{stats.tiempo_promedio}s</b><span>tiempo medio</span></div>
          </div>
        )}
      </header>

      {fase === "inicio" && (
        <div className="card sim-start">
          <label>
            Dificultad
            <select value={dificultad} onChange={(e) => setDificultad(e.target.value as "normal" | "ruidosa")}>
              <option value="normal">Normal (transcripción limpia)</option>
              <option value="ruidosa">Ruidosa (errores de transcripción, muletillas, sin puntuación)</option>
            </select>
          </label>
          <button type="button" className="primary" onClick={() => void empezar()}>Atender llamada simulada</button>
        </div>
      )}

      {fase === "llamada" && caso && (
        <div className="sim-grid">
          <section className="card transcript">
            <header className="card-h">
              <span>Llamada entrante · {caso.origen}</span>
              <span className="timer">{fmtDuration(now - t0)}</span>
            </header>
            <div className="turns">
              {visible.map((t, i) => (
                <div key={i} className={`turn ${t.speaker}`}>
                  <span className="who">{t.speaker === "operador" ? "OP" : "LL"}</span>
                  <p>{t.text}</p>
                </div>
              ))}
            </div>
          </section>
          <section className="card sim-form">
            <header className="card-h"><span>Tu ficha</span></header>
            <label>Calle<input value={form.calle} onChange={set("calle")} autoFocus /></label>
            <div className="row2">
              <label>Altura<input value={form.altura} onChange={set("altura")} /></label>
              <label>Esquina / entre calles<input value={form.interseccion} onChange={set("interseccion")} /></label>
            </div>
            <div className="row2">
              <label>
                Tipo de hecho
                <select value={form.categoria} onChange={set("categoria")}>
                  <option value="">—</option>
                  {Object.entries(CATEGORIA_LABEL).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
                </select>
              </label>
              <label>
                Prioridad
                <select value={form.prioridad} onChange={set("prioridad")}>
                  <option value="">—</option>
                  {Object.entries(PRIORIDAD_LABEL).map(([k, l]) => <option key={k} value={k}>{k} · {l}</option>)}
                </select>
              </label>
            </div>
            <label>Preguntas que harías (una por línea)<textarea rows={4} value={form.preguntas} onChange={set("preguntas")} /></label>
            <label>Instrucciones de pre-arribo<textarea rows={3} value={form.instrucciones} onChange={set("instrucciones")} /></label>
            <button type="button" className="primary" onClick={() => void enviar()}>Finalizar y evaluar</button>
          </section>
        </div>
      )}

      {fase === "resultado" && res && (
        <div className="card sim-result">
          <header className="sim-score">
            <div className={`score ${res.porcentaje >= 85 ? "good" : res.porcentaje >= 60 ? "mid" : "bad"}`}>{res.porcentaje}%</div>
            <div>
              <h2>{res.comentario}</h2>
              <p className="muted">{res.caso_id} · {res.referencia.subcategoria}</p>
            </div>
          </header>
          <table>
            <thead><tr><th>Criterio</th><th>Puntaje</th><th>Tu respuesta</th><th>Referencia</th></tr></thead>
            <tbody>
              {res.items.map((it) => (
                <tr key={it.criterio} className={it.puntaje >= it.maximo ? "ok" : it.puntaje > 0 ? "mid" : "bad"}>
                  <td>{it.criterio}<br /><span className="muted">{it.detalle}</span></td>
                  <td>{it.puntaje}/{it.maximo}</td>
                  <td>{it.respondido ?? "—"}</td>
                  <td>{it.esperado ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="sim-compare">
            <div>
              <h3>Lo que habría sugerido el copiloto</h3>
              <ul>{Object.entries(res.copiloto).map(([k, v]) => <li key={k}><b>{k}</b>: {v ?? "—"}</li>)}</ul>
            </div>
            <div>
              <h3>Referencia del caso</h3>
              <p><b>Instrucciones:</b> {res.referencia.instrucciones}</p>
              <p><b>Riesgos:</b> {res.referencia.riesgos}</p>
            </div>
          </div>
          <button type="button" className="primary" onClick={() => void empezar()}>Siguiente caso</button>
        </div>
      )}
    </div>
  );
}
