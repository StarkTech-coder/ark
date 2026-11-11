"""Session-safe local voice recognition runtime for ARK."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pyaudio
from vosk import KaldiRecognizer, Model


class VoiceRuntimeError(RuntimeError):
    """Base voice runtime exception."""


class VoiceModelNotAvailableError(VoiceRuntimeError):
    """Raised when a requested local Vosk model is unavailable."""


class VoiceMicrophoneError(VoiceRuntimeError):
    """Raised when microphone access or audio stream setup fails."""


class VoiceSessionBusyError(VoiceRuntimeError):
    """Raised when a session tries to start a duplicate voice stream."""


@dataclass
class _VoiceSessionState:
    active: bool
    stop_event: threading.Event


class VoiceRecognitionManager:
    """Coordinates per-session Vosk recognition with safe stream lifecycle."""

    def __init__(
        self,
        *,
        model_en_dir: str | Path,
        model_tr_dir: str | Path,
    ):
        self._model_paths = {
            "en": Path(model_en_dir).expanduser().resolve(),
            "tr": Path(model_tr_dir).expanduser().resolve(),
        }
        self._models: dict[str, Model] = {}
        self._models_lock = threading.Lock()

        self._sessions: dict[str, _VoiceSessionState] = {}
        self._sessions_lock = threading.Lock()

        # Physical microphone is exclusive on many machines.
        self._microphone_lock = threading.Lock()

    def describe_model_setup(self, language: str) -> str:
        lang = self._normalize_language(language)
        target = self._model_paths[lang]
        env_name = "ARK_VOSK_MODEL_DIR" if lang == "en" else "ARK_VOSK_MODEL_TR_DIR"
        return (
            f"Vosk model not found for language='{lang}'. "
            f"Expected directory: {target}. "
            f"Set {env_name} or install model files at this location."
        )

    def model_available(self, language: str) -> bool:
        lang = self._normalize_language(language)
        return self._model_paths[lang].exists()

    def stop(self, session_id: str) -> bool:
        state = self._get_or_create_session_state(session_id)
        if state.active:
            state.stop_event.set()
            return True
        return False

    def cleanup_session(self, session_id: str) -> None:
        with self._sessions_lock:
            state = self._sessions.get(session_id)
            if state and not state.active:
                self._sessions.pop(session_id, None)

    def recognize(
        self,
        *,
        session_id: str,
        phrase_limit_sec: int = 15,
        language: str = "en",
    ) -> str:
        state = self._get_or_create_session_state(session_id)
        if state.active:
            raise VoiceSessionBusyError("voice_session_already_active")

        lock_acquired = self._microphone_lock.acquire(blocking=False)
        if not lock_acquired:
            raise VoiceSessionBusyError("microphone_in_use")

        state.active = True
        state.stop_event.clear()

        stream = None
        audio = None
        try:
            model = self._get_model(language)
            recognizer = None

            audio = pyaudio.PyAudio()
            try:
                if audio.get_device_count() <= 0:
                    raise VoiceMicrophoneError("No microphone device is available")
            except Exception:
                # Some backends may not support device count reliably; proceed to open.
                pass

            try:
                stream = audio.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=16000,
                    input=True,
                    frames_per_buffer=2000,
                )
            except Exception as exc:
                raise VoiceMicrophoneError(
                    f"Microphone access unavailable. Check macOS microphone permission. Details: {exc}"
                ) from exc

            try:
                recognizer = KaldiRecognizer(model, 16000)
            except Exception as exc:
                raise VoiceRuntimeError(
                    f"Failed to initialize local Vosk recognizer: {exc}"
                ) from exc

            start = time.time()
            while True:
                if state.stop_event.is_set():
                    break
                if time.time() - start > max(1, phrase_limit_sec):
                    break

                try:
                    data = stream.read(2000, exception_on_overflow=False)
                except Exception as exc:
                    raise VoiceMicrophoneError(f"Audio stream read failed: {exc}") from exc

                if not data:
                    break
                recognizer.AcceptWaveform(data)

            final_result = json.loads(recognizer.FinalResult())
            text = str(final_result.get("text", "")).strip()
            return text
        finally:
            try:
                if stream is not None:
                    stream.stop_stream()
                    stream.close()
            finally:
                if audio is not None:
                    audio.terminate()

            state.active = False
            state.stop_event.clear()
            if lock_acquired and self._microphone_lock.locked():
                self._microphone_lock.release()

    def _normalize_language(self, language: str) -> str:
        lang = (language or "en").strip().lower()
        return "tr" if lang.startswith("tr") else "en"

    def _get_model(self, language: str) -> Model:
        lang = self._normalize_language(language)
        with self._models_lock:
            cached = self._models.get(lang)
            if cached is not None:
                return cached

            path = self._model_paths[lang]
            if not path.exists():
                raise VoiceModelNotAvailableError(self.describe_model_setup(lang))

            model = Model(str(path))
            self._models[lang] = model
            return model

    def _get_or_create_session_state(self, session_id: str) -> _VoiceSessionState:
        safe_session = (session_id or "api-session").strip() or "api-session"
        with self._sessions_lock:
            existing = self._sessions.get(safe_session)
            if existing is not None:
                return existing
            state = _VoiceSessionState(active=False, stop_event=threading.Event())
            self._sessions[safe_session] = state
            return state
