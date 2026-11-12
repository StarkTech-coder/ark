# ARK Complete Read-Only Audit Report

Date: 2026-11-11  
Audited workspace: /Users/tony/Desktop/ark  
Requested additional local path: /Users/tony/ark (not present)  
GitHub repository: StarkTech-coder/ark

---

## 1) Audit Scope, Constraints, and Method

This audit was executed as read-only.

- No application source files were modified.
- No config, database, vector store, or user data was modified.
- No dependency install/upgrade was performed.
- No git commit/push/reset/clean/history rewrite was performed.

Validation and inspection methods:

- Full code/config review for Python, Go, Chainlit, MCP modules, RAG, memory, web tools, voice, and UI.
- Local-vs-GitHub comparison through git remote state and commit parity.
- Basic Go build health via `go test ./...` (no test files; compile/package checks only).
- Workspace diagnostics scan (no editor errors surfaced).

---

## 2) Local vs GitHub Repository Comparison

## Result

- Local tracked `main` and `origin/main` are identical at commit `06813f865cd7021971d025003aa7bb6f840ce6e0`.
- No tracked file diff between local and GitHub main (`git diff origin/main...HEAD` was empty).
- Local has untracked instruction files only:
  - .github/
  - AGENTS.md

## Important scope note

- The requested second local path `/Users/tony/ark` does not exist on this machine in this session.
- Effective local code audit target was `/Users/tony/Desktop/ark`.

---

## 3) Architecture Audit (UI, orchestration, providers, memory, RAG, DB, MCP, web, voice, desktop)

## Observed architecture

- UI + orchestration centered in [chat_ui.py](chat_ui.py).
- Go automation/backend entry at [main.go](main.go), dispatching into [internal/dispatcher/router.go](internal/dispatcher/router.go).
- Local memory in SQLite via [memory/db.py](memory/db.py).
- Vector RAG in LanceDB via [rag/vector_store.py](rag/vector_store.py).
- “MCP” modules implemented as local Python modules:
  - [mcp_servers/fs_mcp.py](mcp_servers/fs_mcp.py)
  - [mcp_servers/lancedb_mcp.py](mcp_servers/lancedb_mcp.py)
  - [mcp_servers/router_mcp.py](mcp_servers/router_mcp.py)

## Assessment

- Modular separation exists at file/module level.
- However, cross-platform abstraction is weak: many components are directly coupled to macOS and a fixed local path.
- Provider abstraction is partial (dynamic model name selection exists), but Ollama transport is hardcoded in many places.

Evidence:

