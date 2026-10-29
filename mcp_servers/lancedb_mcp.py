"""
MCP LanceDB Server: Handles embedding generation, chunking, and vector insertion.
"""

from rag.vector_store import insert_documents, smart_chunk_pdf_text


def process_and_store_document(file_content: str, file_name: str, is_academic: bool):
    """Chunks document content and inserts it into the appropriate LanceDB table."""
    try:
        chunks = smart_chunk_pdf_text(file_content, source_name=file_name)
        if chunks:
            texts = [c["text"] for c in chunks]
            insert_documents(texts, source_name=file_name, is_academic=is_academic)
            print(
                f"[MCP LANCEDB] Successfully stored chunks for '{file_name}' (Academic: {is_academic})"
            )
            return True
    except Exception as e:
        print(f"[MCP LANCEDB ERROR] Failed to store document {file_name}: {e}")
    return False
