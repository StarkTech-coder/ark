Markdown
# 🛡️ ARK — Autonomous Reasoning & Knowledge System

**ARK** is an ultra-fast, local, offline-first personal AI ecosystem and workspace automation framework designed for macOS. Powered by a hybrid high-performance **Go backend** and an advanced **Python RAG/MCP control plane**, ARK serves as an autonomous assistant built around the **Stark HUD Protocol**.

ARK operates **strictly offline and private by default** without cloud dependencies or telemetry. When web search mode is explicitly enabled by the user, only anonymized search queries and requested URL contents are fetched—your local documents, private memory, and personal history **never leave the device**.

---

## 🏛️ System Architecture

ARK leverages a split-runtime architecture combining Go's low-level execution speed with Python's AI/RAG orchestration capabilities:

```text
                  +-----------------------------------+
                  |      Chainlit UI / Web Client     |
                  +-----------------+-----------------+
                                    |
                                    v
+-----------------------------------+-----------------------------------+
|                     Python Orchestrator Plane                         |
|                                                                       |
|  +--------------------+   +-------------------+   +----------------+  |
|  |  Vosk STT Engine   |   |   Ollama LLM Client |   | SQLite Memory  |  |
|  | (EN/TR Offline)    |   | (Dynamic Select)  |   | (Thread DB)    |  |
|  +--------------------+   +-------------------+   +----------------+  |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  |                   Model Context Protocol (MCP)                  |  |
|  |  +------------------+  +-------------------+  +---------------+ |  |
|  |  | FileSystem MCP   |  |   LanceDB MCP     |  |  Router MCP   | |  |
|  |  | (Multi-Format)   |  | (3-Tier VectorDB) |  | (Intent AI)   | |  |
|  |  +------------------+  +-------------------+  +---------------+ |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------+-----------------------------------+
                                    |
               CLI Bridge & Subprocess Invocation (ark_bin)
                                    |
                                    v
+-----------------------------------+-----------------------------------+
|                        Go High-Speed Engine                           |
|                                                                       |
|  +-------------------+    +--------------------+    +--------------+  |
|  |  CLI Router       |    | System Actions     |    | Fast Web     |  |
|  |  & Dispatcher     |--->| (AppleScript / UI) |--->| Scraper      |  |
|  +-------------------+    +--------------------+    +--------------+  |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  |                     Workspace Modes Engine                      |  |
|  |  +------------+  +---------------+  +------------+  +---------+ |  |
|  |  |  01 Work   |  |  02 Research  |  | 03 Social  |  | 04 HUD  | |  |
|  |  +------------+  +---------------+  +------------+  +---------+ |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------------------------------------------+
🧠 Deep-Dive: System Architecture & Subsystems
📚 LanceDB 3-Tier Knowledge Base Architecture
To avoid vector noise, cross-domain hallucination, and inefficient top-k searches, ARK isolates vector knowledge into three distinct physical tables within a single local .lancedb instance:
university_knowledge_base: Lecture notes, PDFs, textbooks, academic theories.
code_knowledge_base: Source code files (.go, .py, .md), technical repositories, framework SDKs.
relationship_knowledge_base: Personal notes, chat history transcripts, relationship memories.
Intent Routing: Before vector retrieval, Router MCP classifies user query intent using an LLM or keyword fallback. The router deterministically selects the exact target table (e.g., searching only relationship_knowledge_base for personal queries), avoiding cross-table noise and accelerating search speeds.
Fast-Skip Deduplication: Incoming files are checked against table source metadata (is_file_already_indexed). Existing files bypass redundant embedding pipelines and LLM vision ingestion instantly.
🔄 Memory Architecture vs. RAG Pipeline
ARK strictly separates Conversational State (Memory) from Document Context (RAG) to ensure latency optimization and zero token clutter:
Feature	Conversational Memory	Vector RAG
Primary Domain	Thread-isolated chat history & user facts	Multi-domain document & chat embeddings
Isolation Level	Thread-Isolated (thread_id)	Category-Isolated (3 Tables)
Storage Engine	Local SQLite (ark_memory.db)	Local LanceDB (.lancedb)
Retrieval Type	Sequential / Key-Value Lookup	Semantic Vector Search (O(1) ANN)
Lifecycle	Persistent & Sliding Window Context	Static / File-Ingested Knowledge Base
👁️ Local Vision Processing & Optimization
On-Demand OCR / Description: When an image (.jpg, .png) is placed into the documents/ directory, fs_mcp automatically dispatches it to a local Ollama Vision model (llava).
RAG Context Integration: Generated Turkish/English image captions are formatted as structured text blocks ([VISION ANALYSIS / CAPTION]) and automatically chunked and vectorized into LanceDB.
Lazy Loading & Memory Optimization: The vision model is invoked statelessly via Ollama API endpoints, releasing unified RAM back to Apple Silicon for LLM text inference once captioning completes.
⚙️ System Design Decisions (Trade-offs & Rationale)
Why Go + Python Hybrid?
Go: Selected for OS-level IPC, lightning-fast subprocess orchestration, instant AppleScript execution, and high-concurrency web scraping with minimal memory footprint.
Python: Selected for rich AI/ML ecosystem maturity (Ollama integration, PyArrow, LanceDB bindings, Vosk STT, Chainlit UI).
Why LanceDB?
Embedded, serverless, disk-persisted vector store utilizing Apache Arrow columnar format. Zero overhead, near-instant cold startup times, and optimal M-series Apple Silicon RAM usage.
Why SQLite for Memory?
ACID-compliant, lightweight, and zero-configuration storage perfect for thread-isolated conversation threads and key-value memory records.
Why Model Context Protocol (MCP) Pattern?
Decouples data ingestion (fs_mcp), vector persistence (lancedb_mcp), and classification logic (router_mcp). Enables clean, modular, and auditable tool execution boundaries.
Why Local-First & Private Architecture?
Complete privacy guarantees, zero API latency/rate limits, immunity to cloud service outages, and total data ownership on local storage.
✨ Key Features
🔒 Offline-First & Privacy Preserved: 100% local operation by default. When web search is explicitly toggled, only external query strings are fetched—your private databases and files are never transmitted online.
⚡ Hybrid High-Performance Core: Low-level OS window positioning, space switching, audio cues, and HTTP scraping handled by Go binaries; AI orchestration handled by Python.
📚 3-Tier LanceDB Vector RAG: Physical table separation avoiding vector noise across university, code, and relationship domains.
🤖 Model Context Protocol (MCP): Decoupled MCP servers for file system operations, vector insertion, and intent routing.
🎛️ Dynamic UI Model Hot-Swapping: Select and switch installed Ollama models on the fly via Chainlit UI settings.
🎙️ Speech-to-Text & Custom Voice Commands: Integrated offline Vosk speech recognition with audio feedback triggers.
🖥️ Automated Workspace Switching: Deterministic macOS Space switching controlling Spotify, Safari, Chrome, VS Code, Notes, and Terminal via AppleScript.
📁 Repository Structure
Plaintext
.
├── cmd/
│   └── ark/
│       └── main.go           # Go CLI Entry point & subcommand handler
├── internal/
│   ├── actions/              # Low-level macOS AppleScript & Audio control
│   ├── dispatcher/           # Command routing logic
│   ├── modes/                # Workspace automation presets (Work, Research, Social, HUD)
│   └── tools/                # Native Go utilities (Scraper, Pipeline, API)
├── mcp_servers/
│   ├── fs_mcp.py             # FileSystem MCP: Document scanning & Vision integration
│   ├── lancedb_mcp.py        # LanceDB MCP: Ingestion & chunking pipeline
│   └── router_mcp.py         # Router MCP: Dynamic intent & category classification
├── rag/
│   └── vector_store.py       # LanceDB vector database controller & embeddings engine
├── memory/
│   └── db.py                 # Thread-isolated SQLite chat history & persistent facts
├── assets/                   # Audio feedback WAV assets
├── documents/                # Multi-tier RAG ingestion directories
│   ├── code/
│   ├── relationship/
│   └── university/
├── chat_ui.py                # Chainlit UI controller & LLM streaming bridge
├── config.json               # Central system configuration & command mappings
└── go.mod                    # Go module dependencies
## 🛠️ Tech Stack & Dependencies

- Go backend automation (`ark_bin`)
- Python orchestration runtime
- Chainlit UI
- Ollama local inference runtime
- LanceDB vector storage
- SQLite persistent memory
- Vosk offline speech recognition

## 🚀 Quick Start (Local)

### 1) Prerequisites

- Go 1.22+
- Python 3.10+
- Ollama running locally

Pull required models:

```bash
ollama serve
# Keep your existing local Qwen3:8B Q4 model tag.
# Example tag (common):
ollama pull qwen3:8b
ollama pull bge-m3
```

Optional vision model:

```bash
ollama pull llava
```

### 2) Build Go binary

```bash
go build -o ark_bin main.go
```

### 3) Python setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4) Launch ARK backend/UI on localhost

```bash
chainlit run chat_ui.py --host 127.0.0.1 --port 8000 --headless
```

Open: `http://127.0.0.1:8000`