- Hardcoded local path in multiple modules: [chat_ui.py](chat_ui.py#L43), [listen.py](listen.py#L20), [mcp_servers/fs_mcp.py](mcp_servers/fs_mcp.py#L17), [mcp_servers/router_mcp.py](mcp_servers/router_mcp.py#L15), [config.json](config.json#L12), [internal/modes/work.go](internal/modes/work.go#L51).
- macOS-only automation and AppleScript: [internal/actions/system.go](internal/actions/system.go#L30), [internal/actions/system.go](internal/actions/system.go#L47), [internal/actions/system.go](internal/actions/system.go#L60).

---

## 4) Python Code Audit

## Strengths

- Type hints are present in key signatures.
- Error handling exists in I/O and network-heavy paths.
- Clear decomposition across chat, RAG, memory, and helper modules.

## Issues

1. **High-risk router bug (P0): malformed Ollama host URL in query intent routing**  
   - [mcp_servers/router_mcp.py](mcp_servers/router_mcp.py#L96) uses markdown-formatted URL text instead of a raw host URL.  
   - This likely forces fallback routing behavior and degrades RAG precision.

2. **Unused import / dead coupling**  
   - `classify_document` imported in [chat_ui.py](chat_ui.py#L37) but never used (defined in [mcp_servers/router_mcp.py](mcp_servers/router_mcp.py#L31)).

3. **Global mutable state without session isolation for toggles**  
   - Shared flags in [chat_ui.py](chat_ui.py#L88), toggled via [chat_ui.py](chat_ui.py#L472) and [chat_ui.py](chat_ui.py#L482).  
   - In multi-user/process scenarios this can leak behavior across sessions.

4. **Threading/async bridge complexity in RAG router invocation**  
   - Async-to-thread fallback path in [rag/vector_store.py](rag/vector_store.py#L235-L245) works but increases complexity and operational risk.

---

## 5) Go Code Audit

## Strengths

- Clean package boundaries (`dispatcher`, `modes`, `tools`, `actions`).
- Reasonable error handling around external HTTP calls.
- Build/package health check succeeded (`go test ./...` with no compile failures).

## Issues

1. **Cross-platform limitation by design**  
   - AppleScript and `afplay` are hard requirements: [internal/actions/system.go](internal/actions/system.go#L30), [internal/actions/system.go](internal/actions/system.go#L47).

2. **Work mode hardcodes app-specific/macOS session behavior**  
   - [internal/modes/work.go](internal/modes/work.go#L18-L58) launches fixed apps and hardcoded commands.

3. **Wikipedia intent extraction quality issue**  
   - In [internal/tools/router.go](internal/tools/router.go#L94-L101), `WikiTopic` is set to first token of the whole input, not topic phrase.

---

## 6) Chainlit Audit

## Strengths

- Dynamic local model selection from Ollama tags: [chat_ui.py](chat_ui.py#L502-L519).
- FastAPI endpoints integrated for STT/command/web/rag toggles.

## Security and config concerns

1. **CORS open to all origins**: [\.chainlit/config.toml](.chainlit/config.toml#L23)  
2. **Unsafe HTML rendering enabled**: [\.chainlit/config.toml](.chainlit/config.toml#L27)  
3. **Broad spontaneous file upload policy**: [\.chainlit/config.toml](.chainlit/config.toml#L58-L72)

These are acceptable for a strictly local trusted environment, but high risk if exposed beyond localhost.

---

## 7) Ollama + Qwen3:8B Q4 Audit

## Current state

- Provider is Ollama: [config.json](config.json#L3)
- Active model is `qwen3:8b`: [config.json](config.json#L4)
- Embeddings model is `bge-m3`: [config.json](config.json#L5)
- Vision model is `llava`: [config.json](config.json#L6)

## Assessment

- Dynamic model switching is implemented in Chainlit UI.
- Ollama is consistently local (`127.0.0.1:11434`) in most modules.
- Quantization specificity (`Q4`) is not encoded in config; it depends on local Ollama tag naming and pulled model variant.

---

## 8) LanceDB + SQLite Audit

## SQLite (memory)

- DB path and init are straightforward: [memory/db.py](memory/db.py#L8-L49)
- Thread-isolated chat history uses `thread_id`: [memory/db.py](memory/db.py#L26), [memory/db.py](memory/db.py#L71)

Gap vs instruction goals:

- No explicit memory inspection/correction/deletion/export API surface is implemented in app-level commands/endpoints.

## LanceDB (RAG)

- Three logical tables are implemented: [rag/vector_store.py](rag/vector_store.py#L24-L27)
- Schema includes `source`, `page`, `category`: [rag/vector_store.py](rag/vector_store.py#L71-L75)

Important consistency issue:

- Active DB path is `.lancedb`: [rag/vector_store.py](rag/vector_store.py#L18)
- Workspace also contains `lancedb_data/` folder, creating potential operator confusion over which store is authoritative.

---

## 9) RAG Quality, Hybrid Retrieval, Metadata Filtering, Graph RAG Feasibility

## Current RAG behavior

- Routing intent chooses one table or all: [rag/vector_store.py](rag/vector_store.py#L247-L258)
- Retrieval returns only text snippets: [rag/vector_store.py](rag/vector_store.py#L262-L264)

Gaps:

1. **Source attribution not surfaced in answer context** (only snippet text is returned).  
2. **No hybrid retrieval** (no lexical BM25/keyword rank fusion).  
3. **No metadata filtering on query-time path** despite category metadata existing.  
4. **No retrieval quality evaluation pipeline.**

## Graph RAG feasibility

- No graph schema, extraction pipeline, or graph query layer is present.
- Given current corpus scale and architecture maturity, Graph RAG is **not yet justified**.
- Recommended path: stabilize vector+hybrid retrieval and provenance first, then trial relationship extraction on a narrow domain.

---

## 10) MCP Audit

## Observed

- Modules are named as MCP servers but currently act as local helper modules.
- Chainlit MCP feature is disabled: [\.chainlit/config.toml](.chainlit/config.toml#L81)

Assessment:

- “MCP integration” exists as architecture intent, not as full protocol-level runtime management/discovery/permissions UI.
- No explicit per-tool authorization workflow was found for these internal helper calls.

---

## 11) Web Scraping & External Data Audit

## Implemented

- DuckDuckGo HTML search + subpage crawl in Go: [internal/tools/web.go](internal/tools/web.go#L34-L38), [internal/tools/web.go](internal/tools/web.go#L63-L103)
- External APIs for crypto/weather/time/wiki: [internal/tools/api.go](internal/tools/api.go#L31), [internal/tools/api.go](internal/tools/api.go#L73), [internal/tools/api.go](internal/tools/api.go#L102), [internal/tools/api.go](internal/tools/api.go#L130), [internal/tools/api.go](internal/tools/api.go#L159)

Risks:

- No robust content trust boundary or sanitization strategy beyond basic text cleaning.
- Web-sourced content can enter prompt context directly in [chat_ui.py](chat_ui.py#L321-L327).

---

## 12) Vosk / Voice Pipeline Audit

## Implemented

- Offline Vosk models integrated in Chainlit and standalone listener: [chat_ui.py](chat_ui.py#L355-L370), [listen.py](listen.py#L50-L54)
- STT endpoints and command dispatch endpoints exist: [chat_ui.py](chat_ui.py#L420-L468)

Risks / limitations:

- Model paths are hardcoded to local directory structure.
- Resource usage controls are basic (no adaptive profile selection).

---

## 13) Desktop Readiness & Cross-Platform Compatibility

## Desktop readiness

- Chainlit-based desktop-like local UX is functional.
- No dedicated native desktop shell (Tauri/Electron/etc.) detected.

## Cross-platform

- Current automation core is macOS-specific (AppleScript, app names, Space switching, `afplay`).
- Linux/Windows compatibility exists only for non-automation portions unless substantial adapter layer is added.

Evidence: [internal/actions/system.go](internal/actions/system.go#L30-L81), [internal/modes/work.go](internal/modes/work.go#L18-L58).

---

## 14) Security & Privacy Audit

## Positive

- Local-first model/runtime usage is consistent for core LLM, embeddings, and vision.
- No hardcoded cloud API keys detected in audited app source files.

## Findings

1. **P0/P1 surface if non-local exposure occurs:** permissive CORS + unsafe HTML in Chainlit config.  
2. **Prompt-injection risk from web content:** external text is included in model context without explicit instruction hardening/sandboxing policy.  
3. **Sensitive voice command endpoints:** no authentication layer visible for local HTTP endpoints.

---

## 15) M2 16 GB RAM Performance Readiness (Evidence-based only)

Observed from code/config (no synthetic benchmark claims):

- Inference context set to `num_ctx=8192`: [chat_ui.py](chat_ui.py#L675)
- Max generated tokens `num_predict=4096`: [chat_ui.py](chat_ui.py#L674)
- Embeddings and vision are on-demand per operation.

Assessment:

- Architecture is plausible for M2 16 GB if model loading remains sequential and workloads are moderated.
- No runtime telemetry, memory budget enforcement, or benchmark logging was found.
- Therefore, no quantitative performance claim can be made.

---

## 16) Documentation and Repository Hygiene Findings

1. **README command mismatch**  
   - Build command references non-existent path `cmd/ark/main.go`: [README.md](README.md#L147)
   - Actual entry file is [main.go](main.go)

2. **README dependency mismatch**  
   - Mentions `pip install -r requirements.txt`: [README.md](README.md#L152)
   - `requirements.txt` is not present in repository.

3. **Go version declaration unusual**  
   - [go.mod](go.mod#L3) declares `go 1.26.2`; verify tooling expectations across environments.

---

## 17) Prioritized Implementation Plan (P0/P1/P2/P3)

## P0 (Immediate)

1. **Fix RAG router Ollama host bug**  
   - Scope: [mcp_servers/router_mcp.py](mcp_servers/router_mcp.py#L96)  
   - Complexity: Low  
   - Dependencies: None  
   - Risk: Very low  
   - Benefit: Restores semantic route accuracy; prevents silent fallback-heavy behavior.

2. **Harden Chainlit security defaults for local-first safe operation**  
   - Scope: [\.chainlit/config.toml](.chainlit/config.toml#L23), [\.chainlit/config.toml](.chainlit/config.toml#L27)  
   - Complexity: Low  
   - Dependencies: Deployment mode decision (localhost-only vs LAN)  
   - Risk: Medium (may affect current UI behavior/content rendering)  
   - Benefit: Reduces cross-origin and content-injection exposure.

## P1 (High Priority)

3. **Add source attribution to RAG responses**  
   - Scope: [rag/vector_store.py](rag/vector_store.py#L262-L264), [chat_ui.py](chat_ui.py)  
   - Complexity: Medium  
   - Dependencies: Retrieval payload shape update  
   - Risk: Low-Medium  
   - Benefit: Traceability, user trust, auditability.

4. **Introduce query-time metadata filtering and hybrid retrieval baseline**  
   - Scope: [rag/vector_store.py](rag/vector_store.py)  
   - Complexity: Medium-High  
   - Dependencies: indexing metadata normalization, ranking strategy  
   - Risk: Medium  
   - Benefit: better precision/recall, lower hallucination risk.

5. **Unify vector DB location strategy (.lancedb vs lancedb_data)**  
   - Scope: [rag/vector_store.py](rag/vector_store.py#L18) + ops docs  
   - Complexity: Medium  
   - Dependencies: migration plan  
   - Risk: Medium (data migration)  
   - Benefit: operational clarity and backup consistency.

## P2 (Important)

6. **Cross-platform adapter layer for automation actions**  
   - Scope: [internal/actions/system.go](internal/actions/system.go), mode files  
   - Complexity: High  
   - Dependencies: OS capability matrix, interface contracts  
   - Risk: Medium-High  
   - Benefit: unlock Windows/Linux support without rewriting orchestration.

7. **Session-safe state handling for web/rag toggles**  
   - Scope: [chat_ui.py](chat_ui.py#L88), [chat_ui.py](chat_ui.py#L472-L483)  
   - Complexity: Medium  
   - Dependencies: per-thread/per-user session strategy  
   - Risk: Low-Medium  
   - Benefit: avoids state bleed across sessions.

8. **Memory management APIs (inspect/correct/delete/export)**  
   - Scope: [memory/db.py](memory/db.py), UI/endpoint layer  
   - Complexity: Medium  
   - Dependencies: authorization decisions  
   - Risk: Medium  
   - Benefit: aligns with privacy/governance requirements.

## P3 (Strategic)

9. **Performance telemetry and profiling for M2 16 GB**  
   - Scope: inference timings, memory snapshots, ingestion timings  
   - Complexity: Medium  
   - Dependencies: logging/metrics policy  
   - Risk: Low  
   - Benefit: evidence-based model/profile tuning.

10. **Graph RAG pilot only after retrieval maturity milestones**  
   - Scope: narrow-domain relationship extraction + graph index POC  
   - Complexity: High  
   - Dependencies: strong provenance + hybrid retrieval first  
   - Risk: Medium-High  
   - Benefit: measurable gains for relationship-heavy queries only.

---

## 18) Executive Summary

- Local tracked code and GitHub main are in sync at the same commit.
- Core local-first architecture is functional, with Ollama + Chainlit + SQLite + LanceDB integrated.
- The most critical technical defect is the malformed Ollama host in the RAG intent router.
- Security hardening is required before any non-localhost exposure (CORS, unsafe HTML, endpoint protection).
- Cross-platform support is currently limited by explicit macOS automation coupling.
- RAG foundation is solid but still lacks source attribution, metadata filtering, and hybrid retrieval.
- Graph RAG should be deferred until baseline retrieval quality and provenance are strengthened.
