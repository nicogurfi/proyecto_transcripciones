"""Utilidades de texto en español: normalización, tokenización con offsets,
clave fonética, stemming liviano y números en palabras.

Todo es determinista y sin dependencias pesadas: se usa en el camino rápido
(<50 ms) y en el modo mock.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+(?:\.[A-Za-z]{1,2}\.)?")

STOPWORDS: frozenset[str] = frozenset(
    """a al algo algun alguna alguno algunos ante antes aqui asi aun bajo cada casi como con contra cual
    cuales cuando de del desde donde dos el ella ellas ellos en entre era es esa ese eso esta estaba estan
    este esto estos fue fueron ha habia han hasta hay la las le les lo los mas me mi mis muy ni no nos o
    otra otro para pero poco por porque que se sea ser si sin sobre su sus tambien tiene tienen todo todos
    tu un una uno unos usted y ya yo""".split()
)

NUMBER_WORDS: dict[str, int] = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15,
    "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "cien": 100,
}


def strip_accents(text: str) -> str:
    """Quita tildes conservando la Ñ (relevante en nombres de calles)."""
    out = []
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn":
            # conservar la tilde de la ñ (n + U+0303)
            if ch == "̃" and out and out[-1] in "nN":
                out[-1] = "ñ" if out[-1] == "n" else "Ñ"
            continue
        out.append(ch)
    return unicodedata.normalize("NFC", "".join(out))


def norm(text: str) -> str:
    """Mayúsculas, sin tildes, sin puntuación, espacios colapsados."""
    t = strip_accents(text).upper()
    t = re.sub(r"[^A-Z0-9Ñ ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


@dataclass(frozen=True, slots=True)
class Token:
    text: str  # texto original
    norm: str  # normalizado (MAYÚSCULAS sin tildes)
    start: int
    end: int

    @property
    def is_capitalized(self) -> bool:
        return self.text[:1].isupper()

    @property
    def is_number(self) -> bool:
        return self.norm.isdigit()


def tokenize(text: str) -> list[Token]:
    tokens: list[Token] = []
    for m in _WORD_RE.finditer(text):
        raw = m.group(0)
        tokens.append(Token(raw, norm(raw).replace(" ", ""), m.start(), m.end()))
    return tokens


def phonetic_key(text: str) -> str:
    """Clave fonética simplificada para español rioplatense.

    Colapsa confusiones típicas de transcripción/ASR: b/v, s/z/c(e,i),
    ll/y, h muda, qu/k/c(a,o,u), g(e,i)/j, dobles letras y la E protética
    ("Escalabrini" -> "Scalabrini").
    """
    t = norm(text).replace(" ", "")
    if not t:
        return ""
    rules = [
        (r"^ES(?=[CPT])", "S"),
        (r"H", ""),
        (r"LL", "Y"),
        (r"QU", "K"),
        (r"C(?=[EI])", "S"),
        (r"C", "K"),
        (r"G(?=[EI])", "J"),
        (r"GU(?=[EI])", "G"),
        (r"Z", "S"),
        (r"V", "B"),
        (r"W", "B"),
        (r"X", "KS"),
        (r"Y$", "I"),
        (r"(.)\1+", r"\1"),
    ]
    for pattern, repl in rules:
        t = re.sub(pattern, repl, t)
    return t


def stem(word: str) -> str:
    """Stemming muy liviano: prefijo de 5 letras sobre texto normalizado."""
    w = norm(word).replace(" ", "")
    return w[:5] if len(w) > 5 else w


def content_stems(text: str) -> list[str]:
    return [stem(t.norm) for t in tokenize(text) if t.norm.lower() not in STOPWORDS and len(t.norm) > 2]


def word_to_int(word: str) -> int | None:
    w = strip_accents(word).lower()
    if w.isdigit():
        return int(w)
    return NUMBER_WORDS.get(w)


_SENT_RE = re.compile(r"[^.!?¡¿]+[.!?]*")


_ABREVIATURAS = re.compile(r"\b(?:av|avda|dr|dra|gral|sr|sra|srta|cnel|pte|ing|n|nro|dto|depto|esq|km)\.$", re.I)


def split_sentences(text: str, offset: int = 0) -> list[tuple[str, int, int]]:
    """Divide en oraciones devolviendo (texto, start, end) con offsets absolutos.
    No corta después de abreviaturas ("Av. San Juan", "Dr. Rivera")."""
    out: list[tuple[str, int, int]] = []
    chunks: list[tuple[str, int]] = []
    for m in _SENT_RE.finditer(text):
        if chunks and _ABREVIATURAS.search(chunks[-1][0].rstrip()):
            _, start = chunks[-1]
            chunks[-1] = (text[start : m.end()], start)
        else:
            chunks.append((m.group(0), m.start()))
    for chunk, chunk_start in chunks:
        stripped = chunk.strip(" ,;")
        if len(stripped) < 3:
            continue
        lead = len(chunk) - len(chunk.lstrip(" ,;"))
        start = offset + chunk_start + lead
        out.append((stripped, start, start + len(stripped)))
    return out
