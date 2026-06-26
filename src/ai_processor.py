"""
src/ai_processor.py — ProjectRecall AI Processing Layer
Handles: API Key verification, transcript summarization (via Gemini structured outputs),
text chunking, vector embedding generation (via Gemini), and best-effort web verification.
"""
import time
from typing import Optional

from pydantic import BaseModel
from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from .config import (
    GEMINI_API_KEY,
    GEMINI_LLM_MODEL,
    GEMINI_EMBED_MODEL,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    MAX_WEB_RESULTS,
)


# ---------------------------------------------------------------------------
# Pydantic schema — Gemini will natively return data matching this schema
# ---------------------------------------------------------------------------
class ContentSummary(BaseModel):
    """Expected structure of the LLM's summarization response."""
    summary: str
    tags: list[str]


# ---------------------------------------------------------------------------
# API Verification
# ---------------------------------------------------------------------------
def verify_api_key() -> bool:
    """Check if the Gemini API key is loaded in the environment."""
    return bool(GEMINI_API_KEY and GEMINI_API_KEY.strip())


# ---------------------------------------------------------------------------
# Text Chunking
# ---------------------------------------------------------------------------
def chunk_text(text: str) -> list[str]:
    """Split transcript text into overlapping word-based chunks."""
    words = text.split()

    if len(words) <= CHUNK_SIZE:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + CHUNK_SIZE, len(words))
        chunks.append(" ".join(words[start:end]))
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunks


# ---------------------------------------------------------------------------
# Summarization + Tagging (Gemini Structured Outputs)
# ---------------------------------------------------------------------------
_SUMMARIZE_PROMPT = """\
You are a content analyst. Analyze this YouTube Short titled "{title}".

Summarize the content in exactly 3 sentences.
Then list exactly 5 short keyword tags (single words or 2-word phrases).

Transcript:
{transcript}"""


def summarize_transcript(transcript: str, title: str) -> ContentSummary:
    """
    Send the transcript to Gemini and get a strongly-typed Pydantic object back.
    No manual JSON parsing or retry loops needed — the SDK handles it natively.
    """
    prompt = _SUMMARIZE_PROMPT.format(title=title, transcript=transcript)

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    try:
        response = client.models.generate_content(
            model=GEMINI_LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=ContentSummary,
            ),
        )
        # response.parsed contains the Pydantic object
        if response.parsed:
            return response.parsed
        else:
            raise ValueError("Gemini returned empty parsed data.")
            
    except Exception as exc:
        # Hard fallback — store raw beginning of transcript as summary
        # We don't crash the save process just because summarization failed
        return ContentSummary(
            summary=(
                f"Content from YouTube Short: '{title}'. "
                f"Transcript excerpt: {transcript[:250]}..."
            ),
            tags=["youtube", "short", "video", "content", "recall"],
        )


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
def _retry_api_call(fn, *args, max_attempts: int = 3, **kwargs):
    """
    Call fn(*args, **kwargs) with exponential backoff retries.
    Retries on Gemini 503 (UNAVAILABLE) and 429 (RESOURCE_EXHAUSTED).
    """
    delay = 2  # seconds
    for attempt in range(1, max_attempts + 1):
        try:
            return fn(*args, **kwargs)
        except genai_errors.ServerError as exc:
            # 503 UNAVAILABLE — transient server overload
            if attempt < max_attempts:
                time.sleep(delay)
                delay *= 2
            else:
                raise
        except genai_errors.ClientError as exc:
            # 429 RESOURCE_EXHAUSTED — rate limit
            if "RESOURCE_EXHAUSTED" in str(exc) and attempt < max_attempts:
                time.sleep(delay)
                delay *= 2
            else:
                raise


# ---------------------------------------------------------------------------
# Embeddings via Gemini
# ---------------------------------------------------------------------------
def get_embedding(text: str) -> list[float]:
    """
    Generate a vector embedding for a text string using Gemini's embedding model.
    Retries automatically on transient 503/429 errors.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    def _call():
        return client.models.embed_content(
            model=GEMINI_EMBED_MODEL,
            contents=text,
        )

    response = _retry_api_call(_call)
    return response.embeddings[0].values


# ---------------------------------------------------------------------------
# Web Verification (best-effort, non-blocking)
# ---------------------------------------------------------------------------
def verify_with_web(summary: str) -> list[str]:
    """Search DuckDuckGo for the first factual claim in the summary."""
    try:
        from ddgs import DDGS

        first_sentence = summary.split(".")[0].strip()
        if not first_sentence or len(first_sentence) < 10:
            return []

        urls: list[str] = []
        with DDGS() as ddgs:
            for result in ddgs.text(first_sentence, max_results=MAX_WEB_RESULTS):
                href = result.get("href", "")
                if href:
                    urls.append(href)

        return urls[:MAX_WEB_RESULTS]

    except Exception:
        return []  # Always fail silently
