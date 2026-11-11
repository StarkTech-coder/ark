"""Local embedded LanceDB vector store controller for ARK RAG engine.

Supports 3-tier modular tables: University, Code, and Relationship (Sliding Window Chunking).
"""

import asyncio
import concurrent.futures
import hashlib
import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import lancedb
import pyarrow as pa

from llm.config import get_embedding_dimension, get_embedding_model, get_ollama_host
from mcp_servers.router_mcp import route_query_intent
from runtime.paths import resolve_lancedb_path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = str(resolve_lancedb_path())

db = lancedb.connect(DB_PATH)

# 3-Tier Modular Table Names
UNIVERSITY_TABLE = "university_knowledge_base"
CODE_TABLE = "code_knowledge_base"
RELATIONSHIP_TABLE = "relationship_knowledge_base"
WHATSAPP_TABLE = "whatsapp_knowledge_base"

EMBED_DIM = 1024
EMBEDDING_META_PATH = os.path.join(DB_PATH, "embedding_meta.json")

VALID_DOMAINS = {"personal", "messages", "university", "starktech", "projects"}

DOMAIN_TO_TABLE_PREFERENCE = {
    "messages": [RELATIONSHIP_TABLE, WHATSAPP_TABLE],
    "university": [UNIVERSITY_TABLE],
    "projects": [CODE_TABLE],
    "starktech": [CODE_TABLE],
    "personal": [RELATIONSHIP_TABLE],
}


@dataclass(frozen=True)
class RetrievalConfig:
    vector_top_k: int = 10
    keyword_top_k: int = 10
    max_scan_rows: int = 300
    hybrid_alpha: float = 0.65


def _safe_table_names() -> list[str]:
    try:
        raw_names: list[Any] = []
        if hasattr(db, "list_tables"):
            response = db.list_tables()
            if isinstance(response, (list, tuple)):
                raw_names = list(response)
            elif hasattr(response, "tables"):
                tables_value = getattr(response, "tables", None)
                if isinstance(tables_value, (list, tuple)):
                    raw_names = list(tables_value)
                else:
                    raw_names = []
            else:
                raw_names = []
        else:
            raw_names = list(db.table_names())

        normalized: list[str] = []
        for item in raw_names:
            if isinstance(item, str):
                normalized.append(item)
                continue
            if isinstance(item, (list, tuple)) and item:
                first = item[0]
                if isinstance(first, str):
                    normalized.append(first)
                continue
            if isinstance(item, dict):
                maybe_name = item.get("name")
                if isinstance(maybe_name, str):
                    normalized.append(maybe_name)
        return normalized
    except Exception:
        return []


def _normalize_domain(domain: str) -> str:
    normalized = (domain or "").strip().lower()
    if normalized not in VALID_DOMAINS:
        raise ValueError(f"Unsupported domain: {domain}")
    return normalized


def _normalize_authorized_domains(
    authorized_domains: list[str] | None,
    *,
    default_domain: str = "projects",
) -> list[str]:
    if not authorized_domains:
        return [_normalize_domain(default_domain)]
    return [_normalize_domain(d) for d in authorized_domains]


def _infer_domain(category: str | None, table_name: str) -> str:
    category_value = (category or "").strip().lower()
    if category_value in VALID_DOMAINS:
        return category_value

    legacy_map = {
        "relationship": "messages",
        "whatsapp": "messages",
        "university": "university",
        "code": "projects",
    }
    if category_value in legacy_map:
        return legacy_map[category_value]

    lower_table = table_name.lower()
    if "university" in lower_table:
        return "university"
    if "relationship" in lower_table or "whatsapp" in lower_table or "message" in lower_table:
        return "messages"
    if "starktech" in lower_table:
        return "starktech"
    if "code" in lower_table or "project" in lower_table:
        return "projects"
    return "personal"


def _table_fields(table_name: str) -> set[str]:
    try:
        schema = db.open_table(table_name).schema
        return set(schema.names)
    except Exception:
        return set()


def _resolve_title(source: str, row: dict[str, Any]) -> str:
    title = str(row.get("title", "")).strip() if "title" in row else ""
    if title:
        return title
    source_value = (source or "").strip()
    if not source_value:
        return "unknown"
    stem = Path(source_value).stem.strip()
    return stem or source_value


