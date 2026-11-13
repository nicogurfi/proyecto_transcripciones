"""Módulo de simulacro: el operador resuelve casos SIN copiloto (evita la
atrofia de habilidades) y se lo evalúa contra la referencia del dataset.
Las variantes "ruidosas" simulan errores de transcripción y modismos."""

from __future__ import annotations

import random
import re

from rapidfuzz import fuzz

from app import db
from app.extraction.rules import run_rules
from app.geo.callejero import get_callejero
from app.knowledge.catalog import embed_questions
from app.knowledge.dataset import CasoReferencia, get_caso, load_dataset, strip_answer
from app.knowledge.embeddings import get_embedder
from app.schemas import SimulacroCaso, SimulacroItem, SimulacroRespuesta, SimulacroResultado, Turn
from app.text import content_stems, norm
from app.transcript import Document, parse_raw_transcript

_RUIDO_FONETICO = ((r"v", "b"), (r"z", "s"), (r"ll", "y"), (r"ce", "se"), (r"h", ""))
_MULETILLAS = ("eh", "este", "o sea", "nada", "viste")


def _ruido(text: str, seed: int) -> str:
    rnd = random.Random(seed)
    words = text.split()
    out: list[str] = []
    for w in words:
        if len(w) > 4 and w[:1].isupper() and rnd.random() < 0.5:
            for a, b in _RUIDO_FONETICO:
                if a in w.lower():
                    w = re.sub(a, b, w, count=1, flags=re.I)
                    break
        out.append(w)
        if rnd.random() < 0.08:
            out.append(rnd.choice(_MULETILLAS) + ",")
    noisy = " ".join(out).lower()
    return re.sub(r"[¿¡]", "", noisy)


def nuevo_caso(dificultad: str, excluir: list[str]) -> SimulacroCaso:
    casos = [c for c in load_dataset() if c.id not in set(excluir)] or list(load_dataset())
    caso = random.choice(casos)
    turns = parse_raw_transcript(caso.transcripcion)
    if dificultad == "ruidosa":
        seed = sum(map(ord, caso.id))
        turns = [Turn(speaker=t.speaker, text=_ruido(t.text, seed) if t.speaker == "llamante" else t.text) for t in turns]
    return SimulacroCaso(caso_id=caso.id, turnos=turns, timestamp=caso.timestamp, origen=caso.origen, dificultad=dificultad)  # type: ignore[arg-type]


