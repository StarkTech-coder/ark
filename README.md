# ARK — Autonomous Reasoning & Knowledge System

ARK is a local-first AI assistant and desktop automation system. It combines a Python application layer for conversation, model orchestration, memory, retrieval and tool management with a Go execution layer for fast command routing, system automation and utility operations.

The architecture is modular: the user interface, runtime lifecycle, LLM provider, persistent memory, document retrieval, local tools and native system actions are separated into focused packages. Ollama is the current LLM runtime implementation; network-backed research and GitHub features are optional integrations rather than requirements for the local chat and knowledge workflows.

## Architecture at a glance

```text
                         USER
                          |
             +------------+-------------+
             |                          |
       Chainlit / FastAPI          Desktop launcher
         chat_ui.py                desktop/main.py
             |                          |
             +------------+-------------+
                          |
                PYTHON APPLICATION LAYER
                          |
       +------------------+-----------------------+
       |                  |                       |
  Request workflow    LLM provider           Runtime services
  classification      interface               config / paths /
  and orchestration   Ollama adapter           lifecycle / logging
       |                  |                       |
       +------------------+-----------------------+
                          |
       +------------------+-----------------------+
       |                  |                       |
  Persistent memory   Knowledge retrieval     Local tool registry
  SQLite              LanceDB + embeddings    MCP-style management
  conversations       domain routing          permissions / consent
       |                  |                       |
       +------------------+-----------------------+
                          |
                 TOOL / EXECUTION BRIDGE
                          |
                 Go CLI binary (ark_bin)
                          |
       +------------------+-----------------------+
       |                  |                       |
  Command dispatcher  Native system actions   Utility services
  workspace modes     AppleScript / macOS      web / APIs /
                      Spaces / audio           parallel pipeline
```

## Main subsystems

### 1. Python orchestration and user interface

- `chat_ui.py` is the main Chainlit interface and application orchestration entry point.
- The request workflow classifies incoming prompts into general chat, project/RAG, memory, web research, GitHub and tool-oriented paths.
- The UI connects conversation history, source attribution, model streaming, retrieval and tool execution.
- FastAPI routes are used alongside the Chainlit application for application endpoints.
- `desktop/` provides a local desktop launcher. It checks backend readiness, selects an available port when needed, opens the local interface and shuts down the child process cleanly.

### 2. LLM provider layer

- `llm/providers/base.py` defines the provider contract.
- `llm/providers/ollama_provider.py` implements chat generation, streaming, model discovery, health checks and model switching through Ollama.
- `llm/factory.py` constructs the configured provider. Ollama is the currently implemented provider and the fallback.
- `llm/config.py` resolves the active chat, embedding and vision models, Ollama endpoint and hardware profiles from configuration and environment variables.

Default model settings in the repository configuration include `qwen3:8b` for chat, `bge-m3` for embeddings and `llava` for image description. Actual runtime settings can be overridden.

### 3. Persistent memory — SQLite

The memory subsystem is separate from document RAG. It stores structured long-term memory records and conversation messages.

- `memory/connection.py`: SQLite connection and transaction management, including WAL mode.
- `memory/migrations.py`: versioned schema migrations.
- `memory/repository.py`: persistence and query operations.
- `memory/service.py`: application-level memory operations, validation, domain checks and import/export.
- `memory/api.py`: management facade for integrations.

Memory records support domains, types, tags, metadata, importance scores, expiration, active/deleted state and soft deletion. The service also supports filtered listing, search, statistics, JSON/CSV export and JSON import. Cross-domain searches require explicit authorization.

### 4. Document knowledge and RAG — LanceDB

The RAG subsystem indexes document chunks and retrieves relevant context independently of conversational memory.

- `rag/vector_store.py` manages the embedded LanceDB store, embeddings, table selection, insertion and retrieval.
- `mcp_servers/fs_mcp.py` discovers and extracts supported local documents.
- `mcp_servers/router_mcp.py` classifies documents and routes queries to the appropriate knowledge domain.
- `mcp_servers/lancedb_mcp.py` chunks extracted content and sends it to the vector store.

The knowledge store separates content into domain-specific tables, including university, code and relationship knowledge bases. A WhatsApp-specific table is also recognized for compatibility with message data. Retrieval combines vector similarity with keyword scoring and supports source-aware results.

