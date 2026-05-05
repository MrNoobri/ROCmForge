"""Retrieve relevant chunks from the ChromaDB RAG collection."""

from pathlib import Path
from typing import Optional

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

CHROMA_DIR = Path(__file__).parent.parent / ".chroma"
COLLECTION_NAME = "rocmforge_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Module-level cache — loaded once on first retrieve() call
_collection: Optional[chromadb.Collection] = None


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)
    return _collection


def retrieve(query: str, k: int = 4) -> list[dict]:
    """Return the k most relevant chunks for query.

    Each result: {text, source, heading, score}
    Score is cosine distance (lower = more relevant).
    """
    collection = _get_collection()
    if collection.count() == 0:
        raise RuntimeError(
            "ChromaDB collection is empty. Run: python -m docs_rag.ingest_docs"
        )
    results = collection.query(query_texts=[query], n_results=min(k, collection.count()))
    chunks = []
    for doc, meta, distance in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({
            "text": doc,
            "source": meta.get("source", ""),
            "heading": meta.get("heading", ""),
            "score": round(distance, 4),
        })
    return chunks


if __name__ == "__main__":
    query = "how to install pytorch on rocm"
    print(f"Query: {query!r}\n{'─' * 60}")
    results = retrieve(query, k=4)
    for i, r in enumerate(results, 1):
        print(f"\n[{i}] {r['source']} › {r['heading']}  (score: {r['score']})")
        print(r["text"][:300] + ("..." if len(r["text"]) > 300 else ""))
