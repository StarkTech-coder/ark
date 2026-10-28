"""
Local embedded LanceDB vector store controller for ARK RAG engine.
Optimized with Local Ollama bge-m3 Multilingual Embeddings & Detailed Terminal Debugging.
"""

import os
import lancedb
import pyarrow as pa
import httpx

# Absolute path targeting project root directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "lancedb_data")

# Initialize local LanceDB connection (Embedded, no Docker required)
db = lancedb.connect(DB_PATH)

# Default tables
DEFAULT_TABLE = "ark_knowledge_base"
ACADEMIC_TABLE = "academic_pdf_kb"

# Embedding dimension for bge-m3 is 1024
EMBED_DIM = 1024


def get_embedding(text: str) -> list[float]:
    """Retrieves 1024-dim multilingual embedding vector from local Ollama bge-m3 model."""
    try:
        response = httpx.post(
            "http://127.0.0.1:11434/api/embeddings",
            json={"model": "bge-m3", "prompt": text},
            timeout=15.0,
        )
        if response.status_code == 200:
            return response.json().get("embedding", [])
    except Exception as e:
        print(f"[ARK EMBEDDING ERROR] Failed to fetch bge-m3 embedding: {e}")
    return []


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Batch embedding generation using local Ollama bge-m3."""
    return [get_embedding(t) for t in texts]


def get_or_create_table(table_name: str = DEFAULT_TABLE):
    """Initializes or retrieves a specified local LanceDB table."""
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


def insert_documents(
    texts: list[str],
    source_name: str = "manual",
    page: str = "1",
    category: str = "general",
    is_academic: bool = False,
):
    """Embeds and inserts text documents with metadata into the correct vector collection."""
    target_table_name = ACADEMIC_TABLE if is_academic else DEFAULT_TABLE
    table = get_or_create_table(target_table_name)

    print(
        f"[ARK RAG INGEST] Embedding {len(texts)} chunks for source: {source_name}..."
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
            f"[ARK RAG INGEST] Successfully inserted {len(data)} vectors into LanceDB table '{target_table_name}'."
        )


def smart_chunk_pdf_text(
    full_text: str, source_name: str, chunk_size: int = 500, overlap: int = 50
) -> list[dict]:
    """Smart chunking strategy for academic PDFs with overlap and metadata preservation."""
    paragraphs = full_text.split("\n\n")
    chunks = []

    for p_idx, para in enumerate(paragraphs):
        para = para.strip()
        if not para:
            continue

        for i in range(0, len(para), chunk_size - overlap):
            chunk_text = para[i : i + chunk_size]
            if len(chunk_text.strip()) > 30:
                chunks.append(
                    {
                        "text": chunk_text,
                        "source": source_name,
                        "page": f"p.{p_idx + 1}",
                        "category": "academic",
                    }
                )
    return chunks


def query_context(
    query_text: str, top_k: int = 3, search_academic: bool = True
) -> list[str]:
    """Retrieves relevant context snippets and prints exact matched content to terminal."""
    target_table_name = ACADEMIC_TABLE if search_academic else DEFAULT_TABLE

    if target_table_name not in db.table_names():
        print(
            f"[ARK RAG QUERY] Table '{target_table_name}' does not exist yet in LanceDB."
        )
        return []

    table = db.open_table(target_table_name)
    query_vector = get_embedding(query_text)

    if not query_vector:
        print("[ARK RAG QUERY] Failed to generate embedding for query.")
        return []

    # Execute vector search on LanceDB
    results = table.search(query_vector).limit(top_k).to_arrow()
    snippets = results.column("text").to_pylist()

    # TERMINAL DEBUG PRINTS FOR 100% CERTAINTY
    print("\n" + "=" * 50)
    print(f"[ARK RAG DEBUG] Query: '{query_text}'")
    print(f"[ARK RAG DEBUG] Target Table: '{target_table_name}'")
    print(f"[ARK RAG DEBUG] Retrieved Snippets Count: {len(snippets)}")
    for idx, snippet in enumerate(snippets):
        print(f"  -> Snippet [{idx+1}]: {repr(snippet[:250])}...")
    print("=" * 50 + "\n")

    return snippets
