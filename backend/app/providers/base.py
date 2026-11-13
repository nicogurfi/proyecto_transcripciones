"""Patrón de proveedor dual: real (LLM) o simulado (mock determinista)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ExtractionRequest:
    system: str
    user: str
    mock_response: str  # respuesta determinista derivada de las reglas (solo la usa el mock)
    retry_error: str | None = None


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    name: str
    model: str | None
    is_mock: bool

    async def complete_json(self, req: ExtractionRequest) -> str:
        """Devuelve el texto crudo del modelo (se valida aguas abajo)."""
        ...