Supported ingestion paths include PDF, text, Python, Go, Markdown, JSON, CSV, DOCX and common image formats. Image files can be described using the configured local Ollama vision model before being indexed as text.

### 5. Local tool registry and permissions

`mcp_servers/management.py` provides a registry and authorization layer for ARK's local tools. In the current implementation, the default tools are registered as local tools; they are not separate remote MCP protocol processes.

The default registry covers:

- Local filesystem discovery and document reading
- Document/query classification and routing
- LanceDB document ingestion
- Local system actions
- Web research
- Read-only GitHub repository inspection

Tool permissions are represented by `disabled`, `read`, `write` and `admin`. Sensitive actions can require explicit confirmation. Permission state is scoped to a user/session and persisted through the SQLite database layer.

### 6. Optional web and GitHub integrations

- `mcp_servers/web_research_mcp.py` performs web research, extracts source content and formats source-aware research results. It validates remote URLs and blocks localhost, private, loopback and other non-public network targets to reduce SSRF risk.
- `mcp_servers/github_mcp.py` provides read-only GitHub operations such as repository listing, commits, issues, pull requests, diffs and file reads. Configure `ARK_GITHUB_TOKEN` or `GITHUB_TOKEN` to enable authenticated access.
- The Go utility layer also contains web fetching and external API helpers.

These features require network access when invoked. ARK's local chat, SQLite memory and local LanceDB workflows are designed to run against local services; the project should therefore be described as **local-first**, not as unconditionally offline.

### 7. Go execution and macOS automation layer

The Go module is a separate execution layer, built as the `ark_bin` binary from the repository root.

- `main.go`: command-line entry point. Routes web fetching, parallel intent pipelines, direct API requests and standard workspace mode IDs.
- `internal/dispatcher/router.go`: maps mode IDs to their handlers.
- `internal/modes/`: Work, Research, Social and HUD workspace routines.
- `internal/actions/system.go`: AppleScript execution, macOS Space navigation, application activation and audio playback.
- `internal/tools/`: web fetching, parallel intent execution and utility/API integrations.

The native automation routines use macOS facilities such as `osascript` and `afplay`. Those actions are macOS-specific; the Go packages guard or report unsupported platform operations where applicable.

## Data and runtime boundaries

ARK separates source code from runtime data. Runtime paths are resolved centrally in `runtime/paths.py`, with platform-aware defaults and environment overrides.

Important environment overrides include:

| Variable | Purpose |
|---|---|
| `ARK_PROJECT_ROOT` | Project/resource root |
| `ARK_APP_DATA_DIR` | Application data directory |
| `ARK_APP_CONFIG_DIR` | Application configuration directory |
| `ARK_APP_CACHE_DIR` | Cache directory |
| `ARK_CONFIG_PATH` | Explicit configuration file |
| `ARK_MEMORY_DB_PATH` | SQLite memory database path |
| `ARK_LANCEDB_PATH` | LanceDB storage path |
| `ARK_VOSK_MODEL_DIR` | English Vosk model directory |
| `ARK_VOSK_MODEL_TR_DIR` | Turkish Vosk model directory |
| `ARK_BIN_PATH` | Go executable path |
| `ARK_PROVIDER` | LLM provider selection |
| `ARK_ACTIVE_MODEL` | Active chat model |
| `ARK_EMBEDDING_MODEL` | Embedding model |
| `OLLAMA_HOST` | Ollama endpoint |
| `ARK_GITHUB_TOKEN` / `GITHUB_TOKEN` | GitHub API authentication |

On macOS, application data defaults to `~/Library/Application Support/ARK`. SQLite, LanceDB, Vosk models, documents and credentials are runtime assets and should not be committed to the source repository. The local database directory is intentionally excluded from Git.

## Repository layout

