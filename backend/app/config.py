"""Configuración por variables de entorno. Sin secretos en el repo:
las claves se leen solo del entorno (ver `.env.example`)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"

_DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-haiku-5-5",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.0-flash",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3.1:8b",
}

_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://host.docker.internal:11434/v1",
}

_KEY_VARS: dict[str, str] = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str | None
    llm_api_key: str | None
    llm_base_url: str | None
    llm_timeout_s: float
    usig_enabled: bool
    usig_timeout_s: float
    db_path: Path
    models_dir: Path
    embeddings_enabled: bool
    warnings: list[str] = field(default_factory=list)


def _resolve_provider() -> tuple[str, list[str]]:
    warnings: list[str] = []
    requested = _env("LLM_PROVIDER").lower()
    if requested and requested != "auto":
        if requested == "mock":
            return "mock", warnings
        if requested not in _DEFAULT_MODELS:
            warnings.append(f"LLM_PROVIDER='{requested}' desconocido: se usa modo mock.")
            return "mock", warnings
        key_var = _KEY_VARS.get(requested)
        if key_var and not _env(key_var):
            warnings.append(f"LLM_PROVIDER={requested} pero falta {key_var}: se usa modo mock.")
            return "mock", warnings
        return requested, warnings
    # auto-detección: primer proveedor con credencial
    for provider, key_var in _KEY_VARS.items():
        if _env(key_var):
            return provider, warnings
    return "mock", warnings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    provider, warnings = _resolve_provider()
    key_var = _KEY_VARS.get(provider)
    return Settings(
        llm_provider=provider,
        llm_model=(_env("LLM_MODEL") or _DEFAULT_MODELS.get(provider)) if provider != "mock" else None,
        llm_api_key=_env(key_var) if key_var else None,
        llm_base_url=(_env("LLM_BASE_URL") or _env("OLLAMA_BASE_URL") or _BASE_URLS.get(provider))
        if provider != "mock"
        else None,
        llm_timeout_s=float(_env("LLM_TIMEOUT_SECONDS", "12")),
        usig_enabled=_env("USIG_ENABLED", "true").lower() in {"1", "true", "yes", "si"},
        usig_timeout_s=float(_env("USIG_TIMEOUT_SECONDS", "2.5")),
        db_path=Path(_env("DB_PATH", str(Path(__file__).parent.parent / "copiloto.db"))),
        models_dir=Path(_env("MODELS_DIR", str(Path(__file__).parent.parent / ".models"))),
        embeddings_enabled=_env("EMBEDDINGS_ENABLED", "true").lower() in {"1", "true", "yes", "si"},
        warnings=warnings,
    )
