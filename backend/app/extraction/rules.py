"""Extractor determinista (camino rápido y modo mock).

Gazetteer del callejero + patrones del habla rioplatense ("al 800", "casi",
"entre X y Z", "3ro C") + léxicos de dominio. Todo hallazgo guarda el span
del texto que lo respalda: si no hay evidencia, el campo queda vacío.
"""

from __future__ import annotations

import re
from collections import defaultdict

from app.extraction.draft import Direccion, Draft, Hallazgo
from app.geo.callejero import BARRIOS_NORM, Mencion, display_name, get_callejero
from app.knowledge.catalog import SUBCATEGORIA_UMBRAL, Similar, get_retriever
from app.text import norm, split_sentences, word_to_int
from app.transcript import Document

# ---------------------------------------------------------------- léxicos

CATEGORIA_LEXICO: dict[str, tuple[str, ...]] = {
    "INCENDIO_RESCATE": ("fuego", "incendi", "humo", "llama", "prendi", "quema", "bomber", "explot", "ascensor",
                         "atrapad", "rescat", "chispa", "derrame", "cisterna"),
    "ACCIDENTE_VIAL": ("chocó", "choque", "colisi", "atropell", "moto", "taxi", "colectivo", "camión", "vuelc",
                       "volcad", "ciclist", "autopista", "auto ", "autos", "guardarra", "embest", "acoplado"),
    "EMERGENCIA_MEDICA": ("desmay", "respir", "aire", "convuls", "ambulancia", "fractura", "sangr", "dolor",
                          "alérgic", "paciente", "concien", "asma", "broncoesp", "tropez", "cayó", "hinchad",
                          "garganta", "síncope", "transpira", "descompu", "no me contesta", "tirado en el piso"),
    "DEFENSA_CIVIL": ("árbol", "derrumb", "inund", "anegad", "marquesina", "gas", "temporal", "viento",
                      "medianera", "desprend", "colaps"),
    "SERVICIOS_PUBLICOS": ("semáforo", "caño", "agua potable", "cloac", "socavón", "pozo", "cables", "poste",
                           "luz", "bache", "metrobus", "colector"),
    "CONVIVENCIA_SEGURIDAD": ("pelea", "robo", "arma", "disturb", "perro", "agresiv", "vidriera", "botella",
                              "jóvenes", "bozal", "ruido", "amenaz"),
}

# Señales de riesgo de vida inminente => escalan a P1.
SENALES_P1: tuple[tuple[str, str], ...] = (
    (r"atrapad|qued[óo] adentro|adentro qued[óo]|no puede salir|debajo del", "persona atrapada"),
    (r"no respira|no le entra el aire|labios morados|cianosis|se le est[áa] cerrando la garganta|no puede tragar",
     "compromiso respiratorio"),
    (r"no responde|no (?:me |nos )?contesta\b(?! el timbre)|inconsciente|perdi[óo] el conocimiento|no se mueve", "inconsciencia / sin respuesta"),
    (r"convulsi", "convulsión activa"),
    (r"chispe|cable[s]? (?:gruesos? )?(?:cortados?|ca[íi]dos?)", "riesgo eléctrico activo"),
    (r"explot|explosi[óo]n", "explosión"),
    (r"olor a gas|fuga de gas|caño de gas|soplido", "fuga de gas"),
    (r"sangrando (?:mucho|bastante)|sangra a chorros|hemorragia", "hemorragia"),
    (r"humo negro|se prendi[óo] fuego|llamarada", "fuego activo"),
    (r"perdiendo (?:gasoil|nafta|combustible)|derrame", "derrame de combustible"),
    (r"choque en cadena|cruzado en el carril r[áa]pido", "colisión múltiple en vía rápida"),
)