```text
.
├── chat_ui.py                  # Chainlit UI and Python orchestration
├── listen.py                   # Offline voice command entry point
├── main.go                     # Go CLI entry point
├── go.mod                      # Go module definition
├── config.json                 # Default application/model/command settings
├── desktop/
│   ├── main.py                 # Desktop launcher entry point
│   ├── launcher.py             # Backend process and readiness management
│   └── backend_main.py         # Bundled Chainlit backend entry point
├── llm/
│   ├── config.py               # Model/provider configuration
│   ├── factory.py              # Provider construction
│   └── providers/              # Provider interface and implementations
├── memory/
│   ├── api.py                  # Memory management facade
│   ├── connection.py           # SQLite connection/transactions
│   ├── migrations.py           # Database schema migrations
│   ├── repository.py           # Persistence/query layer
│   └── service.py              # Memory business logic
├── rag/
│   └── vector_store.py         # LanceDB, embeddings and retrieval
├── mcp_servers/
│   ├── management.py           # Local tool registry and authorization
│   ├── fs_mcp.py               # Document discovery and extraction
│   ├── router_mcp.py           # Intent/document routing
│   ├── lancedb_mcp.py          # Chunking and vector ingestion
│   ├── web_research_mcp.py     # Secure web research helpers
│   └── github_mcp.py           # Read-only GitHub integration
├── runtime/
│   ├── config.py               # Runtime configuration
│   ├── lifecycle.py            # Startup/readiness/shutdown
│   ├── logging_config.py       # Logging setup
│   ├── paths.py                # Cross-platform path resolution
│   ├── platform_ops.py         # Platform-specific operations
│   └── voice.py                # Session-safe Vosk recognition
├── internal/
│   ├── actions/                # Native OS actions
│   ├── dispatcher/             # Go command routing
│   ├── modes/                  # Workspace automation modes
│   └── tools/                  # Go utility services
├── documents/                  # Local document ingestion folders
├── assets/                     # Local audio/UI assets
└── tests/                      # Python tests
```

## Runtime lifecycle

At startup, `runtime/lifecycle.py` configures logging, loads runtime configuration, creates required runtime directories and initializes SQLite. It also probes LanceDB and optionally checks the configured LLM provider. SQLite is treated as the critical service; LanceDB and the model provider are reported as optional readiness states.

The desktop launcher starts the Chainlit backend on loopback (`127.0.0.1`), waits for readiness and owns the backend process lifecycle. The application can also be started directly through Chainlit for development.

## Getting started

### Requirements

- Python environment compatible with the installed dependencies
- Go version declared in `go.mod`
- Ollama for local chat and embedding inference
- macOS for the native workspace automation actions
- Optional: Vosk English/Turkish model directories for voice recognition
- Optional: `llava` or another configured Ollama vision model for image descriptions
- Optional: GitHub token for repository integration

### Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Prepare local models

Start Ollama and pull the models configured for the installation. The repository defaults are:

```bash
ollama serve
ollama pull qwen3:8b
ollama pull bge-m3
ollama pull llava
```

The vision model is only needed for image captioning. Model names can be changed in `config.json` or through supported environment settings.

### Build the Go executable

From the repository root:

```bash
go build -o ark_bin .
```

### Start ARK

Desktop launcher:

```bash
python -m desktop.main --port 8000
```

Direct Chainlit development mode:

```bash
chainlit run chat_ui.py --host 127.0.0.1 --port 8000 --headless
```

Then open `http://127.0.0.1:8000`.

### Voice setup

Set up the English and/or Turkish Vosk model directories using `ARK_VOSK_MODEL_DIR` and `ARK_VOSK_MODEL_TR_DIR`, or place the model files in the resolved runtime model directories. On macOS, grant microphone permission to the terminal or desktop application.

## Testing

The repository contains Python `unittest` coverage for runtime initialization, memory persistence and domain isolation, MCP tool permissions, RAG behavior, web research security and integrated workflows.

Run the test suite from the repository root:

```bash
python -m unittest discover -s tests -v
```

## Security model and limitations

- Local-first operation: local model inference, SQLite memory and LanceDB storage are available without a hosted AI service.
- Network access is used only by features that explicitly need it, such as web research, remote page fetching and GitHub API integration.
- GitHub integration is read-only in the current implementation.
- Local tool permissions distinguish read, write and admin access; sensitive operations may require confirmation.
- Web research validates destinations and blocks private/local network targets.
- The desktop launcher binds to loopback by default. Do not expose the local UI to an untrusted network without adding authentication and deployment hardening.
- macOS workspace automation requires user-granted system permissions and is not portable to other operating systems.

## Development status

ARK is an actively developed system. The architecture described here reflects the current repository implementation: Python-based application orchestration, provider abstraction with Ollama implementation, separate SQLite memory and LanceDB RAG layers, managed local tools, optional web/GitHub integrations, and a Go-based execution/automation layer.

## License

See [LICENSE](LICENSE) for license terms.
