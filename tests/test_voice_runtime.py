import json
import unittest
from unittest.mock import MagicMock, patch

from runtime.voice import (
    VoiceMicrophoneError,
    VoiceModelNotAvailableError,
    VoiceRecognitionManager,
    VoiceSessionBusyError,
)


class _FakeStream:
    def __init__(self):
        self.read_calls = 0
        self.stopped = False
        self.closed = False

    def read(self, _size, exception_on_overflow=False):
        self.read_calls += 1
        if self.read_calls > 2:
            return b""
        return b"x" * 2000

    def stop_stream(self):
        self.stopped = True

    def close(self):
        self.closed = True


class _FakeAudio:
    def __init__(self, stream=None, raise_open: Exception | None = None):
        self.stream = stream or _FakeStream()
        self.raise_open = raise_open
        self.terminated = False

    def get_device_count(self):
        return 1

    def open(self, **_kwargs):
        if self.raise_open is not None:
            raise self.raise_open
        return self.stream

    def terminate(self):
        self.terminated = True


class _FakeRecognizer:
    def __init__(self, *_args, **_kwargs):
        self.frames = 0

    def AcceptWaveform(self, _data):
        self.frames += 1
        return True

    def FinalResult(self):
        return json.dumps({"text": "hello ark"})


class VoiceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.manager = VoiceRecognitionManager(
            model_en_dir="/tmp/missing-model-en",
            model_tr_dir="/tmp/missing-model-tr",
        )

    def test_model_missing_raises_clear_message(self):
        with self.assertRaises(VoiceModelNotAvailableError) as ctx:
            self.manager.recognize(session_id="s1", language="en", phrase_limit_sec=1)
        self.assertIn("Vosk model not found", str(ctx.exception))

    def test_stop_is_session_scoped(self):
        s1 = self.manager._get_or_create_session_state("session-1")  # noqa: SLF001
        s2 = self.manager._get_or_create_session_state("session-2")  # noqa: SLF001
        s1.active = True
        s2.active = False

        stopped = self.manager.stop("session-1")
        self.assertTrue(stopped)
        self.assertTrue(s1.stop_event.is_set())
        self.assertFalse(s2.stop_event.is_set())

    def test_duplicate_session_detected(self):
        state = self.manager._get_or_create_session_state("dup")  # noqa: SLF001
        state.active = True
        with self.assertRaises(VoiceSessionBusyError):
            self.manager.recognize(session_id="dup", language="en", phrase_limit_sec=1)

    def test_microphone_open_error_handled(self):
        with patch.object(self.manager, "_get_model", return_value=object()), patch(
            "runtime.voice.pyaudio.PyAudio",
            return_value=_FakeAudio(raise_open=RuntimeError("permission denied")),
        ), patch("runtime.voice.KaldiRecognizer", side_effect=AssertionError("recognizer should not be created")) as recognizer_ctor:
            with self.assertRaises(VoiceMicrophoneError) as ctx:
                self.manager.recognize(session_id="s1", language="tr", phrase_limit_sec=1)

        recognizer_ctor.assert_not_called()
        self.assertIn("permission", str(ctx.exception).lower())

    def test_recognizer_init_error_cleans_resources(self):
        fake_stream = _FakeStream()
        fake_audio = _FakeAudio(stream=fake_stream)

        with patch.object(self.manager, "_get_model", return_value=object()), patch(
            "runtime.voice.pyaudio.PyAudio", return_value=fake_audio
        ), patch("runtime.voice.KaldiRecognizer", side_effect=RuntimeError("bad model handle")):
            with self.assertRaisesRegex(Exception, "bad model handle"):
                self.manager.recognize(session_id="s1", language="en", phrase_limit_sec=1)

        self.assertTrue(fake_stream.stopped)
        self.assertTrue(fake_stream.closed)
        self.assertTrue(fake_audio.terminated)

    def test_recognition_lifecycle_cleanup(self):
        fake_stream = _FakeStream()
        fake_audio = _FakeAudio(stream=fake_stream)

        with patch.object(self.manager, "_get_model", return_value=object()), patch(
            "runtime.voice.pyaudio.PyAudio", return_value=fake_audio
        ), patch("runtime.voice.KaldiRecognizer", side_effect=_FakeRecognizer):
            text = self.manager.recognize(session_id="s1", language="en", phrase_limit_sec=1)

        self.assertEqual(text, "hello ark")
        self.assertTrue(fake_stream.stopped)
        self.assertTrue(fake_stream.closed)
        self.assertTrue(fake_audio.terminated)

        # A second call should work, confirming lock/session cleanup.
        with patch.object(self.manager, "_get_model", return_value=object()), patch(
            "runtime.voice.pyaudio.PyAudio", return_value=_FakeAudio()
        ), patch("runtime.voice.KaldiRecognizer", side_effect=_FakeRecognizer):
            text2 = self.manager.recognize(session_id="s1", language="en", phrase_limit_sec=1)
        self.assertEqual(text2, "hello ark")


if __name__ == "__main__":
    unittest.main()
