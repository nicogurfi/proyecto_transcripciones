import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Evidence, Turn } from "../api/schemas";

interface Props {
  turns: Turn[];
  highlight: Evidence[];
  live: boolean;
  onAddTurn: (t: Turn) => void;
  inputRef: React.RefObject<HTMLInputElement>;
}

function renderWithMarks(text: string, marks: Evidence[]): ReactNode {
  if (marks.length === 0) return text;
  const sorted = [...marks].sort((a, b) => a.start - b.start);
  const out: ReactNode[] = [];
  let pos = 0;
  sorted.forEach((m, i) => {
    if (m.start < pos) return;
    out.push(text.slice(pos, m.start));
    out.push(<mark key={i}>{text.slice(m.start, m.end)}</mark>);
    pos = m.end;
  });
  out.push(text.slice(pos));
  return out;
}

export function Transcript({ turns, highlight, live, onAddTurn, inputRef }: Props) {
  const [speaker, setSpeaker] = useState<Turn["speaker"]>("llamante");
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns]);

  const submit = () => {
    if (!draft.trim()) return;
    onAddTurn({ speaker, text: draft.trim() });
    setDraft("");
    setSpeaker((s) => (s === "llamante" ? "operador" : "llamante"));
  };

  return (
    <section className="transcript card">
      <header className="card-h">
        <span>Transcripción</span>
        {live && <span className="live-dot">EN VIVO</span>}
      </header>
      <div className="turns">
        {turns.length === 0 && (
          <div className="empty-state">
            <p>Sin llamada activa.</p>
            <p className="muted">
              Cargá un caso con <kbd>Alt</kbd>+<kbd>L</kbd> o escribí la primera respuesta del llamante abajo.
            </p>
          </div>
        )}
        {turns.map((t, i) => (
          <div key={i} className={`turn ${t.speaker}`}>
            <span className="who">{t.speaker === "operador" ? "OP" : "LL"}</span>
            <p>
              {renderWithMarks(t.text, highlight.filter((h) => h.turn === i))}
              {live && i === turns.length - 1 && t.speaker === "llamante" && <span className="caret" />}
            </p>
          </div>
        ))}
        <div ref={endRef} />
      </div>
      <div className="turn-input">
        <button
          type="button"
          className={`speaker-toggle ${speaker}`}
          onClick={() => setSpeaker((s) => (s === "llamante" ? "operador" : "llamante"))}
          title="Cambiar hablante (Tab)"
        >
          {speaker === "llamante" ? "Llamante" : "Operador"}
        </button>
        <input
          ref={inputRef}
          value={draft}
          placeholder={speaker === "llamante" ? "Respuesta del llamante… (Enter)" : "Pregunta del operador… (Enter)"}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.ctrlKey && !e.metaKey) {
              e.preventDefault();
              submit();
            } else if (e.key === "Tab" && !draft) {
              e.preventDefault();
              setSpeaker((s) => (s === "llamante" ? "operador" : "llamante"));
            }
          }}
        />
      </div>
    </section>
  );
}
