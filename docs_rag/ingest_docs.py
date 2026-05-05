"""Ingest docs_rag/corpus/*.md into a local ChromaDB collection."""

import re
import sys
from pathlib import Path

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

CORPUS_DIR = Path(__file__).parent / "corpus"
CHROMA_DIR = Path(__file__).parent.parent / ".chroma"
COLLECTION_NAME = "rocmforge_docs"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
MAX_CHUNK_TOKENS = 400  # approximate; we split by character count (~4 chars/token)
MAX_CHUNK_CHARS = MAX_CHUNK_TOKENS * 4


def _chunk_by_h2(text: str, source: str) -> list[dict]:
    """Split markdown text on ## headings; fall back to fixed-size windows."""
    chunks = []
    sections = re.split(r"(?=^## )", text, flags=re.MULTILINE)
    for section in sections:
        if not section.strip():
            continue
        heading_match = re.match(r"^## (.+)", section)
        heading = heading_match.group(1).strip() if heading_match else "intro"
        # If the section is too large, split into fixed-size windows with 50-char overlap
        if len(section) <= MAX_CHUNK_CHARS:
            chunks.append({"text": section.strip(), "source": source, "heading": heading})
        else:
            start = 0
            overlap = 200
            while start < len(section):
                end = start + MAX_CHUNK_CHARS
                chunk_text = section[start:end].strip()
                if chunk_text:
                    chunks.append({"text": chunk_text, "source": source, "heading": heading})
                start += MAX_CHUNK_CHARS - overlap
    return chunks


def ingest(corpus_dir: Path = CORPUS_DIR, chroma_dir: Path = CHROMA_DIR) -> int:
    """Walk corpus_dir, chunk all .md files, upsert into ChromaDB. Returns chunk count."""
    ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
    client = chromadb.PersistentClient(path=str(chroma_dir))
    collection = client.get_or_create_collection(name=COLLECTION_NAME, embedding_function=ef)

    all_chunks: list[dict] = []
    for md_file in sorted(corpus_dir.glob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        chunks = _chunk_by_h2(text, source=md_file.name)
        all_chunks.extend(chunks)
        print(f"  {md_file.name}: {len(chunks)} chunk(s)")

    if not all_chunks:
        print("No chunks found — is the corpus directory populated?")
        return 0

    ids = [f"{c['source']}::{c['heading']}::{i}" for i, c in enumerate(all_chunks)]
    documents = [c["text"] for c in all_chunks]
    metadatas = [{"source": c["source"], "heading": c["heading"]} for c in all_chunks]

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    print(f"\nUpserted {len(all_chunks)} chunks into collection '{COLLECTION_NAME}'.")
    return len(all_chunks)


if __name__ == "__main__":
    print(f"Ingesting corpus from: {CORPUS_DIR}")
    total = ingest()
    if total == 0:
        sys.exit(1)