# Frases que indican que una situación de riesgo mejoró o se resolvió más adelante en la llamada.
SALIDA_RE = r"ya (?:sali[óo]|salieron|lo sacaron|la sacaron|los sacaron|est[áa]n? afuera)|lograron salir|no (?:qued[óo]|hay) nadie adentro|nadie qued[óo] adentro"
RESOLUCION: dict[str, str] = {
    "inconsciencia / sin respuesta": r"reaccion[óo]|se despert[óo]|(?:ya )?est[áa] (?:bien|consciente|hablando)|me contest[óo]|recuper[óo] la conciencia",
    "compromiso respiratorio": r"ya respira|respira bien|le entra el aire|(?:ya )?est[áa] bien",
    "persona atrapada": SALIDA_RE,
    "convulsión activa": r"(?:ya )?(?:dej[óo] de convulsionar|se le pas[óo]|par[óo] de temblar)",
}

P4_SENALES = r"hace (?:varios )?d[íi]as|hace una semana|quer[íi]a (?:avisar|informar|reclamar)|no es urgente|reclamo"

RIESGOS_LEXICO: tuple[tuple[str, str], ...] = (
    (r"\bgas\b|garrafa", "Gas / riesgo de explosión"),
    (r"humo", "Humo / inhalación"),
    (r"atrapad|qued[óo] adentro|adentro qued[óo]|debajo del", "Personas atrapadas"),
    (r"cable|chispa|tablero|tensi[óo]n|transformador|subestaci", "Riesgo eléctrico"),
    (r"explot|explosi", "Explosión"),
    (r"gasoil|nafta|combustible|derrame", "Combustible derramado / inflamable"),
    (r"tr[áa]nsito|autos siguen pasando|carril|colectivos y camiones", "Tránsito activo en la zona"),
    (r"\bnenes?\b|\bnenas?\b|chicos|alumnos|ni[ñn][oa]s?|juegos infantiles|menor|hija de \d|hijo de \d", "Menores involucrados"),
    (r"embarazada", "Embarazada"),
    (r"litio|explot[óo] una bater[íi]a", "Baterías de litio"),
    (r"inund|anegad|agua (?:a presi[óo]n|llega)", "Agua / anegamiento"),
    (r"derrumb|colaps|desmoron|socav|cr[áa]ter|pozo", "Colapso estructural"),
    (r"botella|sillas pl[áa]sticas|\barmas?\b|cuchillo", "Elementos contundentes o armas"),
    (r"perro|pitbull|dogo", "Animal agresivo"),
    (r"p[áa]nico", "Crisis de pánico"),
)

ESTADO_LEXICO: tuple[str, ...] = (
    # estados de mejoría (van primero: "ya está bien" no debe partirse)
    r"(?:ya )?est[áa] bien", r"se recuper[óo]", r"reaccion[óo]", r"se despert[óo]", r"est[áa] hablando",
    r"no est[áa] herid[oa]", r"no hay herid[oa]s", r"nadie (?:est[áa] )?herid[oa]", r"ya respira",
    r"est[áa] consciente", r"recuper[óo] la conciencia", r"no responde", r"no se mueve", r"inconsciente",
    r"no respira", r"respira(?: pero)? (?:bien|normal|raro|con dificultad|mal)", r"roncando", r"no (?:me |nos )?contesta\b(?! el timbre)", r"tirad[oa] en el piso", r"sangrando(?: bastante| mucho)?", r"convulsionando", r"se desmay[óo]",
    r"llora de dolor", r"gritando de dolor", r"no se puede incorporar", r"no puede mover la pierna \w+",
    r"le duele mucho la pierna", r"labios morados", r"no le entra el aire", r"mareada?s?", r"en p[áa]nico",
    r"blanca como un papel", r"transpira fr[íi]o", r"no siente las piernas", r"espuma en la boca",
    r"tiene la cara totalmente hinchada", r"no puede tragar", r"se le est[áa] cerrando la garganta",
    r"tiene casco puesto", r"tiraje",
)

