"""Precarga la caché de geocodificación (USIG) para el dataset y los casos
demo, de modo que el mapa funcione aun sin conexión a internet.

Uso: python -m scripts.build_geocache   (requiere internet)
"""

from __future__ import annotations

import asyncio
import json

from app.analysis.pipeline import analizar
from app.config import DATA_DIR
from app.geo.usig import get_usig
from app.knowledge.dataset import load_dataset
from app.schemas import AnalisisRequest, Turn


async def main() -> None:
    reqs = [AnalisisRequest(texto=c.transcripcion, timestamp=c.timestamp, usar_llm=False) for c in load_dataset()]
    for d in json.loads((DATA_DIR / "demo_casos.json").read_text(encoding="utf-8")):
        reqs.append(AnalisisRequest(turnos=[Turn(**t) for t in d["turnos"]], timestamp=d["timestamp"], usar_llm=False))
    ok = 0
    for req in reqs:
        async for a in analizar(req):
            if a.fase == "final" and a.geo.lat is not None:
                ok += 1
    get_usig().dump_cache()
    print(f"Geocodificadas {ok}/{len(reqs)} direcciones -> {DATA_DIR / 'geocache.json'}")


if __name__ == "__main__":
    asyncio.run(main())
