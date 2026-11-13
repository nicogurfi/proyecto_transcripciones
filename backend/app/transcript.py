"""Ingesta de transcripciones: separa turnos de diálogo y mapea offsets.

Acepta texto crudo tipo dataset ("Operador: ... Llamante: ...") o turnos
ya estructurados. Todas las evidencias se expresan como (turno, start, end)
relativos al texto de ese turno, para que el frontend pueda resaltarlas.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.schemas import Evidence, Speaker, Turn

_SPEAKER_RE = re.compile(
    r"(?P<label>Operador(?:a)?|Llamante|Ciudadano|Ciudadana|Op|Ll)\s*:\s*",
    re.IGNORECASE,
)

_SPEAKER_MAP: dict[str, Speaker] = {
    "operador": "operador",
    "operadora": "operador",
    "op": "operador",
    "llamante": "llamante",
    "ciudadano": "llamante",
    "ciudadana": "llamante",
    "ll": "llamante",
}

_FILLERS_RE = re.compile(r"\b(eh+|em+|mm+)\b", re.IGNORECASE)


def parse_raw_transcript(raw: str) -> list[Turn]:
    """Convierte una desgrabación en texto plano a turnos.

    Si no hay etiquetas de hablante, todo el texto se toma como un único
    turno del llamante (caso típico de una desgrabación sin diarización).
    """
    raw = raw.replace("\r\n", "\n").strip()
    if not raw:
        return []
    matches = list(_SPEAKER_RE.finditer(raw))
    if not matches:
        return [Turn(speaker="llamante", text=_clean(raw))]
    turns: list[Turn] = []
    prefix = raw[: matches[0].start()].strip()
    if prefix:
        turns.append(Turn(speaker="llamante", text=_clean(prefix)))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        text = _clean(raw[m.end() : end])
        if text:
            speaker = _SPEAKER_MAP[m.group("label").lower()]
            turns.append(Turn(speaker=speaker, text=text))
    return turns


def _clean(text: str) -> str:
    text = _FILLERS_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


@dataclass(slots=True)
class Document:
    """Concatenación de turnos con mapa de offsets absolutos <-> por turno."""

    turns: list[Turn]
    text: str
    bases: list[int]

    @classmethod
    def from_turns(cls, turns: list[Turn]) -> Document:
        parts: list[str] = []
        bases: list[int] = []
        pos = 0
        for t in turns:
            bases.append(pos)
            parts.append(t.text)
            pos += len(t.text) + 1  # "\n" separador
        return cls(turns=turns, text="\n".join(parts), bases=bases)

    def turn_of(self, abs_pos: int) -> int:
        idx = 0
        for i, base in enumerate(self.bases):
            if abs_pos >= base:
                idx = i
        return idx

    def evidence(self, start: int, end: int) -> Evidence:
        turn = self.turn_of(start)
        base = self.bases[turn]
        turn_len = len(self.turns[turn].text)
        rel_start = max(0, start - base)
        rel_end = min(turn_len, end - base)
        return Evidence(turn=turn, start=rel_start, end=rel_end, text=self.text[start:end])

    def is_caller(self, abs_pos: int) -> bool:
        return self.turns[self.turn_of(abs_pos)].speaker == "llamante"

    @property
    def caller_text(self) -> str:
        return " ".join(t.text for t in self.turns if t.speaker == "llamante")