## 🖥️ Desktop-oriented launch workflow (macOS)

```bash
python -m desktop.main --port 8000
```

- Binds to localhost (`127.0.0.1`) only.
- Waits for backend readiness before opening UI.
- Falls back to local browser-based desktop flow.
- Cleans up backend process on launcher shutdown.

## 📦 Build macOS `.app` bundle

```bash
bash desktop/build_macos_app.sh
```

Output:

- `dist/ARKDesktop.app`

Signing/notarization is not included without Apple Developer credentials.

## 🎙️ Vosk voice setup

ARK voice remains local-only. Model directories are resolved in this order:

1. `ARK_VOSK_MODEL_DIR` and `ARK_VOSK_MODEL_TR_DIR`
2. Project folders: `model/` and `model_tr/`
3. App data folders under `~/Library/Application Support/ARK/`

If models are missing, voice endpoints return a setup error instead of crashing.

Microphone permission (macOS):

- Open **System Settings → Privacy & Security → Microphone**
- Allow access for the terminal or app process running ARK

## 🔒 Privacy and data locations

- Local-first by default.
- No cloud AI dependency for core assistant runtime.
- User data is stored outside the packaged app using platform-aware paths.
- Bundle must not include private SQLite/LanceDB/documents.

Detailed setup and troubleshooting: [docs/macos_desktop_setup.md](docs/macos_desktop_setup.md)
⌨️ Command Modes & Automations
Mode ID	Command Name	Description	Trigger Keywords
01	Work	Resets to Space 1, launches Spotify + Gmail, moves to Space 2 for Safari research, opens VS Code + Notes in Space 3.	work, coding, office
02	Research	Activates Safari and sets focus for web analysis.	research, browser, study
03	Social	Launches communication apps (WhatsApp, Instagram) with delay buffers.	social, chat, messages
04	HUD	Opens system resource monitoring (btop) in Terminal.	hud, monitor, stats
🚧 Current Limitations & Future Roadmap
ARK is under active development. Current roadmap milestones include:
[ ] RAG Retrieval Evaluation Pipeline: Integrate automated evaluation frameworks (Ragas/TruLens) for precision/recall benchmarking across vector stores.
[ ] Memory Consolidation Agent: Automated periodic background task to summarize old chat threads into long-term user facts in SQLite (user_memory).
[ ] MCP Error Recovery & Fallbacks: Self-healing retry mechanisms for file parsing errors or vector insertion failures.
[ ] Automated Integration Tests: Comprehensive E2E test suites for Go CLI subprocess bridges and Python API routes.
[ ] Vision Model Lifecycle Optimization: Dynamic unload signals to Ollama API to free VRAM/RAM immediately after processing image queues.
## 📜 License

This project is open-source under the MIT License. Designed and built with high standards of privacy and software engineering principles.