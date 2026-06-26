"""
src/retrieval.py — ProjectRecall Retrieval & Chat Layer
Handles the full RAG pipeline: embedding user queries, searching ChromaDB,
constructing prompts, and generating grounded answers via Llama 3.

ARCHITECTURE NOTE (Chat-Ready Design):
  All retrieval logic is intentionally isolated in this module.
  The functions `ask_question` and `filter_items` have no dependency on
  argparse or the CLI. In a future Phase 2 chat UI, these can be imported
  directly without rewriting any retrieval logic.
"""
import json
import time

from google import genai
from google.genai import errors as genai_errors

from .config import GEMINI_API_KEY, GEMINI_LLM_MODEL, TOP_K_RESULTS
from .ai_processor import get_embedding
from .storage import get_client, get_collection, semantic_search, filter_by_tag, filter_by_date

# ---------------------------------------------------------------------------
# RAG System Prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """\
You are ProjectRecall — a helpful assistant that helps users find information \
from their saved YouTube Shorts.

Rules:
1. Use ONLY the provided context to answer. Never invent or assume information.
2. If the answer is not found in the context, say: \
"I couldn't find that in your saved videos."
3. Be concise and direct.
4. Always end your answer with the source URL on its own line, prefixed with \
"📎 Source:"
"""


# ---------------------------------------------------------------------------
# Core RAG Pipeline
# ---------------------------------------------------------------------------
def ask_question(question: str) -> dict:
    """
    Full RAG pipeline for answering a user's natural language question.

    Steps:
      1. Embed the question using nomic-embed-text
      2. Search ChromaDB for the top-K most relevant chunks
      3. Build a grounded RAG prompt from retrieved context
      4. Send to Llama 3 and collect the response
      5. Return the answer + structured source metadata

    Returns:
      {
        "answer": str,
        "sources": [
          {
            "title": str,
            "url": str,
            "summary": str,
            "thumbnail": str,
            "tags": list[str],
            "web_verification_urls": list[str],
          },
          ...
        ]
      }
    """
    client = get_client()
    collection = get_collection(client)

    # 1. Embed the question
    query_embedding = get_embedding(question)

    # 2. Vector search
    results = semantic_search(collection, query_embedding, top_k=TOP_K_RESULTS)

    # Handle empty database
    if not results["ids"] or not results["ids"][0]:
        return {
            "answer": (
                "No videos saved yet. "
                "Use `python recall.py save <url>` to get started."
            ),
            "sources": [],
        }

    # 3. Build context string + collect source metadata (deduplicated by video)
    context_parts: list[str] = []
    sources: list[dict] = []
    seen_video_ids: set[str] = set()

    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        vid_id = meta.get("video_id", "")

        context_parts.append(
            f"[From: \"{meta.get('title', 'Unknown')}\" | {meta.get('source_url', '')}]\n{doc}"
        )

        if vid_id not in seen_video_ids:
            seen_video_ids.add(vid_id)
            sources.append({
                "title": meta.get("title", "Unknown"),
                "url": meta.get("source_url", ""),
                "summary": meta.get("summary", ""),
                "thumbnail": meta.get("thumbnail_local_path", ""),
                "tags": json.loads(meta.get("tags", "[]")),
                "web_verification_urls": json.loads(
                    meta.get("web_verification_urls", "[]")
                ),
            })

    context = "\n\n---\n\n".join(context_parts)

    # 4. Construct RAG prompt
    full_prompt = (
        f"{_SYSTEM_PROMPT}\n\n"
        f"=== CONTEXT FROM SAVED VIDEOS ===\n{context}\n"
        f"=== END CONTEXT ===\n\n"
        f"User Question: {question}\n\n"
        f"Answer:"
    )

    # 5. Generate answer via Gemini (with retry on 503/429)
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    def _generate():
        return gemini_client.models.generate_content(
            model=GEMINI_LLM_MODEL,
            contents=full_prompt,
        )

    delay = 2
    response = None
    for attempt in range(1, 4):
        try:
            response = _generate()
            break
        except genai_errors.ServerError:
            if attempt < 3:
                time.sleep(delay)
                delay *= 2
            else:
                raise
        except genai_errors.ClientError as exc:
            if "RESOURCE_EXHAUSTED" in str(exc) and attempt < 3:
                time.sleep(delay)
                delay *= 2
            else:
                raise

    answer = response.text if response else "No answer generated."
    return {"answer": answer.strip(), "sources": sources}
