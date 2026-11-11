"""Factory utilities for ARK LLM providers."""

from __future__ import annotations

from llm.config import get_active_chat_model, get_ollama_host, get_provider_name
from llm.providers.base import LLMProvider
from llm.providers.ollama_provider import OllamaProvider


def get_chat_provider() -> LLMProvider:
    """Build the configured chat provider. Falls back to Ollama."""
    provider_name = get_provider_name()

    if provider_name == "ollama":
        return OllamaProvider(
            host=get_ollama_host(),
            default_model=get_active_chat_model(),
        )

    # Fallback keeps ARK operational if an unsupported provider is configured.
    return OllamaProvider(
        host=get_ollama_host(),
        default_model=get_active_chat_model(),
    )
