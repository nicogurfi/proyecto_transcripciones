"""Vectorización de texto.

- Primario: `paraphrase-multilingual-MiniLM-L12-v2` vía fastembed (ONNX, CPU,
  ~220 MB, se descarga en el build de Docker para funcionar offline).
- Fallback: embedding por hashing de n-gramas de caracteres (determinista,
  sin dependencias). Se usa si el modelo no está disponible.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.config import get_settings
from app.text import norm

log = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Embedder(Protocol):
    name: str
    # Umbral de similitud a partir del cual dos textos "hablan de lo mismo".
    semantic_threshold: float

    def embed(self, texts: list[str]) -> np.ndarray: ...


def _l2(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


class HashingEmbedder:
    name = "hashing-char-ngrams"
    semantic_threshold = 0.42
    dim = 4096

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            t = f" {norm(text)} "
            feats: dict[int, float] = {}
            for n in (3, 4, 5):
                for i in range(len(t) - n + 1):
                    h = int.from_bytes(hashlib.blake2b(t[i : i + n].encode(), digest_size=4).digest(), "little")
                    feats[h % self.dim] = feats.get(h % self.dim, 0.0) + 1.0
            for idx, v in feats.items():
                out[row, idx] = 1.0 + np.log(v)
        return _l2(out)


class FastEmbedEmbedder:
    name = MODEL_NAME
    semantic_threshold = 0.5

    def __init__(self) -> None:
        from fastembed import TextEmbedding

        settings = get_settings()
        self._model = TextEmbedding(MODEL_NAME, cache_dir=str(settings.models_dir))

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        return _l2(np.array(list(self._model.embed(texts)), dtype=np.float32))


@lru_cache(maxsize=1)
def get_embedder() -> Embedder:
    if not get_settings().embeddings_enabled:
        return HashingEmbedder()
    try:
        emb = FastEmbedEmbedder()
        emb.embed(["prueba"])
        log.info("Embeddings: %s", MODEL_NAME)
        return emb
    except Exception as exc:  # noqa: BLE001 - cualquier fallo de modelo => fallback determinista
        log.warning("Modelo de embeddings no disponible (%s). Se usa fallback por hashing.", exc)
        return HashingEmbedder()


if __name__ == "__main__" and "--download" in sys.argv:
    # Usado en el Dockerfile para hornear el modelo en la imagen.
    FastEmbedEmbedder().embed(["descarga del modelo"])
    print(f"Modelo {MODEL_NAME} descargado en {get_settings().models_dir}")