_PERSONA_NOUNS = (
    r"hija|hijo|mam[áa]|madre|pap[áa]|padre|abuela|abuelo|esposa|esposo|se[ñn]ora|se[ñn]or|hombre|mujer|"
    r"chico|chica|nene|nena|ni[ñn]o|ni[ñn]a|beb[ée]|joven|delivery|cocinero|conductor|chofer|motociclista|"
    r"ciclista|comensal|paciente|operario|obrero|embarazada|empleado|vecino|vecina|anciano|anciana"
)
_VICTIMA_RE = re.compile(
    rf"\b(?:mi|un|una|el|la)\s+(?P<who>{_PERSONA_NOUNS})\b(?P<rest>[^.,;!?]{{0,25}}?\b(?:de\s+)?(?:unos\s+)?(?P<edad>\d{{1,3}})\s+años)?",
    re.IGNORECASE,
)
_CANTIDAD_RE = re.compile(
    r"\b(?P<n>\d{1,4}|una|un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|veinte)\s+"
    r"(?P<what>personas|chicos|chicas|nenes|alumnos|heridos|ocupantes|j[óo]venes|vecinos|obreros|pacientes|"
    r"v[íi]ctimas|adultos|menores|autos|veh[íi]culos|camionetas)\b",
    re.IGNORECASE,
)
_ROL_RE = re.compile(
    r"\bsoy\s+(?:el|la)\s+(?P<rol>encargad[oa]|director[a]?|due[ñn][oa]|portero|vecin[oa]|personal de \w+|"
    r"m[ée]dic[oa]|enfermer[oa]|maestr[oa]|chofer|conductor[a]?)",
    re.IGNORECASE,
)
_FAMILIAR_RE = re.compile(r"\bmi\s+(hija|hijo|mam[áa]|madre|pap[áa]|padre|abuela|abuelo|esposa|esposo|hermano|hermana)\b", re.I)
_TESTIGO_RE = re.compile(r"\b(estoy (?:corriendo|pasando|caminando|reportando)|reporto|acabo de ver|vi que|desde ac[áa] veo)\b", re.I)
_REFERENCIA_RE = re.compile(
    r"\b(?P<ref>(?:Parque|Plaza|[Ee]staci[óo]n|Hospital|[Ee]scuela(?: primaria)?|colegio|subestaci[óo]n el[ée]ctrica|"
    r"bajo puente|viaducto|ciclov[íi]a|rotonda|predio de canchas(?: de f[úu]tbol \d)?|bodeg[óo]n|restaurante|"
    r"pizzer[íi]a|bar|taller de reparaci[óo]n de \w+(?: \w+)?|obra en construcci[óo]n|edificio|local|kiosco|and[ée]n|"
    r"Plaza \w+)\b(?:\s+(?:[A-ZÁÉÍÓÚ][\wáéíóúñ]*|de la L[íi]nea [A-Z]|L[íi]nea [A-Z]))*)",
)
_HEDGE_RE = re.compile(
    r"\b(parece(?:ría)?|creo que|no sé|no se (?:si|qué|bien)|como (?:unos?|dos|tres|cuatro|cinco)|m[áa]s o menos|"
    r"perd[óo]n|mejor dicho|digo|o sea|capaz)\b|\b(\w{4,}) o (\w{4,})\b",
    re.IGNORECASE,
)
_UNIT_AFTER_NUMBER = {"ANOS", "METROS", "PERSONAS", "MINUTOS", "KM", "PISOS", "CHICOS", "AUTOS", "HORAS", "CM",
                      "KG", "DISPAROS", "MANZANAS", "ALUMNOS", "LITROS", "VECES"}
_ORDINALES = {"primer": "1", "primero": "1", "segundo": "2", "tercer": "3", "tercero": "3", "cuarto": "4",
              "quinto": "5", "sexto": "6", "séptimo": "7", "octavo": "8", "noveno": "9", "décimo": "10", "pb": "PB"}
