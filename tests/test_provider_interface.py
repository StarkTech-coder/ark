import unittest
from unittest.mock import patch
from typing import Any, AsyncIterator

from llm import config as llm_config
from llm.providers.base import ActiveModelInfo, LLMProvider


class IncompleteProvider(LLMProvider):
    pass


class DummyProvider(LLMProvider):
    def __init__(self):
        self._active_model = "qwen3:8b"

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
        target_model = model or self._active_model
        if messages:
            return f"{target_model}:{messages[-1].get('content', '')}"
        return f"{target_model}:{prompt or ''}"

    async def stream_response(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        options: dict[str, Any] | None = None,
        request_kwargs: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        for msg in messages:
            content = msg.get("content", "")
            if content:
                yield content

    async def list_available_models(self) -> list[str]:
        return ["qwen3:8b"]

    async def check_provider_health(self) -> bool:
        return True

    async def get_active_model_info(self) -> ActiveModelInfo:
        return ActiveModelInfo(
            provider="dummy",
            model=self._active_model,
            endpoint="http://127.0.0.1",
            healthy=True,
        )

    async def switch_model(self, model: str) -> ActiveModelInfo:
        if not model.strip():
            raise ValueError("empty")
        self._active_model = model
        return await self.get_active_model_info()

    async def close(self) -> None:
        return None


class ProviderInterfaceTests(unittest.IsolatedAsyncioTestCase):
    def test_incomplete_provider_is_abstract(self):
        with self.assertRaises(TypeError):
            IncompleteProvider()

    async def test_dummy_provider_implements_contract(self):
        provider = DummyProvider()
        self.assertEqual(
            await provider.generate_response(model="qwen3:8b", prompt="hello"),
            "qwen3:8b:hello",
        )
        self.assertEqual(await provider.list_available_models(), ["qwen3:8b"])
        self.assertTrue(await provider.check_provider_health())

        info = await provider.get_active_model_info()
        self.assertEqual(info.provider, "dummy")
        self.assertEqual(info.model, "qwen3:8b")

        switched = await provider.switch_model("qwen2.5-coder")
        self.assertEqual(switched.model, "qwen2.5-coder")

    def test_hardware_profile_override_and_selection(self):
        with patch.dict(
            "os.environ",
            {"ARK_HARDWARE_PROFILE": "high_memory"},
            clear=False,
        ):
            self.assertEqual(llm_config.get_hardware_profile_name(total_ram_gb=16), "high_memory")

        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(llm_config.get_hardware_profile_name(total_ram_gb=16), "m2_16gb")
            self.assertEqual(
                llm_config.get_hardware_profile_name(total_ram_gb=516),
                "high_memory",
            )

    def test_embedding_and_chat_configuration_separation(self):
        fake_cfg = {
            "ai": {
                "active_model": "qwen3:8b",
                "embedding_model": "bge-m3",
                "embedding_dimensions": {"bge-m3": 1024},
            }
        }
        with patch("llm.config.load_config", return_value=fake_cfg):
            self.assertEqual(llm_config.get_active_chat_model(), "qwen3:8b")
            self.assertEqual(llm_config.get_embedding_model(), "bge-m3")
            self.assertEqual(llm_config.get_embedding_dimension("bge-m3"), 1024)


if __name__ == "__main__":
    unittest.main()
