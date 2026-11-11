import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from llm.providers.ollama_provider import OllamaProvider, ProviderRuntimeError


class OllamaProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.provider = OllamaProvider(
            host="http://127.0.0.1:11434",
            default_model="qwen3:8b",
        )

    async def test_generate_response_prompt_mode(self):
        self.provider._client.generate = AsyncMock(
            return_value={"response": "hello world"}
        )
        result = await self.provider.generate_response(
            model="qwen3:8b",
            prompt="hello",
        )
        self.assertEqual(result, "hello world")

    async def test_generate_response_messages_mode(self):
        self.provider._client.chat = AsyncMock(
            return_value={"message": {"content": "from chat"}}
        )
        result = await self.provider.generate_response(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "ping"}],
        )
        self.assertEqual(result, "from chat")

    async def test_stream_response(self):
        async def fake_stream():
            yield {"message": {"content": "a"}}
            yield {"message": {"content": "b"}}

        self.provider._client.chat = AsyncMock(return_value=fake_stream())

        tokens = []
        async for token in self.provider.stream_response(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "stream"}],
        ):
            tokens.append(token)

        self.assertEqual(tokens, ["a", "b"])

    async def test_stream_response_invalid_chunk_raises(self):
        async def fake_stream():
            yield "not-a-dict"

        self.provider._client.chat = AsyncMock(return_value=fake_stream())

        with self.assertRaises(ProviderRuntimeError):
            async for _ in self.provider.stream_response(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "stream"}],
            ):
                pass

    async def test_list_available_models(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "qwen3:8b"}, {"name": "llava"}]
        }

        mock_httpx_client = MagicMock()
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("llm.providers.ollama_provider.httpx.AsyncClient", return_value=mock_cm):
            models = await self.provider.list_available_models()

        self.assertEqual(models, ["qwen3:8b", "llava"])

    async def test_list_available_models_connection_failure_raises(self):
        mock_httpx_client = MagicMock()
        mock_httpx_client.get = AsyncMock(side_effect=RuntimeError("connect error"))

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "llm.providers.ollama_provider.httpx.AsyncClient",
            return_value=mock_cm,
        ):
            with self.assertRaises(ProviderRuntimeError):
                await self.provider.list_available_models()

    async def test_check_provider_health(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_httpx_client = MagicMock()
        mock_httpx_client.get = AsyncMock(return_value=mock_response)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("llm.providers.ollama_provider.httpx.AsyncClient", return_value=mock_cm):
            healthy = await self.provider.check_provider_health()

        self.assertTrue(healthy)

    async def test_check_provider_health_failure_returns_false(self):
        mock_httpx_client = MagicMock()
        mock_httpx_client.get = AsyncMock(side_effect=RuntimeError("unreachable"))

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_httpx_client)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "llm.providers.ollama_provider.httpx.AsyncClient",
            return_value=mock_cm,
        ):
            healthy = await self.provider.check_provider_health()

        self.assertFalse(healthy)

    async def test_switch_model_success(self):
        self.provider.list_available_models = AsyncMock(
            return_value=["qwen3:8b", "qwen2.5-coder"]
        )
        self.provider.check_provider_health = AsyncMock(return_value=True)

        info = await self.provider.switch_model("qwen2.5-coder")
        self.assertEqual(info.model, "qwen2.5-coder")
        active = await self.provider.get_active_model_info()
        self.assertEqual(active.model, "qwen2.5-coder")

    async def test_switch_model_unavailable_raises(self):
        self.provider.list_available_models = AsyncMock(return_value=["qwen3:8b"])
        with self.assertRaises(ProviderRuntimeError):
            await self.provider.switch_model("unknown-model")


if __name__ == "__main__":
    unittest.main()