_PISO_RE = re.compile(r"^\s*,?\s*(?:piso\s+)?(?P<piso>\d{1,2}|primer[o]?|segundo|tercer[o]?|cuarto|quinto|sexto|s[ée]ptimo|octavo|noveno|d[ée]cimo|pb)\s*(?:ro|do|er|to|mo|vo|no|°|º)?\s*(?:piso)?\s*,?\s*"
                      r"(?:dto\.?|depto\.?|departamento)?\s*\"?(?P<depto>[A-Ha-h])?\b")


# ---------------------------------------------------------------- dirección


def _altura_after(doc_text: str, m: Mencion) -> tuple[int, int, int] | None:
    """Busca la altura inmediatamente después de la calle ('Corrientes 1540', 'al 800')."""
    tail = doc_text[m.end : m.end + 30]
    mm = re.match(r"^\s*(?:,\s*)?(?:al\s+|n[°º]\s*|numero\s+|número\s+)?(\d{2,5})\b(?:\s+(\w+))?", tail, re.I)
    if not mm:
        return None
    unit = norm(mm.group(2) or "")
    if unit in _UNIT_AFTER_NUMBER:
        return None
    return int(mm.group(1)), m.end + mm.start(1), m.end + mm.end(1)


def extract_direccion(doc: Document, draft: Draft) -> None:
    cal = get_callejero()
    mentions: list[Mencion] = []
    for idx, turn in enumerate(doc.turns):
        if idx == 0 and turn.speaker == "operador":
            continue  # saludo institucional ("Defensa Civil, dígame")
        base = doc.bases[idx]
        for m in cal.find_mentions(turn.text):
            m.start += base
            m.end += base
            mentions.append(m)
    if not mentions:
        return
    d = Direccion()
    alturas = {id(m): _altura_after(doc.text, m) for m in mentions}
    primary = next((m for m in mentions if alturas[id(m)]), None)
    if primary is None:
        primary = next((m for m in mentions if m.prev in {"EN", "AV", "AVENIDA", "AVDA", "CALLE"}), mentions[0])
    d.calle = primary
    alt = alturas[id(primary)]
    alt_corregida: int | None = None
    if alt:
        corr = re.match(r"^\s*(?:,|\.\.\.)?\s*(?:perd[óo]n|digo|mejor dicho|no)\s*,?\s*(\d{2,5})\b", doc.text[alt[2] : alt[2] + 30], re.I)
        if corr:
            alt_corregida = alt[0]
            alt = (int(corr.group(1)), alt[2] + corr.start(1), alt[2] + corr.end(1))
    d.altura = alt[0] if alt else None
    d.calle_tramos = [cal.pick_tramo(primary.tramos, d.altura, primary.av_cue)]
    d.calle_tramos += [t for t in primary.tramos if t not in d.calle_tramos]

    pi = mentions.index(primary)
    i = pi + 1
    while i < len(mentions):
        m = mentions[i]
        gap = norm(doc.text[mentions[i - 1].end : m.start])
        if gap in {"ENTRE"} or gap.endswith(" ENTRE") or re.search(r"\bENTRE$", gap):
            d.entre.append(m)
            if i + 1 < len(mentions) and norm(doc.text[m.end : mentions[i + 1].start]) == "Y":
                d.entre.append(mentions[i + 1])
                i += 1
        elif re.search(r"(?:^|\s)(Y|CASI|ESQUINA|ESQ)$", gap) and len(gap) < 40:
            d.cruces.append(m)
            d.casi = d.casi or gap.endswith("CASI")
        else:
            d.otras.append(m)
        i += 1
    # Calle mencionada antes que la principal ("en Plaza X, Sarmiento y Bulnes" ya resuelto arriba)
    d.otras.extend(mentions[:pi])
    draft.direccion = d

    calle_display = display_name(d.calle_tramos[0])
    draft.campos["ubicacion.calle"] = Hallazgo(
        value=calle_display,
        spans=[(primary.start, primary.end)],
        method=f"callejero ({primary.match})",
        confidence={"exacto": 0.9, "fonetico": 0.7, "aproximado": 0.6}[primary.match],
        alternatives=[display_name(t) for t in primary.tramos[1:3] if display_name(t) != calle_display],
    )
    if alt:
        draft.campos["ubicacion.altura"] = Hallazgo(
            str(alt[0]), [(alt[1], alt[2])],
            "autocorrección del llamante" if alt_corregida else "número tras la calle",
            0.7 if alt_corregida else 0.9,
            alternatives=[str(alt_corregida)] if alt_corregida else [],
        )
        piso = _PISO_RE.match(doc.text[alt[2] : alt[2] + 25])
        if piso and (piso.group("depto") or "piso" in piso.group(0).lower() or re.search(r"\d\s*(ro|do|er|to|°|º)", piso.group(0))):
            num = _ORDINALES.get(piso.group("piso").lower(), piso.group("piso"))
            val = f"{num}° {piso.group('depto').upper()}" if piso.group("depto") else f"Piso {num}"
            s = alt[2] + piso.start("piso")
            draft.campos["ubicacion.piso_depto"] = Hallazgo(val, [(s, alt[2] + piso.end())], "patrón piso/depto", 0.8)
    if d.cruces:
        names = [display_name(cal.pick_tramo(m.tramos, None, m.av_cue)) for m in d.cruces]
        draft.campos["ubicacion.interseccion"] = Hallazgo(
            " y ".join(names),
            [(m.start, m.end) for m in d.cruces],
            "esquina mencionada" + (" ('casi')" if d.casi else ""),
            0.85 if all(m.match == "exacto" for m in d.cruces) else 0.6,
        )
    if d.entre:
        names = [display_name(cal.pick_tramo(m.tramos, None, m.av_cue)) for m in d.entre]
        draft.campos["ubicacion.entre_calles"] = Hallazgo(
            " y ".join(names), [(m.start, m.end) for m in d.entre], "'entre X y Z'", 0.85
        )


