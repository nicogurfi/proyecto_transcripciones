"""Persistencia mínima en SQLite (stdlib): cartas derivadas, correcciones
del operador (dataset de mejora continua) y resultados de simulacros."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

from app.config import get_settings

_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS cartas (
    numero TEXT PRIMARY KEY,
    creada TEXT NOT NULL,
    prioridad TEXT,
    categoria TEXT,
    direccion TEXT,
    payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS correcciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    carta TEXT NOT NULL,
    campo TEXT NOT NULL,
    sugerido TEXT,
    final TEXT,
    confianza REAL,
    proveedor TEXT,
    caso_ref TEXT
);
CREATE TABLE IF NOT EXISTS simulacros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creado TEXT DEFAULT CURRENT_TIMESTAMP,
    caso_id TEXT NOT NULL,
    dificultad TEXT,
    porcentaje INTEGER,
    tiempo_segundos INTEGER,
    payload TEXT NOT NULL
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    path = get_settings().db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(SCHEMA)
            yield conn
            conn.commit()
        finally:
            conn.close()


def next_carta_number(prefix: str) -> str:
    with connect() as c:
        n = c.execute("SELECT COUNT(*) FROM cartas WHERE numero LIKE ?", (f"{prefix}%",)).fetchone()[0]
    return f"{prefix}{n + 1:04d}"


def save_carta(carta: dict[str, Any], correcciones: list[tuple[str, str | None, str | None, float | None]],
               proveedor: str | None, caso_ref: str | None) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO cartas(numero, creada, prioridad, categoria, direccion, payload) VALUES (?,?,?,?,?,?)",
            (carta["numero"], carta["creada"], carta["prioridad"], carta["categoria"], carta["direccion"],
             json.dumps(carta, ensure_ascii=False)),
        )
        c.executemany(
            "INSERT INTO correcciones(carta, campo, sugerido, final, confianza, proveedor, caso_ref) VALUES (?,?,?,?,?,?,?)",
            [(carta["numero"], campo, sug, fin, conf, proveedor, caso_ref) for campo, sug, fin, conf in correcciones],
        )


def list_cartas(limit: int = 50) -> list[dict[str, Any]]:
    with connect() as c:
        rows = c.execute("SELECT payload FROM cartas ORDER BY creada DESC LIMIT ?", (limit,)).fetchall()
    return [json.loads(r["payload"]) for r in rows]


def correcciones_stats() -> list[dict[str, Any]]:
    with connect() as c:
        rows = c.execute(
            "SELECT campo, COUNT(*) AS n, AVG(confianza) AS conf FROM correcciones GROUP BY campo ORDER BY n DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def save_simulacro(caso_id: str, dificultad: str, porcentaje: int, tiempo: int, payload: dict[str, Any]) -> None:
    with connect() as c:
        c.execute(
            "INSERT INTO simulacros(caso_id, dificultad, porcentaje, tiempo_segundos, payload) VALUES (?,?,?,?,?)",
            (caso_id, dificultad, porcentaje, tiempo, json.dumps(payload, ensure_ascii=False)),
        )


def simulacro_stats() -> dict[str, Any]:
    with connect() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n, AVG(porcentaje) AS prom, AVG(tiempo_segundos) AS t FROM simulacros"
        ).fetchone()
        ult = c.execute(
            "SELECT caso_id, porcentaje, tiempo_segundos, creado FROM simulacros ORDER BY id DESC LIMIT 10"
        ).fetchall()
    return {
        "sesiones": row["n"],
        "promedio": round(row["prom"] or 0),
        "tiempo_promedio": round(row["t"] or 0),
        "ultimos": [dict(r) for r in ult],
    }