def _resolve_document_id(table_name: str, row: dict[str, Any]) -> str:
    doc_id = str(row.get("document_id", "")).strip() if "document_id" in row else ""
    if doc_id:
        return doc_id

    source = str(row.get("source", "")).strip()
    page = str(row.get("page", "")).strip()
    text = str(row.get("text", ""))[:200]
    fingerprint = f"{table_name}|{source}|{page}|{text}".encode("utf-8", errors="ignore")
    return hashlib.sha1(fingerprint).hexdigest()[:20]


def _score_from_distance(distance: float | None) -> float:
    if distance is None:
        return 0.0
    if distance < 0:
        return 0.0
    return 1.0 / (1.0 + distance)


def _keyword_score(query: str, text: str) -> float:
    query_terms = [t for t in re.findall(r"\w+", query.lower()) if t]
    text_terms = re.findall(r"\w+", text.lower())
    if not query_terms or not text_terms:
        return 0.0

    text_len = len(text_terms)
    tf_total = 0.0
    for term in query_terms:
        count = text_terms.count(term)
        if count > 0:
            tf_total += count / text_len

    if tf_total <= 0:
        return 0.0
    normalization = math.log(1 + len(query_terms))
    return tf_total / normalization


def get_embedding_model_name() -> str:
    """Read embedding model name from config.json dynamically, defaulting to bge-m3 if missing."""
    return get_embedding_model()


def get_embedding(text: str) -> list[float]:
    """Generate vector embedding for target text using local Ollama embedding endpoint."""
    model_name = get_embedding_model_name()
    ollama_host = get_ollama_host()
    try:
        response = httpx.post(
            f"{ollama_host}/api/embeddings",
            json={"model": model_name, "prompt": text},
            timeout=15.0,
        )
        if response.status_code == 200:
            return response.json().get("embedding", [])
    except Exception as e:
        print(f"[ARK EMBEDDING ERROR] {e}")
    return []


