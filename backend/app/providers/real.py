"""Proveedores reales. Se usa HTTP directo (httpx) para no acoplar el
proyecto a SDKs: Anthropic Messages API y cualquier API compatible con
OpenAI Chat Completions (OpenAI, Groq, Gemini, Ollama, vLLM)."""

from __future__ import annotations

import httpx

from app.providers.base import ExtractionRequest, LLMError


def _messages(req: ExtractionRequest) -> list[dict[str, str]]:
    user = req.user
    if req.retry_error:
        user += (
            "\n\nTu respuesta anterior no pasó la validación del esquema: "
            f"{req.retry_error}\nDevolvé SOLO el JSON corregido."
        )
    return [{"role": "user", "content": user}]


class AnthropicProvider:
    is_mock = False

    def __init__(self, api_key: str, model: str, base_url: str, timeout: float) -> None:
        self.name = "anthropic"
        self.model = model
        self._key = api_key
        self._url = base_url.rstrip("/") + "/v1/messages"
        self._timeout = timeout

    async def complete_json(self, req: ExtractionRequest) -> str:
        payload = {
            "model": self.model,
            "max_tokens": 2000,
            "temperature": 0,
            "system": req.system,
            "messages": _messages(req),
        }
        headers = {"x-api-key": self._key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"anthropic: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise LLMError(f"anthropic HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


class OpenAICompatibleProvider:
    is_mock = False

    def __init__(self, name: str, api_key: str | None, model: str, base_url: str, timeout: float) -> None:
        self.name = name
        self.model = model
        self._key = api_key
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._timeout = timeout

    async def complete_json(self, req: ExtractionRequest) -> str:
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": req.system}, *_messages(req)],
        }
        headers = {"content-type": "application/json"}
        if self._key:
            headers["authorization"] = f"Bearer {self._key}"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                r = await client.post(self._url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name}: {type(exc).__name__}") from exc
        if r.status_code != 200:
            raise LLMError(f"{self.name} HTTP {r.status_code}: {r.text[:200]}")
        try:
            return str(r.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"{self.name}: respuesta sin contenido") from exc