def extract_referencia_barrio(doc: Document, draft: Draft) -> None:
    caller = [(i, t) for i, t in enumerate(doc.turns) if t.speaker == "llamante"]
    refs: list[tuple[str, int, int]] = []
    for idx, turn in caller:
        base = doc.bases[idx]
        for m in _REFERENCIA_RE.finditer(turn.text):
            val = m.group("ref").strip()
            if len(val) >= 3 and val.lower() not in {r[0].lower() for r in refs}:
                refs.append((val, base + m.start("ref"), base + m.end("ref")))
        if "ubicacion.barrio" not in draft.campos:
            names = "|".join(re.escape(b) for b in sorted(BARRIOS_NORM.values(), key=len, reverse=True))
            bm = re.search(rf"\b(?:[Ee]n|[Bb]arrio)\s+({names})\b", turn.text)
            if bm:
                s = base + bm.start(1)
                draft.campos["ubicacion.barrio"] = Hallazgo(bm.group(1), [(s, base + bm.end(1))], "barrio mencionado", 0.8)
    if refs:
        refs = refs[:2]
        draft.campos["ubicacion.referencia"] = Hallazgo(
            "; ".join(r[0] for r in refs), [(r[1], r[2]) for r in refs], "lugar de referencia", 0.75
        )


# ---------------------------------------------------------------- suceso / prioridad


def _caller_spans(doc: Document) -> list[tuple[str, int]]:
    return [(t.text, doc.bases[i]) for i, t in enumerate(doc.turns) if t.speaker == "llamante"]


