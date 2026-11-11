"""Ollama provider adapter implementing ARK's LLM provider interface."""

from __future__ import annotations

from typing import Any, AsyncIterator

import httpx
from ollama import AsyncClient

from llm.providers.base import ActiveModelInfo, LLMProvider


class ProviderRuntimeError(RuntimeError):
    """Raised when provider runtime operations fail."""


class OllamaProvider(LLMProvider):
    """Ollama runtime adapter for chat/generation/model discovery operations."""

    def __init__(self, host: str, default_model: str):
        self._host = host
        self._default_model = default_model
        self._active_model = default_model
        self._client = AsyncClient(host=host)

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
        options = options or {}
        request_kwargs = request_kwargs or {}
        target_model = model or self._active_model

        if messages is not None:
            payload: dict[str, Any] = {
                "model": target_model,
                "messages": messages,
                "options": options,
                "stream": False,
            }
            if response_format:
                payload["format"] = response_format
            payload.update(request_kwargs)

            try:
                response = await self._client.chat(**payload)
            except Exception as e:
                raise ProviderRuntimeError(
                    f"Ollama chat request failed for model '{target_model}': {e}"
                ) from e

            if not isinstance(response, dict):
                raise ProviderRuntimeError(
                    "Ollama chat response is not a JSON object"
                )

            content = (response.get("message", {}) or {}).get("content", "")
            if not isinstance(content, str):
                raise ProviderRuntimeError(
                    "Ollama chat response content is missing or invalid"
                )
            return content

        payload = {
            "model": target_model,
            "prompt": prompt or "",
            "options": options,
            "stream": False,
        }
        if response_format:
            payload["format"] = response_format
        payload.update(request_kwargs)

        try:
            response = await self._client.generate(**payload)
        except Exception as e:
            raise ProviderRuntimeError(
                f"Ollama generate request failed for model '{target_model}': {e}"
            ) from e

        if not isinstance(response, dict):
            raise ProviderRuntimeError("Ollama generate response is not a JSON object")

        text = response.get("response", "")
        if not isinstance(text, str):
            raise ProviderRuntimeError(
                "Ollama generate response text is missing or invalid"
            )
        return text

    async def stream_response(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        request_kwargs: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        options = options or {}
        request_kwargs = request_kwargs or {}

        payload: dict[str, Any] = {
            "model": model or self._active_model,
            "messages": messages,
            "options": options,
            "stream": True,
        }
        payload.update(request_kwargs)

        try:
            stream = await self._client.chat(**payload)
        except Exception as e:
            raise ProviderRuntimeError(
                f"Ollama stream request failed for model '{payload['model']}': {e}"
            ) from e

        async for chunk in stream:
            if not isinstance(chunk, dict):
                raise ProviderRuntimeError("Ollama stream chunk is not a JSON object")

            token = (chunk.get("message", {}) or {}).get("content", "")
            if token and not isinstance(token, str):
                raise ProviderRuntimeError(
                    "Ollama stream token content is invalid"
                )
            if token:
                yield token

    async def list_available_models(self) -> list[str]:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self._host}/api/tags", timeout=5.0)
            if response.status_code != 200:
                raise ProviderRuntimeError(
                    f"Ollama model listing failed with HTTP {response.status_code}"
                )
            payload = response.json()
            models = payload.get("models", [])
            if not isinstance(models, list):
                raise ProviderRuntimeError(
                    "Ollama model listing payload is invalid: 'models' is not a list"
                )
            return [m.get("name", "") for m in models if isinstance(m, dict) and m.get("name")]
        except ProviderRuntimeError:
            raise
        except Exception as e:
            raise ProviderRuntimeError(
                f"Ollama model listing request failed: {e}"
            ) from e

    async def check_provider_health(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self._host}/api/tags", timeout=5.0)
            return response.status_code == 200
        except Exception:
            return False

    async def get_active_model_info(self) -> ActiveModelInfo:
        return ActiveModelInfo(
            provider="ollama",
            model=self._active_model,
            endpoint=self._host,
            healthy=await self.check_provider_health(),
        )

    async def switch_model(self, model: str) -> ActiveModelInfo:
        candidate = (model or "").strip()
        if not candidate:
            raise ValueError("Model name cannot be empty")

        models = await self.list_available_models()
        if models and candidate not in models:
            raise ProviderRuntimeError(
                f"Model '{candidate}' is not available in Ollama runtime"
            )

        self._active_model = candidate
        return await self.get_active_model_info()

    async def close(self) -> None:
        close_fn = getattr(self._client, "close", None)
        if callable(close_fn):
            try:
                result = close_fn()
                if hasattr(result, "__await__"):
                    await result
            except Exception:
                pass
