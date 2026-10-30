"""MCP LanceDB Server module.

Handles embedding generation, chunking, and vector insertion across 3 isolated knowledge bases.
"""

from typing import Any
from rag.vector_store import insert_documents, smart_chunk_pdf_text


def process_and_store_document(
    file_content: str, file_name: str, category: str
) -> bool:
    """Chunk document content and insert it into the appropriate category-mapped LanceDB table."""
    try:
        chunks = smart_chunk_pdf_text(file_content, source_name=file_name)
        if chunks:
            texts = [c["text"] for c in chunks]
            # category: 'relationship', 'university', or 'code'
            insert_documents(texts, source_name=file_name, category=category)
            print(
                f"[MCP LANCEDB] Successfully stored chunks for '{file_name}' under category/table: '{category}'"
            )
            return True
    except Exception as e:
        print(f"[MCP LANCEDB ERROR] Failed to store document {file_name}: {e}")
    return False
