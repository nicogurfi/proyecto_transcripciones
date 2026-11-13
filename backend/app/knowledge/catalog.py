"""Catálogo de protocolos: preguntas e instrucciones estándar por categoría
(criterio general de centros 911) + casos de referencia del dataset
indexados semánticamente para recuperar los más parecidos."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.knowledge.dataset import CasoReferencia, load_dataset
from app.knowledge.embeddings import get_embedder

# Preguntas transversales del interrogatorio (todas las llamadas).
BASE_PREGUNTAS: tuple[tuple[str, bool], ...] = (
    ("Confirmar número de teléfono para rellamada", False),
    ("¿Hay personas heridas? ¿Cuántas?", True),
    ("¿Usted se encuentra en un lugar seguro?", True),
)

PREGUNTAS_CATEGORIA: dict[str, tuple[tuple[str, bool], ...]] = {
    "INCENDIO_RESCATE": (
        ("¿Hay personas atrapadas o que no pudieron salir?", True),
        ("¿Qué es lo que se está quemando?", False),
        ("¿Hay garrafas, gas o materiales peligrosos cerca?", True),
        ("¿El fuego o el humo se propaga a otros ambientes o viviendas?", False),
    ),
    "ACCIDENTE_VIAL": (
        ("¿Cuántos vehículos y personas están involucrados?", False),
        ("¿Hay personas atrapadas dentro de los vehículos?", True),
        ("¿Hay pérdida de combustible, humo o fuego?", True),
    ),
    "EMERGENCIA_MEDICA": (
        ("¿El paciente está consciente y responde?", True),
        ("¿Respira normalmente?", True),
        ("¿Qué edad aproximada tiene el paciente?", False),
        ("¿Tiene dolor en el pecho, sangrado o algún golpe en la cabeza?", True),
        ("¿Tiene antecedentes o toma medicación (cardíaco, diabetes, anticoagulantes)?", False),
    ),
    "DEFENSA_CIVIL": (
        ("¿Hay personas en riesgo inmediato o atrapadas?", True),
        ("¿Hay cables eléctricos o gas comprometidos?", True),
        ("¿La zona fue evacuada o aislada?", False),
    ),
    "SERVICIOS_PUBLICOS": (
        ("¿Hay riesgo inmediato para peatones o vehículos?", True),
        ("¿Desde hace cuánto tiempo ocurre?", False),
    ),
    "CONVIVENCIA_SEGURIDAD": (
        ("¿Se observan armas blancas o de fuego?", True),
        ("¿Los involucrados siguen en el lugar? ¿Hacia dónde se dirigen?", False),
        ("¿Puede describir a los involucrados (ropa, cantidad)?", False),
    ),
}

INSTRUCCIONES_CATEGORIA: dict[str, tuple[str, ...]] = {
    "INCENDIO_RESCATE": (
        "Salir del lugar y no volver a entrar por ningún motivo.",
        "Si hay humo, desplazarse agachado y cerrar las puertas al salir.",
    ),
    "ACCIDENTE_VIAL": (
        "No mover a los heridos salvo peligro inminente (fuego, tránsito).",
        "Señalizar la zona con balizas o luces para evitar otro impacto.",
    ),
    "EMERGENCIA_MEDICA": (
        "No darle de comer ni de beber al paciente.",
        "No dejarlo solo; avisar de inmediato si deja de respirar o de responder.",
    ),
    "DEFENSA_CIVIL": (
        "Alejarse de la zona afectada y no acercarse a cables caídos.",
    ),
    "SERVICIOS_PUBLICOS": (
        "Mantener a peatones y vehículos alejados del sector afectado.",
    ),
    "CONVIVENCIA_SEGURIDAD": (
        "No intervenir; resguardarse en un lugar seguro.",
        "Observar a distancia para aportar descripción y dirección de huida.",
    ),
}

# Similitud mínima para aplicar el protocolo específico de una subcategoría del
# catálogo. Medido leave-one-out: casos de subcategorías distintas llegan a ~0.68,
# por eso por debajo de 0.75 solo se usa el protocolo de la categoría.
SUBCATEGORIA_UMBRAL = 0.75

DESCRIPCION_PRIORIDAD: dict[str, str] = {
    "P1": "Riesgo de vida inminente",
    "P2": "Riesgo potencial / urgente",
    "P3": "Urgencia sin riesgo de vida",
    "P4": "No urgente / informativo",
}


@dataclass(frozen=True, slots=True)
class Similar:
    caso: CasoReferencia
    similitud: float


class Retriever:
    """Vector store en memoria (numpy): 30 casos no justifican una base vectorial."""

    def __init__(self) -> None:
        self.casos = load_dataset()
        self.embedder = get_embedder()
        self.matrix = self.embedder.embed([c.caller_text for c in self.casos])

    def similares(self, text: str, k: int = 3, exclude: str | None = None) -> list[Similar]:
        if not text.strip():
            return []
        q = self.embedder.embed([text])[0]
        sims = self.matrix @ q
        order = np.argsort(-sims)
        out: list[Similar] = []
        for idx in order:
            caso = self.casos[int(idx)]
            if caso.id == exclude:
                continue
            out.append(Similar(caso, float(sims[idx])))
            if len(out) == k:
                break
        return out


@lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()


_question_cache: dict[str, np.ndarray] = {}


def embed_questions(questions: list[str]) -> np.ndarray:
    missing = [q for q in questions if q not in _question_cache]
    if missing:
        vecs = get_embedder().embed(missing)
        for q, v in zip(missing, vecs, strict=True):
            _question_cache[q] = v
    if not questions:
        return np.zeros((0, 1), dtype=np.float32)
    return np.stack([_question_cache[q] for q in questions])
