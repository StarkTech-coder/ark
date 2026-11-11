"""Base provider interface for ARK LLM runtimes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, AsyncIterator


@dataclass
class ActiveModelInfo:
    """Metadata about the currently selected runtime/model."""

    provider: str
    model: str
    endpoint: str
    healthy: bool


class LLMProvider(ABC):
    """Abstract runtime-independent LLM provider contract."""

    @abstractmethod
    async def generate_response(
        self,
        *,
        model: str,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        options: dict[str, Any] | None = None,
        response_format: str | None = None,
        request_kwargs: dict[str, Any] | None = None,
    ) -> str:
        """Generate a non-streamed model response."""

    @abstractmethod
    async def stream_response(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        request_kwargs: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Stream model response tokens/chunks."""

    @abstractmethod
    async def list_available_models(self) -> list[str]:
        """List models available in the provider runtime."""

    @abstractmethod
    async def check_provider_health(self) -> bool:
        """Check provider runtime availability/health."""

    @abstractmethod
    async def get_active_model_info(self) -> ActiveModelInfo:
        """Return active model metadata for UI and orchestration layers."""

    @abstractmethod
    async def switch_model(self, model: str) -> ActiveModelInfo:
        """Safely switch active model and return new active model metadata."""

    @abstractmethod
    async def close(self) -> None:
        """Close provider-managed resources, if any."""
