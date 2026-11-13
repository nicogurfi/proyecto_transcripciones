"""Callejero oficial de CABA (USIG / Buenos Aires Data) embebido para
validación offline: existencia de la calle, rangos de altura y cruces.

Formato fuente: [cod, nombre, keywords, [[desde, hasta], ...], [cod_cruce, ...]]
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache

from rapidfuzz import fuzz, process

from app.config import DATA_DIR
from app.text import STOPWORDS, Token, norm, phonetic_key, tokenize

STRONG_CUES = frozenset({"AV", "AVENIDA", "AVDA", "CALLE", "CASI", "ESQUINA", "ENTRE", "ALTURA", "PASAJE"})
WEAK_CUES = frozenset({"EN", "Y", "DE", "POR", "SOBRE", "HACIA", "CON"})
# Si la palabra previa es una de estas, lo que sigue es un lugar, no una calle.
BLOCK_PREV = frozenset(
    {"PLAZA", "PARQUE", "ESTACION", "LINEA", "VIAS", "BARRIO", "VILLA", "HOSPITAL", "CLUB", "COLEGIO",
     "SANATORIO", "CLINICA", "SUBTE", "TREN", "FERROCARRIL", "DEL", "SOY", "LLAMO", "SENORA", "SENOR",
     "DON", "DONA", "PUENTE"}
)
# Nombres de calles que también son palabras/expresiones frecuentes en un relato.
AMBIGUOUS = frozenset(
    {"HOLA", "PAZ", "SOL", "LUNA", "LIBERTAD", "JUSTO", "AGUA", "CUBA", "LIMA", "SALTA", "PERU", "CHILE",
     "ESPANA", "MEXICO", "ITALIA", "FRANCIA", "PIEDRAS", "DEFENSA", "CONGRESO", "PROVINCIA", "PATRICIOS",
     "BOMBEROS", "FUEGO", "HUMO", "GENTE", "VIDA", "TERRERO", "MORENO", "SUAREZ", "LOPEZ", "GARCIA",
     "GONZALEZ", "PEREZ", "MARTINEZ", "FERNANDEZ", "ALVAREZ", "SANCHEZ", "TORRES", "RAMOS", "CASTRO",
     "BLANCO", "NEGRO", "CAMPANA", "MAYO", "JULIO", "ABRIL", "AMERICA", "ARGENTINA", "REPUBLICA", "MAR",
     "SOLDADO", "CAMION", "PLAZA", "MADERA", "LINEA", "FRANKLIN", "ESCUELA", "LAGO", "RIO", "CAMPO", "MONTE", "SALUD", "AMOR", "PIEDRA", "AYUDA",
     "URGENCIA", "EMERGENCIA", "SEGURIDAD", "RESCATE", "AUXILIO", "CIUDAD", "NORTE", "SUR", "ESTE", "OESTE"}
)
BARRIOS: tuple[str, ...] = (
    "Agronomía", "Almagro", "Balvanera", "Barracas", "Belgrano", "Boedo", "Caballito", "Chacarita", "Coghlan",
    "Colegiales", "Constitución", "Flores", "Floresta", "La Boca", "La Paternal", "Liniers", "Mataderos",
    "Monte Castro", "Montserrat", "Nueva Pompeya", "Núñez", "Palermo", "Parque Avellaneda", "Parque Chacabuco",
    "Parque Chas", "Parque Patricios", "Puerto Madero", "Recoleta", "Retiro", "Saavedra", "San Cristóbal",
    "San Nicolás", "San Telmo", "Vélez Sarsfield", "Versalles", "Villa Crespo", "Villa del Parque",
    "Villa Devoto", "Villa General Mitre", "Villa Lugano", "Villa Luro", "Villa Ortúzar", "Villa Pueyrredón",
    "Villa Real", "Villa Riachuelo", "Villa Santa Rita", "Villa Soldati", "Villa Urquiza", "Pompeya", "Soldati",
    "Lugano",
)
BARRIOS_NORM = {norm(b): b for b in BARRIOS}
# Palabras que no pueden abrir ni cerrar el nombre de una calle.
_EDGE_WORDS = frozenset({w.upper() for w in STOPWORDS} - {"MAYO"}) | {"SE", "UN", "ES"}
_SKIP_NAME = re.compile(r"SIN NOMBRE OFICIAL|NO OFICIAL|^PJE \(|PUENTE PEATONAL|^PASAJE PEATONAL")
_TITLES = re.compile(r"\b(GRAL|CNEL|CMTE|DR|ING|PTE|TTE|STA|STO|SGTO|CAP|ALTE|PBRO|FRAY|GOB|INT|MAESTRO)\b\.?")


@dataclass(frozen=True, slots=True)
class Tramo:
    cod: int
    nombre: str  # nombre oficial, p.ej. "SCALABRINI ORTIZ, RAUL AV."
    rangos: tuple[tuple[int, int], ...]
    cruces: frozenset[int]

    @property
    def es_avenida(self) -> bool:
        return bool(re.search(r"\bAV\.?$", self.nombre))


@dataclass(slots=True)
class Mencion:
    start: int
    end: int
    surface: str
    alias: str
    tramos: list[Tramo]
    match: str  # exacto | fonetico | aproximado
    score: float
    av_cue: bool
    prev: str | None
    token_index: int
    token_end: int


@dataclass(slots=True)
class Callejero:
    alias_index: dict[str, list[Tramo]] = field(default_factory=dict)
    phonetic_index: dict[str, list[str]] = field(default_factory=dict)
    aliases: list[str] = field(default_factory=list)
    by_cod: dict[int, list[Tramo]] = field(default_factory=dict)

    # ---------- construcción ----------
    @classmethod
    def load(cls) -> Callejero:
        raw = json.loads((DATA_DIR / "callejero_caba.json").read_text(encoding="utf-8"))
        cal = cls()
        for cod, nombre, _keywords, rangos, cruces in raw:
            if _SKIP_NAME.search(nombre):
                continue
            tramo = Tramo(cod, nombre, tuple((int(a), int(b)) for a, b in rangos), frozenset(cruces))
            cal.by_cod.setdefault(cod, []).append(tramo)
            for alias in _aliases(nombre):
                cal.alias_index.setdefault(alias, []).append(tramo)
        cal.aliases = sorted(cal.alias_index)
        for alias in cal.aliases:
            cal.phonetic_index.setdefault(phonetic_key(alias), []).append(alias)
        return cal

    # ---------- búsqueda de menciones en texto ----------
    def find_mentions(self, text: str) -> list[Mencion]:
        tokens = tokenize(text)
        mentions: list[Mencion] = []
        i = 0
        last_end = -1
        while i < len(tokens):
            found = self._match_at(text, tokens, i, chained=last_end == i - 1)
            if found:
                mentions.append(found)
                i = found.token_end
                last_end = found.token_end
            else:
                i += 1
        return mentions

    def _match_at(self, text: str, tokens: list[Token], i: int, chained: bool = False) -> Mencion | None:
        prev = tokens[i - 1].norm if i > 0 else None
        prev2 = tokens[i - 2].norm if i > 1 else None
        if tokens[i].norm in {"AV", "AVENIDA", "AVDA"}:
            # Solo nombres oficiales que empiezan con "Avenida" ("Avenida de Mayo")
            for n in (4, 3):
                phrase = " ".join(t.norm for t in tokens[i : i + n])
                if i + n <= len(tokens) and phrase in self.alias_index:
                    return self._mencion(text, tokens[i : i + n], phrase, "exacto", 100.0, True, prev, i, n)
            return None
        if (tokens[i].norm in _EDGE_WORDS and tokens[i].norm != "ENTRE") or tokens[i].norm == "CALLE":
            return None
        if tokens[i].is_number and not (i + 2 < len(tokens) and tokens[i + 1].norm == "DE"):
            return None  # números sueltos no son calles (salvo "27 de Febrero")
        av_cue = prev in {"AV", "AVENIDA", "AVDA"}
        # chained: "X y Z" / "entre X y Z" -> Z hereda el contexto de calle de X
        chained = chained and prev in {"Y", "CASI", "ESQUINA"}
        candidates: list[tuple[int, list[Token], str, bool]] = []
        for n in (5, 4, 3, 2, 1):
            if i + n > len(tokens):
                continue
            window = tokens[i : i + n]
            if window[-1].norm in _EDGE_WORDS or "\n" in text[window[0].start : window[-1].end]:
                continue
            phrase = " ".join(t.norm for t in window)
            if len(phrase) < 4:
                continue
            gate = True if chained else self._gate(text, tokens, i, n, prev, prev2, phrase)
            if gate is None:
                continue
            if phrase in self.alias_index:  # 1) exacto, el más largo primero
                return self._mencion(text, window, phrase, "exacto", 100.0, av_cue, prev, i, n)
            if gate and n <= 3 and len(phrase) >= 6 and len(window[-1].norm) > 2:
                candidates.append((n, window, phrase, gate))
        for n, window, phrase, _ in candidates:  # 2) fonético  3) aproximado
            pk = phonetic_key(phrase)
            if pk in self.phonetic_index:
                alias = self.phonetic_index[pk][0]
                return self._mencion(text, window, alias, "fonetico", 90.0, av_cue, prev, i, n)
        for n, window, phrase, _ in candidates:
            best = process.extractOne(phrase, self.aliases, scorer=fuzz.ratio, score_cutoff=88)
            if best and abs(len(best[0]) - len(phrase)) <= 3:
                return self._mencion(text, window, best[0], "aproximado", float(best[1]), av_cue, prev, i, n)
        return None

    def _gate(
        self, text: str, tokens: list[Token], i: int, n: int, prev: str | None, prev2: str | None, phrase: str
    ) -> bool | None:
        """None = descartar; False = aceptar solo exacto; True = aceptar exacto/fonético/aproximado."""
        nxt = tokens[i + n] if i + n < len(tokens) else None
        nxt2 = tokens[i + n + 1] if i + n + 1 < len(tokens) else None
        number_after = bool(nxt and (nxt.is_number or (nxt.norm == "AL" and nxt2 and nxt2.is_number)))
        strong = prev in STRONG_CUES
        if prev in BLOCK_PREV and not number_after and not strong:
            return None
        if phrase in AMBIGUOUS or phrase in BARRIOS_NORM:
            return False if (strong or number_after) else None
        first = tokens[i]
        sentence_start = i == 0 or bool(re.search(r"[.!?¡¿:\n]\s*$", text[: first.start]))
        capitalized = first.is_capitalized and not sentence_start
        if strong or number_after:
            return True
        if capitalized and prev in WEAK_CUES:
            return True
        if capitalized:
            return False
        return None

    def _mencion(
        self, text: str, window: list[Token], alias: str, match: str, score: float, av_cue: bool,
        prev: str | None, i: int, n: int,
    ) -> Mencion:
        start, end = window[0].start, window[-1].end
        return Mencion(start, end, text[start:end], alias, self.alias_index[alias], match, score, av_cue, prev, i, i + n)

    # ---------- validación ----------
    def pick_tramo(self, tramos: list[Tramo], altura: int | None, prefer_av: bool) -> Tramo:
        if altura is not None:
            for t in tramos:
                if any(a <= altura <= b for a, b in t.rangos):
                    return t
        if prefer_av:
            for t in tramos:
                if t.es_avenida:
                    return t
        return max(tramos, key=lambda t: (len(t.cruces), len(t.rangos)))

    def altura_en_rango(self, tramos: list[Tramo], altura: int) -> bool | None:
        con_rango = [t for t in tramos if t.rangos]
        if not con_rango:
            return None  # autopistas / trazas sin numeración
        return any(a <= altura <= b for t in con_rango for a, b in t.rangos)

    def rangos(self, tramos: list[Tramo]) -> list[tuple[int, int]]:
        return sorted({r for t in tramos for r in t.rangos})

    def se_cruzan(self, a: list[Tramo], b: list[Tramo]) -> bool:
        cods_b = {t.cod for t in b}
        cods_a = {t.cod for t in a}
        cruces_a = {c for cod in cods_a for t in self.by_cod.get(cod, []) for c in t.cruces}
        cruces_b = {c for cod in cods_b for t in self.by_cod.get(cod, []) for c in t.cruces}
        return bool(cruces_a & cods_b) or bool(cruces_b & cods_a)

    def lookup(self, name: str) -> tuple[str, list[Tramo], str] | None:
        """Busca un nombre suelto (p.ej. propuesto por el LLM) en el callejero."""
        phrase = norm(re.sub(r"^(av\.?|avenida|avda\.?|calle)\s+", "", name.strip(), flags=re.I))
        if not phrase:
            return None
        if phrase in self.alias_index:
            return phrase, self.alias_index[phrase], "exacto"
        pk = phonetic_key(phrase)
        if pk in self.phonetic_index:
            alias = self.phonetic_index[pk][0]
            return alias, self.alias_index[alias], "fonetico"
        best = process.extractOne(phrase, self.aliases, scorer=fuzz.ratio, score_cutoff=88)
        if best:
            return best[0], self.alias_index[best[0]], "aproximado"
        return None


def _aliases(nombre: str) -> set[str]:
    base = re.sub(r"\(.*?\)", "", nombre).strip()
    base = re.sub(r"\s+AV\.?$", "", base).strip()
    out: set[str] = set()
    if "," in base:
        apellido, nombres = (p.strip() for p in base.split(",", 1))
        nombres_sin_titulo = _TITLES.sub("", nombres).strip()
        out.add(norm(apellido))
        if " DE " in apellido:  # "RAMIREZ DE VELASCO" -> también "VELASCO"
            out.add(norm(apellido.rsplit(" DE ", 1)[1]))
        out.add(norm(f"{nombres} {apellido}"))
        if nombres_sin_titulo and nombres_sin_titulo != nombres:
            out.add(norm(f"{nombres_sin_titulo} {apellido}"))
    else:
        out.add(norm(base))
        if base.startswith("DE ") and re.search(r"\bAV\.?$", nombre):
            out.add(norm(f"AVENIDA {base}"))  # "DE MAYO AV." -> "AVENIDA DE MAYO"
        sin_titulo = _TITLES.sub("", base).strip()
        if sin_titulo and sin_titulo != base:
            out.add(norm(sin_titulo))
    return {a for a in out if len(a) >= 4}


def display_name(tramo: Tramo) -> str:
    """'SCALABRINI ORTIZ, RAUL AV.' -> 'Av. Raul Scalabrini Ortiz'"""
    nombre = re.sub(r"\(.*?\)", "", tramo.nombre).strip()
    es_av = bool(re.search(r"\s+AV\.?$", nombre))
    nombre = re.sub(r"\s+AV\.?$", "", nombre).strip()
    if "," in nombre:
        apellido, nombres = (p.strip() for p in nombre.split(",", 1))
        nombre = f"{nombres} {apellido}"
    words = []
    for w in nombre.split():
        lw = w.lower()
        words.append(lw if lw in {"de", "del", "la", "las", "los", "y"} else lw.capitalize())
    pretty = " ".join(words)
    return f"Av. {pretty}" if es_av else pretty


@lru_cache(maxsize=1)
def get_callejero() -> Callejero:
    return Callejero.load()