def classify(doc: Document, draft: Draft, exclude: str | None) -> None:
    caller = doc.caller_text
    low = caller.lower()
    lex: dict[str, float] = defaultdict(float)
    for cat, words in CATEGORIA_LEXICO.items():
        for w in words:
            if w in low:
                lex[cat] += 1.0
    total_lex = sum(lex.values()) or 1.0
    sims: list[Similar] = get_retriever().similares(caller, k=5, exclude=exclude)
    draft.similares = sims
    knn: dict[str, float] = defaultdict(float)
    for s in sims:
        knn[s.caso.categoria] += max(s.similitud, 0.0)
    total_knn = sum(knn.values()) or 1.0
    scores = {c: 0.55 * knn[c] / total_knn + 0.45 * lex[c] / total_lex for c in CATEGORIA_LEXICO}
    draft.categoria_scores = scores
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if not caller.strip() or ranked[0][1] <= 0:
        return
    cat, score = ranked[0]
    margin = score - ranked[1][1]
    conf = min(0.95, 0.45 + score * 0.4 + margin)
    spans = _lexicon_spans(doc, CATEGORIA_LEXICO[cat])[:3]
    draft.campos["suceso.categoria"] = Hallazgo(
        cat, spans, "léxico + casos similares (kNN)", conf, source="inferido",
        alternatives=[c for c, s in ranked[1:3] if s > 0.15],
    )
    same = [s for s in sims if s.caso.categoria == cat]
    if same:
        best = same[0]
        fuerte = best.similitud >= SUBCATEGORIA_UMBRAL
        draft.campos["suceso.subcategoria"] = Hallazgo(
            best.caso.subcategoria, [],
            f"catálogo: {best.caso.id} (sim {best.similitud:.2f})" if fuerte
            else f"orientativa: caso más parecido {best.caso.id} (sim {best.similitud:.2f})",
            min(0.92, best.similitud) if fuerte else min(0.4, best.similitud * 0.6), source="inferido",
            alternatives=[s.caso.subcategoria for s in same[1:3] if s.caso.subcategoria != best.caso.subcategoria],
        )
    # descripción breve: la oración del llamante con más vocabulario del hecho
    best: tuple[int, str, int, int] | None = None
    for text, base in _caller_spans(doc):
        for sent, s, e in split_sentences(text, base):
            hits = sum(1 for w in CATEGORIA_LEXICO[cat] if w in sent.lower())
            if len(sent.split()) >= 5 and hits and (best is None or hits > best[0]):
                best = (hits, sent, s, e)
    if best:
        _, sent, s, e = best
        val = sent if len(sent) <= 160 else sent[:157] + "…"
        draft.campos["suceso.descripcion"] = Hallazgo(val, [(s, e)], "oración clave del relato", 0.7)


