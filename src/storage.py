"""
src/storage.py — ProjectRecall Knowledge Management Layer
All ChromaDB operations: initialization, duplicate detection, save, list,
filter, and delete. Tags and URLs are stored as JSON strings because
ChromaDB metadata values must be scalar (str / int / float).
"""
import json
from datetime import datetime
from typing import Optional

import chromadb

from .config import DB_DIR, CHROMA_COLLECTION_NAME


# ---------------------------------------------------------------------------
# Client + Collection
# ---------------------------------------------------------------------------
def get_client() -> chromadb.PersistentClient:
    """Return a persistent ChromaDB client writing to ./recall_db/."""
    return chromadb.PersistentClient(path=str(DB_DIR))


def get_collection(client: chromadb.PersistentClient) -> chromadb.Collection:
    """Get or create the youtube_shorts collection (cosine similarity space)."""
    return client.get_or_create_collection(
        name=CHROMA_COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Duplicate Detection
# ---------------------------------------------------------------------------
def check_duplicate(collection: chromadb.Collection, video_id: str) -> Optional[dict]:
    """
    Check if a video_id already exists in the database.

    Returns the metadata dict of the first chunk (chunk_index=0) if found,
    or None if this is a new video.
    """
    try:
        results = collection.get(
            where={"video_id": video_id},
            limit=1,
            include=["metadatas"],
        )
        if results["ids"]:
            return (results["metadatas"] or [None])[0]
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
def save_content(
    collection: chromadb.Collection,
    video_id: str,
    source_url: str,
    title: str,
    duration_seconds: int,
    summary: str,
    tags: list[str],
    thumbnail_local_path: str,
    web_verification_urls: list[str],
    chunks: list[str],
    embeddings: list[list[float]],
) -> str:
    """
    Persist all chunks with their embeddings and shared metadata to ChromaDB.

    Each chunk gets:
      - A unique ID: {video_id}_chunk_{i}
      - The chunk text as the document
      - The embedding vector
      - The full metadata dict (shared across all chunks of the same video)

    Returns the ISO-format timestamp string of when the video was saved.
    """
    saved_at = datetime.now().isoformat()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []

    shared_meta = {
        "video_id": video_id,
        "source_url": source_url,
        "title": title,
        "duration_seconds": duration_seconds,
        "summary": summary,
        # Lists must be JSON-stringified for ChromaDB scalar metadata
        "tags": json.dumps(tags),
        "thumbnail_local_path": thumbnail_local_path or "",
        "web_verification_urls": json.dumps(web_verification_urls),
        "saved_at": saved_at,
    }

    for i, chunk in enumerate(chunks):
        ids.append(f"{video_id}_chunk_{i}")
        documents.append(chunk)
        metadatas.append({**shared_meta, "chunk_index": i})

    collection.add(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    return saved_at


# ---------------------------------------------------------------------------
# List all saved videos
# ---------------------------------------------------------------------------
def list_all_items(collection: chromadb.Collection) -> list[dict]:
    """
    Return metadata for all saved videos (one entry per video, not per chunk).

    Fetches only chunk_index=0 to avoid returning a row per chunk.
    """
    try:
        results = collection.get(
            where={"chunk_index": 0},
            include=["metadatas"],
        )
        return results.get("metadatas") or []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------
def delete_video(collection: chromadb.Collection, video_id: str) -> int:
    """
    Delete all chunks for a given video_id.

    Returns the number of chunks deleted (0 if video was not found).
    Raises RuntimeError on unexpected ChromaDB failures.
    """
    try:
        existing = collection.get(where={"video_id": video_id})
        if not existing["ids"]:
            return 0
        count = len(existing["ids"])
        collection.delete(where={"video_id": video_id})
        return count
    except Exception as exc:
        raise RuntimeError(f"Failed to delete video '{video_id}': {exc}") from exc


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------
def filter_by_tag(collection: chromadb.Collection, tag: str) -> list[dict]:
    """
    Return all saved videos whose tags contain the given tag string.

    Filtering is done in Python (not ChromaDB query) because tags are stored
    as a JSON-stringified list and ChromaDB's $contains operator works on
    plain strings, not nested JSON.

    Matching is case-insensitive and partial (e.g. "cook" matches "cooking").
    """
    try:
        results = collection.get(
            where={"chunk_index": 0},
            include=["metadatas"],
        )
        tag_lower = tag.lower()
        return [
            meta
            for meta in (results.get("metadatas") or [])
            if any(tag_lower in t.lower() for t in json.loads(meta.get("tags", "[]")))
        ]
    except Exception:
        return []


def filter_by_date(collection: chromadb.Collection, year_month: str) -> list[dict]:
    """
    Return all saved videos whose saved_at starts with the given YYYY-MM string.

    Example: year_month="2025-06" matches anything saved in June 2025.
    """
    try:
        results = collection.get(
            where={"chunk_index": 0},
            include=["metadatas"],
        )
        return [
            meta
            for meta in (results.get("metadatas") or [])
            if meta.get("saved_at", "").startswith(year_month)
        ]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Semantic Search (used by retrieval.py)
# ---------------------------------------------------------------------------
def semantic_search(
    collection: chromadb.Collection,
    query_embedding: list[float],
    top_k: int = 3,
) -> dict:
    """
    Query ChromaDB using a pre-computed embedding vector.

    Returns the raw ChromaDB query result dict containing:
      - ids, documents, metadatas, distances
    """
    return collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        include=["documents", "metadatas", "distances"],
    )
