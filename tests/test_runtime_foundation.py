import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from llm import config as llm_config
from runtime import config as runtime_config
from runtime import paths as runtime_paths
from runtime.lifecycle import initialize_runtime, shutdown_runtime


class RuntimeFoundationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_cross_platform_path_resolution_with_env_overrides(self):
        data_dir = Path(self.tmp.name) / "data"
        config_dir = Path(self.tmp.name) / "config"
        cache_dir = Path(self.tmp.name) / "cache"
        db_file = data_dir / "custom_memory.db"
        ldb_dir = data_dir / "custom_lancedb"
        model_en_dir = data_dir / "custom_model_en"
        model_tr_dir = data_dir / "custom_model_tr"
        cfg_file = config_dir / "custom_config.json"

        config_dir.mkdir(parents=True, exist_ok=True)
        cfg_file.write_text("{}", encoding="utf-8")

        with patch.dict(
            os.environ,
            {
                "ARK_APP_DATA_DIR": str(data_dir),
                "ARK_APP_CONFIG_DIR": str(config_dir),
                "ARK_APP_CACHE_DIR": str(cache_dir),
                "ARK_MEMORY_DB_PATH": str(db_file),
                "ARK_LANCEDB_PATH": str(ldb_dir),
                "ARK_VOSK_MODEL_DIR": str(model_en_dir),
                "ARK_VOSK_MODEL_TR_DIR": str(model_tr_dir),
                "ARK_CONFIG_PATH": str(cfg_file),
            },
            clear=False,
        ):
            runtime_paths._cached_paths = None
            paths = runtime_paths.get_runtime_paths()
            self.assertEqual(paths.sqlite_path, db_file)
            self.assertEqual(paths.lancedb_path, ldb_dir)
            self.assertEqual(paths.model_dir, model_en_dir)
            self.assertEqual(paths.model_tr_dir, model_tr_dir)
            self.assertEqual(paths.config_path, cfg_file)
            runtime_paths.ensure_runtime_dirs(paths)
            self.assertTrue(paths.logs_dir.exists())

    def test_existing_legacy_paths_remain_accessible(self):
        # These paths should remain the defaults when present in the project root.
        runtime_paths._cached_paths = None
        root = runtime_paths.get_project_root()
        self.assertEqual(runtime_paths.resolve_sqlite_path(), root / "ark_memory.db")
        self.assertEqual(runtime_paths.resolve_lancedb_path(), root / ".lancedb")

    def test_runtime_config_loading_and_env_log_override(self):
        cfg_file = Path(self.tmp.name) / "config.json"
        cfg_file.write_text('{"runtime": {"log_level": "INFO"}}', encoding="utf-8")

        with patch.dict(os.environ, {"ARK_CONFIG_PATH": str(cfg_file), "ARK_LOG_LEVEL": "DEBUG"}, clear=False):
            runtime_config._cached_config = None
            cfg = runtime_config.load_runtime_config(force_reload=True)
            self.assertEqual(cfg.log_level, "DEBUG")

    async def test_initialize_runtime_handles_optional_service_failure(self):
        fake_provider = type("Provider", (), {})()
        fake_provider.check_provider_health = AsyncMock(side_effect=RuntimeError("down"))
        fake_provider.close = AsyncMock(return_value=None)

        status = await initialize_runtime(chat_provider=fake_provider)
        self.assertTrue(status.sqlite_ready)
        self.assertIs(status.ollama_ready, False)

        await shutdown_runtime(chat_provider=fake_provider)

    def test_llm_provider_config_compatibility(self):
        cfg_file = Path(self.tmp.name) / "cfg.json"
        cfg_file.write_text(
            '{"ai": {"provider": "ollama", "active_model": "qwen3:8b", "ollama_host": "http://127.0.0.1:11434"}}',
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ARK_CONFIG_PATH": str(cfg_file)}, clear=False):
            runtime_config._cached_config = None
            self.assertEqual(llm_config.get_provider_name(), "ollama")
            self.assertEqual(llm_config.get_active_chat_model(), "qwen3:8b")
            self.assertEqual(llm_config.get_ollama_host(), "http://127.0.0.1:11434")


if __name__ == "__main__":
    unittest.main()