def _lexicon_spans(doc: Document, words: tuple[str, ...]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    low = doc.text.lower()
    for w in words:
        pos = low.find(w)
        if pos >= 0 and doc.is_caller(pos):
            end = pos + len(w)
            while end < len(low) and low[end].isalpha():
                end += 1
            spans.append((pos, end))
    return sorted(spans)


def prioritize(doc: Document, draft: Draft) -> None:
    caller = doc.caller_text
    for pattern, label in SENALES_P1:
        for text, base in _caller_spans(doc):
            m = re.search(pattern, text, re.I)
            if m:
                draft.senales_p1.append((label, base + m.start(), base + m.end()))
                break
    # ¿Alguna señal parece resolverse más adelante? Se informa, pero la prioridad NO baja sola.
    for label, _s, e in draft.senales_p1:
        patron = RESOLUCION.get(label)
        if not patron:
            continue
        for mm in re.finditer(patron, doc.text[e:], re.I):
            pos = e + mm.start()
            if doc.is_caller(pos):
                draft.senales_resueltas.append((label, mm.group(0), pos, e + mm.end()))
                break
    cat = draft.campos.get("suceso.categoria")
    ref = [s for s in draft.similares if cat is None or s.caso.categoria == cat.value]
    votes: dict[str, float] = defaultdict(float)
    for s in ref[:3]:
        votes[s.caso.prioridad] += max(s.similitud, 0.01)
    base_p = max(votes, key=votes.get) if votes else "P3"  # type: ignore[arg-type]
    method = f"casos similares ({base_p})"
    conf = 0.55
    if draft.senales_p1:
        senales = sorted({s[0] for s in draft.senales_p1})
        p = "P1"
        method = "señales de riesgo de vida: " + ", ".join(senales)
        conf = min(0.95, 0.7 + 0.08 * len(senales))
        resueltas = {r[0] for r in draft.senales_resueltas}
        if resueltas and resueltas >= set(senales):
            # todas las señales parecen resueltas: se mantiene P1 (nunca se baja solo) pero se pide verificar
            method += " (parecen resueltas más adelante: verificar si corresponde bajar)"
            conf = 0.5
    elif re.search(P4_SENALES, caller, re.I):
        p = "P4"
        method = "sin riesgo actual (reclamo / informativo)"
        conf = 0.6
    else:
        total = sum(votes.values()) or 1.0
        conf = min(0.85, 0.35 + 0.5 * votes.get(base_p, 0) / total)
        if base_p == "P1":
            # P1 exige evidencia explícita de riesgo de vida: sin señal, se propone P2 y se pide verificar.
            p = "P2"
            method = "casos similares sugieren P1 pero no hay señal explícita de riesgo de vida: verificar"
            conf = 0.45
        else:
            p = base_p
    draft.campos["prioridad"] = Hallazgo(
        p, [(s[1], s[2]) for s in draft.senales_p1[:3]], method, conf, source="inferido"
    )


# ---------------------------------------------------------------- personas / llamante / riesgos


def extract_personas(doc: Document, draft: Draft) -> None:
    victimas: list[tuple[str, int, int]] = []
    cantidades: list[tuple[int, str, int, int]] = []
    estados: list[tuple[str, int, int]] = []
    atrapados: list[tuple[int, int]] = []
    for text, base in _caller_spans(doc):
        for m in _VICTIMA_RE.finditer(text):
            who = m.group("who").lower()
            edad = m.group("edad")
            desc = f"{who} ({edad} años)" if edad else who
            if desc not in {v[0] for v in victimas} and not (edad is None and any(v[0].startswith(who) for v in victimas)):
                victimas.append((desc, base + m.start(), base + m.end()))
        for m in _CANTIDAD_RE.finditer(text):
            n = word_to_int(m.group("n"))
            if n is not None:
                cantidades.append((n, m.group("what").lower(), base + m.start(), base + m.end()))
        for pat in ESTADO_LEXICO:
            for m in re.finditer(pat, text, re.I):
                if not any(s <= base + m.start() < e for _, s, e in estados):
                    estados.append((m.group(0).lower(), base + m.start(), base + m.end()))
        m = re.search(SENALES_P1[0][0], text, re.I)
        if m:
            atrapados.append((base + m.start(), base + m.end()))

    personas_cant = [c for c in cantidades if c[1] not in {"autos", "vehículos", "vehiculos", "camionetas"}]
    if personas_cant:
        n, what, s, e = max(personas_cant, key=lambda c: c[0])
        draft.campos["personas.cantidad"] = Hallazgo(f"{n} {what}", [(s, e)], "cantidad explícita", 0.85)
    elif victimas:
        draft.campos["personas.cantidad"] = Hallazgo(
            str(len(victimas)), [(v[1], v[2]) for v in victimas], "personas mencionadas", 0.55, source="inferido"
        )
    if victimas:
        draft.campos["personas.victimas"] = Hallazgo(
            ", ".join(v[0] for v in victimas[:4]), [(v[1], v[2]) for v in victimas[:4]], "personas mencionadas", 0.75
        )
    if estados:
        estados.sort(key=lambda x: x[1])
        ultimo_turno = max(doc.turn_of(s) for _, s, _ in estados)
        actuales = [x for x in estados if doc.turn_of(x[1]) == ultimo_turno]
        previos = [x for x in estados if doc.turn_of(x[1]) != ultimo_turno]
        valor = "; ".join(x[0] for x in actuales[:4])
        metodo = "estado relatado"
        if previos:
            antes = "; ".join(x[0] for x in previos[-3:])
            valor = f"{valor} (antes: {antes})"
            metodo = f"estado actualizado en el turno {ultimo_turno + 1}"
            draft.cambios.append(("personas.estado", antes, "; ".join(x[0] for x in actuales[:4]), actuales[0][1], actuales[-1][2]))
        draft.campos["personas.estado"] = Hallazgo(
            valor, [(x[1], x[2]) for x in actuales[:4]] + [(x[1], x[2]) for x in previos[-3:]], metodo, 0.8
        )
    salidas: list[tuple[int, int]] = []
    for text, base in _caller_spans(doc):
        for mm in re.finditer(SALIDA_RE, text, re.I):
            salidas.append((base + mm.start(), base + mm.end()))
    if salidas and (not atrapados or salidas[-1][0] > atrapados[-1][0]):
        valor = "No (ya salió)" + (" (antes: Sí)" if atrapados else "")
        draft.campos["personas.atrapados"] = Hallazgo(valor, [salidas[-1], *atrapados[:1]], "actualizado durante la llamada" if atrapados else "relato", 0.8)
        if atrapados:
            draft.cambios.append(("personas.atrapados", "Sí", "No", *salidas[-1]))
    elif atrapados:
        draft.campos["personas.atrapados"] = Hallazgo("Sí", atrapados[:2], "mención de atrapamiento", 0.85)

    for text, base in _caller_spans(doc):
        if (m := _ROL_RE.search(text)):
            draft.campos["llamante.rol"] = Hallazgo(m.group("rol").capitalize(), [(base + m.start(), base + m.end())], "se identifica", 0.9)
            break
        if (m := _FAMILIAR_RE.search(text)):
            draft.campos["llamante.rol"] = Hallazgo(f"Familiar ({m.group(1).lower()})", [(base + m.start(), base + m.end())], "relación familiar", 0.8)
            break
        if (m := _TESTIGO_RE.search(text)):
            draft.campos["llamante.rol"] = Hallazgo("Testigo", [(base + m.start(), base + m.end())], "relata como testigo", 0.6)
            break

    riesgos: list[tuple[str, int, int]] = []
    for pattern, label in RIESGOS_LEXICO:
        for text, base in _caller_spans(doc):
            m = re.search(pattern, text, re.I)
            if m and label not in {r[0] for r in riesgos}:
                riesgos.append((label, base + m.start(), base + m.end()))
                break
    if riesgos:
        draft.campos["riesgos"] = Hallazgo(
            "; ".join(r[0] for r in riesgos[:6]), [(r[1], r[2]) for r in riesgos[:6]], "léxico de riesgos", 0.7
        )


def extract_dudas(doc: Document, draft: Draft) -> None:
    for text, base in _caller_spans(doc):
        for m in _HEDGE_RE.finditer(text):
            if m.group(2):  # "X o Y"
                a, b = m.group(2).lower(), m.group(3).lower()
                if a in {"este", "pero", "para", "como", "algo"} or b in {"algo", "para", "pero"}:
                    continue
            draft.dudas.append((m.group(0), base + m.start(), base + m.end()))


# ---------------------------------------------------------------- orquestación


def run_rules(doc: Document, exclude: str | None = None) -> Draft:
    draft = Draft()
    if not doc.turns:
        return draft
    extract_direccion(doc, draft)
    extract_referencia_barrio(doc, draft)
    classify(doc, draft, exclude)
    prioritize(doc, draft)
    extract_personas(doc, draft)
    extract_dudas(doc, draft)
    return draft
