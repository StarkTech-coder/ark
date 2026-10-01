"""Local embedded Qdrant vector store controller for ARK RAG engine."""

import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

# Absolute path targeting project directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "qdrant_data")

# Embedded local file storage (No Docker container required)
client = QdrantClient(path=DB_PATH)

# Local HuggingFace embedding model (cached on disk)
encoder = SentenceTransformer("all-MiniLM-L6-v2")
COLLECTION_NAME = "ark_knowledge_base"


def init_vector_store() -> None:
    """Initializes local Qdrant collection if not already existing."""
    if not client.collection_exists(COLLECTION_NAME):
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )


def query_context(query_text: str, top_k: int = 3) -> list[str]:
    """Retrieves relevant context snippets for RAG augmentation."""
    query_vector = encoder.encode(query_text).tolist()

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        limit=top_k,
    )

    return [hit.payload["text"] for hit in results if hit.payload]