def _load_embedding_meta() -> dict[str, dict[str, int | str]]:
    if not os.path.exists(EMBEDDING_META_PATH):
        return {}
    try:
        with open(EMBEDDING_META_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_embedding_meta(meta: dict[str, dict[str, int | str]]) -> None:
    try:
        os.makedirs(os.path.dirname(EMBEDDING_META_PATH), exist_ok=True)
        with open(EMBEDDING_META_PATH, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _assert_embedding_compatibility(table_name: str, expected_dim: int) -> None:
    model_name = get_embedding_model_name()
    meta = _load_embedding_meta()
    current = meta.get(table_name)

    if current is None:
        has_rows = False
        if table_name in _safe_table_names():
            try:
                table = db.open_table(table_name)
                has_rows = table.search().limit(1).to_arrow().num_rows > 0
            except Exception:
                has_rows = False

        if has_rows:
            raise RuntimeError(
                f"Embedding metadata missing for non-empty table '{table_name}'. "
                "Refusing writes to avoid silent vector mixing."
            )

        meta[table_name] = {
            "embedding_model": model_name,
            "embedding_dim": expected_dim,
        }
        _save_embedding_meta(meta)
        return

    existing_model = str(current.get("embedding_model", "")).strip()
    existing_dim = int(current.get("embedding_dim", expected_dim))

    if existing_model and existing_model != model_name:
        raise RuntimeError(
            f"Embedding model mismatch for table '{table_name}': "
            f"stored='{existing_model}', current='{model_name}'."
        )

    if existing_dim != expected_dim:
        raise RuntimeError(
            f"Embedding dimension mismatch for table '{table_name}': "
            f"stored={existing_dim}, current={expected_dim}."
        )


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of text strings."""
    return [get_embedding(t) for t in texts]


def get_or_create_table(table_name: str):
    """Initialize or retrieve a specified local LanceDB table."""
    if table_name in _safe_table_names():
        return db.open_table(table_name)

    schema = pa.schema(
        [
            ("vector", pa.list_(pa.float32(), EMBED_DIM)),
            ("text", pa.string()),
            ("source", pa.string()),
            ("page", pa.string()),
            ("category", pa.string()),
        ]
    )
    return db.create_table(table_name, schema=schema)


def _tables_for_domains(domains: list[str]) -> list[str]:
    available = set(_safe_table_names())
    selected: list[str] = []
    for domain in domains:
        for table_name in DOMAIN_TO_TABLE_PREFERENCE.get(domain, []):
            if table_name in available and table_name not in selected:
                selected.append(table_name)
    return selected


def _tables_for_target_intent(target_intent: str) -> list[str]:
    available = set(_safe_table_names())
    if target_intent == RELATIONSHIP_TABLE:
        result = [RELATIONSHIP_TABLE, WHATSAPP_TABLE]
    elif target_intent == UNIVERSITY_TABLE:
        result = [UNIVERSITY_TABLE]
    elif target_intent == CODE_TABLE:
        result = [CODE_TABLE]
    else:
        # Keep broad intent deterministic but still bounded to known legacy tables.
        result = [RELATIONSHIP_TABLE, WHATSAPP_TABLE, UNIVERSITY_TABLE, CODE_TABLE]
    return [name for name in result if name in available]


def _vector_hits(
    table_name: str,
    query_vector: list[float],
    limit: int,
) -> list[dict[str, Any]]:
    table = db.open_table(table_name)
    arrow = table.search(query_vector).limit(limit).to_arrow()
    columns = set(arrow.schema.names)
    text_col = arrow.column("text").to_pylist() if "text" in columns else []
    source_col = arrow.column("source").to_pylist() if "source" in columns else [""] * len(text_col)
    page_col = arrow.column("page").to_pylist() if "page" in columns else [""] * len(text_col)
    category_col = (
        arrow.column("category").to_pylist()
        if "category" in columns
        else [""] * len(text_col)
    )
    doc_id_col = (
        arrow.column("document_id").to_pylist()
        if "document_id" in columns
        else [""] * len(text_col)
    )
    title_col = (
        arrow.column("title").to_pylist()
        if "title" in columns
        else [""] * len(text_col)
    )
    distance_col = (
        arrow.column("_distance").to_pylist()
        if "_distance" in columns
        else [None] * len(text_col)
    )

    rows: list[dict[str, Any]] = []
    for idx, text in enumerate(text_col):
        rows.append(
            {
                "table": table_name,
                "text": str(text or ""),
                "source": str(source_col[idx] or ""),
                "page": str(page_col[idx] or ""),
                "category": str(category_col[idx] or ""),
                "document_id": str(doc_id_col[idx] or ""),
                "title": str(title_col[idx] or ""),
                "distance": distance_col[idx],
            }
        )
    return rows


def _keyword_hits(table_name: str, query_text: str, cfg: RetrievalConfig) -> list[dict[str, Any]]:
    table = db.open_table(table_name)

    # Prefer native Lance keyword retrieval where available.
    try:
        arrow = table.search(query_text).limit(cfg.keyword_top_k).to_arrow()
        columns = set(arrow.schema.names)
        if "text" in columns:
            text_col = arrow.column("text").to_pylist()
            source_col = arrow.column("source").to_pylist() if "source" in columns else [""] * len(text_col)
            page_col = arrow.column("page").to_pylist() if "page" in columns else [""] * len(text_col)
            category_col = (
                arrow.column("category").to_pylist() if "category" in columns else [""] * len(text_col)
            )
            doc_id_col = (
                arrow.column("document_id").to_pylist() if "document_id" in columns else [""] * len(text_col)
            )
            title_col = (
                arrow.column("title").to_pylist() if "title" in columns else [""] * len(text_col)
            )
            rows: list[dict[str, Any]] = []
            for idx, text in enumerate(text_col):
                rows.append(
                    {
                        "table": table_name,
                        "text": str(text or ""),
                        "source": str(source_col[idx] or ""),
                        "page": str(page_col[idx] or ""),
                        "category": str(category_col[idx] or ""),
                        "document_id": str(doc_id_col[idx] or ""),
                        "title": str(title_col[idx] or ""),
                        "keyword_score": _keyword_score(query_text, str(text or "")),
                    }
                )
            rows.sort(key=lambda x: x.get("keyword_score", 0.0), reverse=True)
            return rows[: cfg.keyword_top_k]
    except Exception:
        pass

    # Fallback: scan a bounded number of rows and perform lexical scoring.
    try:
        arrow = table.search().limit(cfg.max_scan_rows).to_arrow()
    except Exception:
        return []

    columns = set(arrow.schema.names)
    if "text" not in columns:
        return []

    text_col = arrow.column("text").to_pylist()
    source_col = arrow.column("source").to_pylist() if "source" in columns else [""] * len(text_col)
    page_col = arrow.column("page").to_pylist() if "page" in columns else [""] * len(text_col)
    category_col = (
        arrow.column("category").to_pylist() if "category" in columns else [""] * len(text_col)
    )
    doc_id_col = (
        arrow.column("document_id").to_pylist() if "document_id" in columns else [""] * len(text_col)
    )
    title_col = (
        arrow.column("title").to_pylist() if "title" in columns else [""] * len(text_col)
    )

    rows: list[dict[str, Any]] = []
    for idx, text in enumerate(text_col):
        text_value = str(text or "")
        score = _keyword_score(query_text, text_value)
        if score <= 0:
            continue
        rows.append(
            {
                "table": table_name,
                "text": text_value,
                "source": str(source_col[idx] or ""),
                "page": str(page_col[idx] or ""),
                "category": str(category_col[idx] or ""),
                "document_id": str(doc_id_col[idx] or ""),
                "title": str(title_col[idx] or ""),
                "keyword_score": score,
            }
        )
    rows.sort(key=lambda x: x.get("keyword_score", 0.0), reverse=True)
    return rows[: cfg.keyword_top_k]


def retrieve_context_with_sources(
    query_text: str,
    *,
    top_k: int = 3,
    authorized_domains: list[str] | None = None,
    allow_cross_domain: bool = False,
    retrieval_mode: str = "hybrid",
    config: RetrievalConfig | None = None,
    target_intent_override: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve RAG context with explicit source attribution and domain isolation.

    This function preserves backward compatibility with legacy tables by inferring
    domain/category metadata when explicit fields are not present.
    """

    cfg = config or RetrievalConfig()
    mode = (retrieval_mode or "hybrid").strip().lower()
    if mode not in {"vector", "keyword", "hybrid"}:
        mode = "hybrid"

    if authorized_domains and len(authorized_domains) > 1 and not allow_cross_domain:
        raise PermissionError(
            "Cross-domain retrieval requires explicit authorization."
        )

    # Determine intent and candidate tables.
    if target_intent_override:
        target_intent = target_intent_override
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor() as pool:
                target_intent = pool.submit(
                    asyncio.run, route_query_intent(query_text)
                ).result()
        else:
            target_intent = asyncio.run(route_query_intent(query_text))

    if target_intent == RELATIONSHIP_TABLE:
        default_domain = "messages"
    elif target_intent == UNIVERSITY_TABLE:
        default_domain = "university"
    elif target_intent == CODE_TABLE:
        default_domain = "projects"
    else:
        # No cross-domain by default.
        default_domain = "projects"

    domains = _normalize_authorized_domains(authorized_domains, default_domain=default_domain)

    if len(domains) > 1 and not allow_cross_domain:
        raise PermissionError(
            "Cross-domain retrieval requires explicit authorization."
        )

    intent_tables = _tables_for_target_intent(target_intent)
    domain_tables = _tables_for_domains(domains)
    # Keep intersection if both are defined, otherwise whichever is specific.
    if intent_tables and domain_tables:
        candidate_tables = [t for t in intent_tables if t in set(domain_tables)]
    else:
        candidate_tables = intent_tables or domain_tables

    if not candidate_tables:
        return []

    query_vector = get_embedding(query_text)
    expected_dim = get_embedding_dimension(get_embedding_model_name())
    can_vector = bool(query_vector and len(query_vector) == expected_dim)

    combined: dict[str, dict[str, Any]] = {}

    for table_name in candidate_tables:
        rows_vector: list[dict[str, Any]] = []
        rows_keyword: list[dict[str, Any]] = []

        if mode in {"vector", "hybrid"} and can_vector:
            try:
                rows_vector = _vector_hits(table_name, query_vector, cfg.vector_top_k)
            except Exception:
                rows_vector = []

        if mode in {"keyword", "hybrid"}:
            rows_keyword = _keyword_hits(table_name, query_text, cfg)

        # If vector unavailable in vector-only mode, gracefully fallback to keyword.
        if mode == "vector" and not rows_vector:
            rows_keyword = _keyword_hits(table_name, query_text, cfg)

        for row in rows_vector:
            category = row.get("category", "")
            inferred_domain = _infer_domain(str(category), table_name)
            if inferred_domain not in domains:
                continue

            doc_id = _resolve_document_id(table_name, row)
            existing = combined.get(doc_id)
            vector_score = _score_from_distance(row.get("distance"))
            base_payload = {
                "document_id": doc_id,
                "text": row.get("text", ""),
                "source": row.get("source", ""),
                "title": _resolve_title(str(row.get("source", "")), row),
                "page": row.get("page", ""),
                "domain": inferred_domain,
                "category": category,
                "table": table_name,
                "vector_score": vector_score,
                "keyword_score": 0.0,
                "score": vector_score,
            }
            if existing is None or base_payload["score"] > existing["score"]:
                combined[doc_id] = base_payload

        for row in rows_keyword:
            category = row.get("category", "")
            inferred_domain = _infer_domain(str(category), table_name)
            if inferred_domain not in domains:
                continue

            doc_id = _resolve_document_id(table_name, row)
            keyword_score = float(row.get("keyword_score", 0.0) or 0.0)
            existing = combined.get(doc_id)
            if existing is None:
                combined[doc_id] = {
                    "document_id": doc_id,
                    "text": row.get("text", ""),
                    "source": row.get("source", ""),
                    "title": _resolve_title(str(row.get("source", "")), row),
                    "page": row.get("page", ""),
                    "domain": inferred_domain,
                    "category": category,
                    "table": table_name,
                    "vector_score": 0.0,
                    "keyword_score": keyword_score,
                    "score": keyword_score,
                }
            else:
                existing["keyword_score"] = max(existing.get("keyword_score", 0.0), keyword_score)

    if not combined:
        return []

    alpha = max(0.0, min(1.0, cfg.hybrid_alpha))
    for item in combined.values():
        vector_score = float(item.get("vector_score", 0.0))
        keyword_score = float(item.get("keyword_score", 0.0))
        if mode == "vector":
            item["score"] = vector_score if vector_score > 0 else keyword_score
        elif mode == "keyword":
            item["score"] = keyword_score
        else:
            item["score"] = (alpha * vector_score) + ((1 - alpha) * keyword_score)

    ranked = sorted(combined.values(), key=lambda x: x.get("score", 0.0), reverse=True)
    return ranked[: max(1, top_k)]


def is_file_already_indexed(file_name: str, table_name: str) -> bool:
    """Check if a file has already been indexed in the specified table."""
    if table_name not in _safe_table_names():
        return False
    try:
        table = db.open_table(table_name)
        sources = (
            table.search().select(["source"]).to_arrow().column("source").to_pylist()
        )
        return file_name in sources
    except Exception:
        return False


def insert_documents(
    texts: list[str],
    source_name: str = "manual",
    page: str = "1",
    category: str = "university",
):
    """Insert documents into the correct modular table based on category."""
    if category == "relationship":
        target_table_name = RELATIONSHIP_TABLE
    elif category == "code":
        target_table_name = CODE_TABLE
    else:
        target_table_name = UNIVERSITY_TABLE

    if is_file_already_indexed(source_name, target_table_name):
        print(
            f"⏩ [ARK RAG INGEST] '{source_name}' is already indexed in '{target_table_name}'. Skipping."
        )
        return

    table = get_or_create_table(target_table_name)
    model_name = get_embedding_model_name()
    expected_dim = get_embedding_dimension(model_name)
    _assert_embedding_compatibility(target_table_name, expected_dim)

    print(
        f"[ARK RAG INGEST] Embedding {len(texts)} chunks for source: {source_name} into '{target_table_name}'..."
    )

    embeddings = get_embeddings_batch(texts)
    data = [
        {
            "vector": vec,
            "text": txt,
            "source": source_name,
            "page": str(page),
            "category": category,
        }
        for vec, txt in zip(embeddings, texts)
        if vec and len(vec) == expected_dim
    ]

    invalid_count = len(texts) - len(data)
    if invalid_count > 0:
        raise RuntimeError(
            f"Embedding dimension validation failed for {invalid_count} chunk(s). "
            f"Expected dimension: {expected_dim}, model: {model_name}."
        )

    if data:
        table.add(data)
        print(
            f"[ARK RAG INGEST] Successfully inserted {len(data)} vectors into '{target_table_name}'."
        )


def parse_and_chunk_whatsapp_chat(
    file_path: str, window_size: int = 12, overlap: int = 3
) -> list[dict]:
    """Read chat log line by line and generate chunks using a sliding window strategy."""
    pattern = re.compile(r"^(\d{2}\.\d{2}\.\d{4} \d{2}:\d{2}) (.*?): (.*)$")
    messages = []

    if not os.path.exists(file_path):
        print(f"[CHAT PARSER] File not found: {file_path}")
        return []

    with open(file_path, "r", encoding="utf-8") as f:
        current_msg = None
        for line in f:
            line_str = line.strip()
            match = pattern.match(line_str)
            if match:
                if current_msg:
                    messages.append(current_msg)
                ts, author, content = match.groups()
                current_msg = {"timestamp": ts, "author": author, "content": content}
            else:
                if current_msg:
                    current_msg["content"] += "\n" + line_str

        if current_msg:
            messages.append(current_msg)

    # Sliding Window Chunking
    chunks = []
    source_name = os.path.basename(file_path)

    for i in range(0, len(messages), window_size - overlap):
        window_msgs = messages[i : i + window_size]
        if not window_msgs:
            continue

        block_text = "\n".join(
            [f"[{m['timestamp']}] {m['author']}: {m['content']}" for m in window_msgs]
        )
        start_ts = window_msgs[0]["timestamp"]
        end_ts = window_msgs[-1]["timestamp"]

        chunks.append(
            {
                "text": block_text,
                "source": source_name,
                "page": f"chat_{i // (window_size - overlap) + 1} ({start_ts} to {end_ts})",
                "category": "relationship",
            }
        )

    return chunks


def smart_chunk_pdf_text(
    full_text: str,
    source_name: str,
    chunk_size: int = 500,
    overlap: int = 50,
    category: str = "university",
) -> list[dict]:
    """Smart chunking for PDF documents and code files."""
    paragraphs = full_text.split("\n\n")
    chunks = []

    for p_idx, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue

        for i in range(0, len(para), chunk_size - overlap):
            chunk_text = para[i : i + chunk_size]
            if len(chunk_text.strip()) > 20:
                chunks.append(
                    {
                        "text": chunk_text,
                        "source": source_name,
                        "page": f"p.{p_idx + 1}",
                        "category": category,
                    }
                )
    return chunks


def query_context(query_text: str, top_k: int = 3) -> list[str]:
    """Backward-compatible text-only context retrieval for chat prompts.

    Uses a single authorized domain by default to prevent accidental cross-domain
    retrieval. Use `retrieve_context_with_sources` for explicit multi-domain access.
    """

    results = retrieve_context_with_sources(
        query_text,
        top_k=top_k,
        authorized_domains=None,
        allow_cross_domain=False,
        retrieval_mode="hybrid",
    )
    return [str(item.get("text", "")) for item in results if item.get("text")]


def query_context_with_sources(
    query_text: str,
    *,
    top_k: int = 3,
    authorized_domains: list[str] | None = None,
    allow_cross_domain: bool = False,
    retrieval_mode: str = "hybrid",
    config: RetrievalConfig | None = None,
) -> list[dict[str, Any]]:
    """Public source-aware retrieval API for citation-ready ARK responses."""
    return retrieve_context_with_sources(
        query_text,
        top_k=top_k,
        authorized_domains=authorized_domains,
        allow_cross_domain=allow_cross_domain,
        retrieval_mode=retrieval_mode,
        config=config,
    )
