"""Doble verificación online con el normalizador oficial USIG (GCBA) y
caché local para funcionar sin conexión (precargada para el dataset)."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from typing import Any

import httpx

from app.config import DATA_DIR, get_settings
from app.text import norm

log = logging.getLogger(__name__)

NORMALIZAR_URL = "https://servicios.usig.buenosaires.gob.ar/normalizar/"
DATOS_UTILES_URL = "https://ws.usig.buenosaires.gob.ar/datos_utiles"
CACHE_FILE = DATA_DIR / "geocache.json"


@dataclass(slots=True)
class UsigResultado:
    direccion: str
    lat: float
    lon: float
    barrio: str | None = None
    comuna: str | None = None
    comisaria_vecinal: str | None = None
    fuente: str = "usig"


class UsigClient:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}
        if CACHE_FILE.exists():
            self._cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        self._offline_until = 0.0  # tras un error de red se evita reintentar durante un rato

    @staticmethod
    def key(query: str) -> str:
        return norm(query)

    async def geocode(self, query: str, con_altura: bool, allow_network: bool = True) -> UsigResultado | None:
        k = self.key(query)
        settings = get_settings()
        if k in self._cache:
            return _from_cache(self._cache[k])
        if not allow_network or not settings.usig_enabled or time.monotonic() < self._offline_until:
            return None
        try:
            async with httpx.AsyncClient(timeout=settings.usig_timeout_s) as client:
                r = await client.get(
                    NORMALIZAR_URL, params={"direccion": query, "geocodificar": "TRUE", "srid": "4326"}
                )
                r.raise_for_status()
                data = r.json()
                caba = [d for d in data.get("direccionesNormalizadas", []) if d.get("cod_partido") == "caba"]
                if not caba or "coordenadas" not in caba[0]:
                    return None
                d = caba[0]
                res = UsigResultado(
                    direccion=d["direccion"],
                    lat=float(d["coordenadas"]["y"]),
                    lon=float(d["coordenadas"]["x"]),
                )
                if con_altura and d.get("altura"):
                    try:
                        du = await client.get(
                            DATOS_UTILES_URL, params={"calle": d["nombre_calle"], "altura": d["altura"]}
                        )
                        info = du.json()
                        res.barrio = info.get("barrio")
                        res.comuna = info.get("comuna")
                        res.comisaria_vecinal = info.get("comisaria_vecinal")
                    except (httpx.HTTPError, ValueError):
                        pass
                self._cache[k] = asdict(res) | {"fuente": "cache"}
                return res
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("USIG no disponible (%s: %s); se continúa offline", type(exc).__name__, exc)
            # Si falla por red, no se reintenta en cada request (el operador no espera timeouts).
            if isinstance(exc, httpx.TransportError):
                self._offline_until = time.monotonic() + 60
            return None

    def dump_cache(self) -> None:
        CACHE_FILE.write_text(json.dumps(self._cache, ensure_ascii=False, indent=1), encoding="utf-8")


def _from_cache(d: dict[str, Any]) -> UsigResultado:
    return UsigResultado(
        direccion=d["direccion"],
        lat=d["lat"],
        lon=d["lon"],
        barrio=d.get("barrio"),
        comuna=d.get("comuna"),
        comisaria_vecinal=d.get("comisaria_vecinal"),
        fuente="cache",
    )


_client: UsigClient | None = None


def get_usig() -> UsigClient:
    global _client
    if _client is None:
        _client = UsigClient()
    return _client
