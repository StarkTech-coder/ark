"""Local embedded LanceDB vector store controller for ARK RAG engine.

Supports 3-tier modular tables: University, Code, and Relationship (Sliding Window Chunking).
"""

import asyncio
import concurrent.futures
import json
import os
import re
import httpx
import lancedb
import pyarrow as pa

from mcp_servers.router_mcp import route_query_intent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, ".lancedb")
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

db = lancedb.connect(DB_PATH)

# 3-Tier Modular Table Names
UNIVERSITY_TABLE = "university_knowledge_base"
CODE_TABLE = "code_knowledge_base"
RELATIONSHIP_TABLE = "relationship_knowledge_base"

EMBED_DIM = 1024


def get_embedding_model_name() -> str:
    """Read embedding model name from config.json dynamically, defaulting to bge-m3 if missing."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config_data = json.load(f)
                return config_data.get("ai", {}).get("embedding_model", "bge-m3")
        except Exception:
            pass
    return "bge-m3"


def get_embedding(text: str) -> list[float]:
    """Generate vector embedding for target text using local Ollama embedding endpoint."""
    model_name = get_embedding_model_name()
    try:
        response = httpx.post(
            "http://127.0.0.1:11434/api/embeddings",
            json={"model": model_name, "prompt": text},
            timeout=15.0,
        )
        if response.status_code == 200:
            return response.json().get("embedding", [])
    except Exception as e:
        print(f"[ARK EMBEDDING ERROR] {e}")
    return []


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of text strings."""
    return [get_embedding(t) for t in texts]


def get_or_create_table(table_name: str):
    """Initialize or retrieve a specified local LanceDB table."""
    if table_name in db.table_names():
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


def is_file_already_indexed(file_name: str, table_name: str) -> bool:
    """Check if a file has already been indexed in the specified table."""
    if table_name not in db.table_names():
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
        if vec
    ]
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
    """Use query router to select target table and retrieve relevant context from vector store."""
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

    print(
        f"🎯 [ARK RAG ROUTER] Target Table Intent: '{target_intent}' for query: '{query_text[:40]}...'"
    )

    tables_to_search = []
    if target_intent == RELATIONSHIP_TABLE:
        tables_to_search = [RELATIONSHIP_TABLE]
    elif target_intent == UNIVERSITY_TABLE:
        tables_to_search = [UNIVERSITY_TABLE]
    elif target_intent == CODE_TABLE:
        tables_to_search = [CODE_TABLE]
    else:
        tables_to_search = [RELATIONSHIP_TABLE, UNIVERSITY_TABLE, CODE_TABLE]

    snippets = []
    query_vector = get_embedding(query_text)
    if not query_vector:
        return []

    for table_name in tables_to_search:
        if table_name in db.table_names():
            table = db.open_table(table_name)
            results = table.search(query_vector).limit(top_k).to_arrow()
            snippets.extend(results.column("text").to_pylist())

    snippets = snippets[:top_k]

    print("\n" + "=" * 50)
    print(f"[ARK RAG DEBUG] Query: '{query_text}'")
    print(f"[ARK RAG DEBUG] Tables Searched: {tables_to_search}")
    print(f"[ARK RAG DEBUG] Snippets Found: {len(snippets)}")
    print("=" * 50 + "\n")

    return snippets