def _misma_calle(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    cal = get_callejero()
    la, lb = cal.lookup(a), cal.lookup(re.sub(r"\(.*?\)", "", b))
    if la and lb:
        return bool({t.cod for t in la[1]} & {t.cod for t in lb[1]})
    return fuzz.token_set_ratio(norm(a), norm(b)) >= 85


def evaluar(r: SimulacroRespuesta) -> SimulacroResultado:
    caso = get_caso(r.caso_id)
    if caso is None:
        raise KeyError(r.caso_id)
    items: list[SimulacroItem] = []

    def item(criterio: str, puntos: float, maximo: float, detalle: str, esperado: str | None, respondido: str | None) -> None:
        items.append(SimulacroItem(criterio=criterio, puntaje=round(puntos, 1), maximo=maximo, detalle=detalle, esperado=esperado, respondido=respondido))

    ok = _misma_calle(r.calle, caso.calle)
    item("Calle", 25 if ok else 0, 25, "Correcta" if ok else "No coincide con la referencia", caso.calle, r.calle)

    gt_alt = re.search(r"\d{2,5}", caso.altura)
    if gt_alt and gt_alt.group(0) in caso.transcripcion:
        resp = re.sub(r"\D", "", r.altura or "")
        ok_alt = bool(resp) and abs(int(resp) - int(gt_alt.group(0))) <= 50
        item("Altura", 10 if ok_alt else 0, 10, "Correcta" if ok_alt else "Incorrecta o faltante", caso.altura, r.altura)

    cruces_gt = [c.strip() for c in re.split(r"\s+y\s+|/", caso.interseccion) if c.strip()]
    dichas = [c for c in cruces_gt if fuzz.partial_ratio(norm(c.split()[-1]), norm(caso.transcripcion)) >= 90]
    if dichas:
        resp_cruces = [c.strip() for c in re.split(r"\s+y\s+|,|/", r.interseccion or "") if c.strip()]
        hit = any(_misma_calle(a, b) for a in resp_cruces for b in dichas)
        item("Esquina / entre calles", 10 if hit else 0, 10, "Correcta" if hit else "No se registró la esquina mencionada", " y ".join(dichas), r.interseccion)

    ok_cat = (r.categoria or "") == caso.categoria
    item("Tipo de hecho", 15 if ok_cat else 0, 15, "Correcto" if ok_cat else "Distinto a la referencia", caso.categoria, r.categoria)

    if r.prioridad and r.prioridad[1:].isdigit():
        diff = abs(int(r.prioridad[1:]) - int(caso.prioridad[1:]))
        pts = 15 if diff == 0 else (7 if diff == 1 else 0)
        det = "Exacta" if diff == 0 else ("Subestimada" if int(r.prioridad[1:]) > int(caso.prioridad[1:]) else "Sobreestimada")
    else:
        pts, det = 0, "Sin prioridad"
    item("Prioridad", pts, 15, det, caso.prioridad, r.prioridad)

    gt_q = [strip_answer(q) for q in caso.preguntas_pendientes]
    resp_q = [q for q in r.preguntas_pendientes if q.strip()]
    cubiertas = 0
    if gt_q and resp_q:
        gv, rv = embed_questions(gt_q), get_embedder().embed(resp_q)
        sims = gv @ rv.T
        thr = get_embedder().semantic_threshold
        for i, q in enumerate(gt_q):
            if sims[i].max() >= thr or max(fuzz.token_set_ratio(q.lower(), x.lower()) for x in resp_q) >= 70:
                cubiertas += 1
    item("Preguntas pendientes identificadas", 15 * cubiertas / max(len(gt_q), 1), 15,
         f"{cubiertas}/{len(gt_q)} preguntas clave cubiertas", " | ".join(gt_q), " | ".join(resp_q) or None)

    gt_st = set(content_stems(caso.instrucciones))
    resp_st = set(content_stems(r.instrucciones or ""))
    overlap = len(gt_st & resp_st) / max(len(gt_st), 1)
    item("Instrucciones de pre-arribo", 10 * min(1.0, overlap / 0.35), 10,
         f"Cobertura de conceptos clave: {int(overlap * 100)}%", caso.instrucciones, r.instrucciones)

    total = sum(i.puntaje for i in items)
    maximo = sum(i.maximo for i in items)
    pct = int(round(100 * total / maximo)) if maximo else 0
    draft = run_rules(Document.from_turns(parse_raw_transcript(caso.transcripcion)), exclude=caso.id)
    copiloto = {k: (draft.campos[k].value if k in draft.campos else None) for k in ("ubicacion.calle", "ubicacion.altura", "suceso.categoria", "prioridad")}
    comentario = (
        "Excelente: resolviste el caso con criterio propio." if pct >= 85 else
        "Bien. Revisá los criterios marcados en rojo." if pct >= 60 else
        "Repasá el protocolo de este tipo de hecho y volvé a intentarlo."
    )
    if r.tiempo_segundos and r.tiempo_segundos > 90:
        comentario += f" Tiempo: {r.tiempo_segundos}s (objetivo < 90s)."
    res = SimulacroResultado(
        caso_id=caso.id, puntaje=round(total, 1), maximo=maximo, porcentaje=pct, items=items,
        copiloto=copiloto, referencia=_referencia(caso), comentario=comentario,
    )
    db.save_simulacro(caso.id, r.dificultad, pct, r.tiempo_segundos, res.model_dump())
    return res


def _referencia(c: CasoReferencia) -> dict[str, str]:
    return {
        "subcategoria": c.subcategoria,
        "direccion": f"{c.calle} {c.altura} ({c.interseccion}) – {c.barrio}",
        "instrucciones": c.instrucciones,
        "riesgos": c.riesgos,
        "recursos": c.recursos,
        "notas": c.notas,
    }
