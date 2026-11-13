"""Selección del proveedor según configuración (dual provider)."""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.providers.base import ExtractionRequest, LLMProvider
from app.providers.real import AnthropicProvider, OpenAICompatibleProvider


class MockProvider:
    """Modo simulado: determinista, offline y gratuito. Devuelve el mismo
    esquema que un LLM, construido por el extractor de reglas."""

    name = "mock"
    model: str | None = "reglas-deterministas"
    is_mock = True

    async def complete_json(self, req: ExtractionRequest) -> str:
        return req.mock_response


@lru_cache(maxsize=1)
def get_provider() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "mock" or not s.llm_model or not s.llm_base_url:
        return MockProvider()
    if s.llm_provider == "anthropic":
        return AnthropicProvider(s.llm_api_key or "", s.llm_model, s.llm_base_url, s.llm_timeout_s)
    return OpenAICompatibleProvider(s.llm_provider, s.llm_api_key, s.llm_model, s.llm_base_url, s.llm_timeout_s)
