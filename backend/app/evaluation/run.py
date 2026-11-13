"""Evaluación leave-one-out sobre el dataset.

Para cada caso se excluye ese mismo caso del catálogo (no hay fuga de la
respuesta) y se compara la ficha generada contra la referencia.

Uso:  python -m app.evaluation.run [--llm]
  --llm  usa el proveedor configurado (por defecto solo la fase de reglas/mock)
"""

from __future__ import annotations

import asyncio
import re
import statistics
import sys
import time

from rapidfuzz import fuzz

from app.analysis.pipeline import analizar
from app.geo.callejero import get_callejero
from app.knowledge.dataset import load_dataset
from app.schemas import AnalisisRequest, Analisis
from app.text import norm


def _misma_calle(a: str | None, b: str) -> bool:
    if not a:
        return False
    cal = get_callejero()
    la, lb = cal.lookup(a), cal.lookup(re.sub(r"\(.*?\)", "", b))
    if la and lb:
        return bool({t.cod for t in la[1]} & {t.cod for t in lb[1]})
    return fuzz.token_set_ratio(norm(a), norm(b)) >= 85


async def evaluar(usar_llm: bool) -> str:
    rows = []
    lat_rapida: list[int] = []
    lat_final: list[int] = []
    for c in load_dataset():
        req = AnalisisRequest(texto=c.transcripcion, timestamp=c.timestamp, caso_ref=c.id, usar_llm=usar_llm)
        fases: list[Analisis] = []
        t0 = time.perf_counter()
        async for a in analizar(req):
            fases.append(a)
            if a.fase == "rapida":
                lat_rapida.append(int((time.perf_counter() - t0) * 1000))
        lat_final.append(int((time.perf_counter() - t0) * 1000))
        f = fases[-1].ficha
        alt_gt = re.search(r"\d{2,5}", c.altura)
        alt_dicha = alt_gt is not None and alt_gt.group(0) in c.transcripcion
        cruces_gt = [x.strip() for x in re.split(r"\s+y\s+|/", c.interseccion) if x.strip()]
        cruces_dichos = [x for x in cruces_gt if norm(x.split()[-1]) in norm(c.transcripcion)]
        cruces_resp = [x.strip() for x in re.split(r"\s+y\s+", " y ".join(filter(None, [f.ubicacion.interseccion.value, f.ubicacion.entre_calles.value]))) if x.strip()]
        no_dichas = [x for x in cruces_resp if not any(_misma_calle(x, g) for g in cruces_gt)]
        p_pred = f.prioridad.value
        rows.append({
            "calle": _misma_calle(f.ubicacion.calle.value, c.calle),
            "altura": (f.ubicacion.altura.value == alt_gt.group(0)) if alt_dicha and alt_gt else None,
            "cruce": any(_misma_calle(x, g) for x in cruces_resp for g in cruces_dichos) if cruces_dichos else None,
            "cruce_extra": len(no_dichas),
            "categoria": f.suceso.categoria.value == c.categoria,
            "prioridad": p_pred == c.prioridad,
            "prioridad_1": bool(p_pred) and abs(int(p_pred[1]) - int(c.prioridad[1])) <= 1,
            "sub_estimada": bool(p_pred) and int(p_pred[1]) > int(c.prioridad[1]),
        })

    def pct(key: str) -> str:
        vals = [r[key] for r in rows if r[key] is not None]
        return f"{100 * sum(vals) / len(vals):.0f}% ({sum(vals)}/{len(vals)})"

    def p95(xs: list[int]) -> int:
        return sorted(xs)[max(0, int(len(xs) * 0.95) - 1)]

    lines = [
        f"| Métrica (leave-one-out, n={len(rows)}) | Resultado |",
        "|---|---|",
        f"| Calle principal correcta | {pct('calle')} |",
        f"| Altura correcta (cuando fue dicha) | {pct('altura')} |",
        f"| Esquina/entre calles capturada (cuando fue dicha) | {pct('cruce')} |",
        f"| Calles agregadas que no estaban en la referencia | {sum(r['cruce_extra'] for r in rows)} |",
        f"| Categoría correcta | {pct('categoria')} |",
        f"| Prioridad exacta | {pct('prioridad')} |",
        f"| Prioridad a ±1 nivel | {pct('prioridad_1')} |",
        f"| Prioridad subestimada (más leve que la referencia) | {pct('sub_estimada')} |",
        f"| Latencia fase rápida p50 / p95 | {statistics.median(lat_rapida):.0f} ms / {p95(lat_rapida)} ms |",
        f"| Latencia fase final p50 / p95 | {statistics.median(lat_final):.0f} ms / {p95(lat_final)} ms |",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(asyncio.run(evaluar("--llm" in sys.argv)))
