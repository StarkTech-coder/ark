# ARK macOS Desktop Setup (Apple Silicon)

## Supported environment

- macOS 13+ (Apple Silicon recommended)
- Python 3.10+
- Go 1.22+
- Ollama running locally

## What ARK currently does

ARK runs as a local-first assistant with:

- Chainlit chat UI
- Ollama chat model support (default: `qwen3:8b`)
- SQLite memory
- LanceDB RAG
- MCP permission management
- Local web research pipeline
- Local Vosk speech recognition endpoints

## Privacy and local-first behavior

- Core chat, memory, RAG, and voice processing run locally.
- The server launcher binds to `127.0.0.1` only.
- Desktop packaging must not include private local data (SQLite DB, LanceDB indexes, personal documents).
- Web research fetches only explicitly requested public pages.

## First-launch prerequisites

### 1) Ollama

Start Ollama locally:

```bash
ollama serve
```

Pull required models:

```bash
# Keep your existing local Qwen3:8B Q4 tag.
# Example tag (common):
ollama pull qwen3:8b
ollama pull bge-m3
```

Optional vision model:

```bash
ollama pull llava
```

### 2) Vosk models

ARK looks for models in this order:

1. `ARK_VOSK_MODEL_DIR` (English)
2. `ARK_VOSK_MODEL_TR_DIR` (Turkish)
3. Project paths: `model/`, `model_tr/`
4. App data paths: `~/Library/Application Support/ARK/model` and `~/Library/Application Support/ARK/model_tr`

If model folders are missing, voice endpoints return a clear setup error message.

### 3) Microphone permission

On macOS, allow microphone for the app/terminal process that runs ARK:

- System Settings → Privacy & Security → Microphone
- Enable access for your terminal or packaged ARK app.

## Development launch

From project root:

```bash
source venv/bin/activate
chainlit run chat_ui.py --host 127.0.0.1 --port 8000 --headless
```

Then open:

- http://127.0.0.1:8000

## Desktop-oriented launcher (local browser fallback)

Use the desktop launcher entry:

```bash
source venv/bin/activate
python -m desktop.main --port 8000
```

Behavior:

- Starts Chainlit backend on localhost only.
- Detects backend readiness before opening UI.
- Auto-selects a nearby port if the preferred one is busy.
- Opens local browser as desktop fallback.
- Stops backend process on launcher shutdown.

## Build a macOS `.app` bundle

Build script:

```bash
source venv/bin/activate
bash desktop/build_macos_app.sh
```

Expected output:

- `dist/ARKDesktop.app`

Notes:

- Current build is local/development signing state only.
- Not signed/not notarized unless Apple credentials are provided externally.

## Packaging scope and exclusions

Bundle includes runtime code and UI assets needed to start ARK.

Bundle excludes user/private data:

- SQLite DB files
- LanceDB indexes
- `documents/` personal content
- local Ollama model blobs

## Data storage locations

Runtime paths are platform-aware. On macOS default location is:

- `~/Library/Application Support/ARK/`

Typical files:

- `ark_memory.db` (SQLite)
- `lancedb/` (vector store when no legacy project `.lancedb` exists)
- `logs/ark.log`

## Troubleshooting

### Ollama unavailable

- Symptom: chat generation fails or warning appears at launcher startup.
- Fix: run `ollama serve` and verify `http://127.0.0.1:11434/api/tags`.

### Port conflict

- Symptom: preferred port already in use.
- Fix: launcher auto-selects a nearby free port, or pass `--port <free_port>`.

### Voice model missing

- Symptom: `/ark/listen/stt` returns `model_missing`.
- Fix: install Vosk model folders and/or set `ARK_VOSK_MODEL_DIR`, `ARK_VOSK_MODEL_TR_DIR`.

### Microphone access denied

- Symptom: `microphone_unavailable` response.
- Fix: grant microphone permission and retry.

### Backend does not open UI

- Symptom: readiness timeout.
- Fix: inspect stderr/log output and run manually with `chainlit run chat_ui.py --host 127.0.0.1 --port 8000 --headless`.
