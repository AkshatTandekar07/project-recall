"""
src/ingestion.py — ProjectRecall Data Ingestion Layer
Handles all URL parsing, metadata fetching, thumbnail downloading,
transcript extraction, and audio transcription fallback.
"""
import re
import time
import requests
from pathlib import Path
from typing import Optional, Tuple

import yt_dlp
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)
from google import genai
from google.genai import errors as genai_errors

from .config import THUMBNAIL_DIR, AUDIO_DIR, MAX_SHORT_DURATION, GEMINI_API_KEY, GEMINI_LLM_MODEL

# ---------------------------------------------------------------------------
# URL Patterns (ordered by specificity)
# Handles all known YouTube URL formats, including mobile and shared links
# ---------------------------------------------------------------------------
_YT_PATTERNS = [
    r'(?:www\.|m\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})',  # shorts URL
    r'(?:www\.|m\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',  # watch URL
    r'youtu\.be/([a-zA-Z0-9_-]{11})',                            # short share URL
]


def extract_video_id(url: str) -> Optional[str]:
    """
    Extract the 11-character YouTube video ID from any supported URL format.

    Supported formats:
      - youtube.com/shorts/{id}
      - m.youtube.com/shorts/{id}
      - youtube.com/shorts/{id}?feature=share  (query params stripped)
      - youtube.com/watch?v={id}
      - youtu.be/{id}

    Returns the video ID string, or None if no match is found.
    """
    # Strip query params from the path portion but keep ?v= for watch URLs
    for pattern in _YT_PATTERNS:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def fetch_metadata(video_id: str) -> dict:
    """
    Fetch video metadata using yt-dlp (no API key required).

    Returns a dict with:
      - title (str)
      - duration (int, seconds)
      - thumbnail_url (str)
      - webpage_url (str)
      - channel (str)

    Falls back to sensible defaults if yt-dlp fails.
    """
    url = f"https://www.youtube.com/shorts/{video_id}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        # Don't attempt to extract subtitles here — that's done separately
        "writesubtitles": False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info.get("title", "Unknown Title"),
                "duration": int(info.get("duration") or 0),
                "thumbnail_url": info.get(
                    "thumbnail",
                    f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
                ),
                "webpage_url": info.get("webpage_url", url),
                "channel": info.get("uploader", "Unknown Channel"),
            }
    except Exception:
        # yt-dlp failure is non-fatal — we proceed with defaults
        return {
            "title": "Unknown Title",
            "duration": 0,
            "thumbnail_url": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
            "webpage_url": url,
            "channel": "Unknown Channel",
        }


def download_thumbnail(video_id: str, thumbnail_url: str) -> Optional[str]:
    """
    Download the video thumbnail and save it locally.

    Tries maxresdefault → hqdefault → the yt-dlp URL as fallback.
    Rejects suspiciously small responses (< 1 KB) which YouTube returns
    for unavailable thumbnails.

    Returns the local file path string, or None if all attempts fail.
    """
    candidate_urls = [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
        thumbnail_url,
    ]

    local_path = THUMBNAIL_DIR / f"{video_id}.jpg"

    for url in candidate_urls:
        try:
            resp = requests.get(url, timeout=10)
            # YouTube returns a tiny placeholder for missing maxresdefault
            if resp.status_code == 200 and len(resp.content) > 1_000:
                local_path.write_bytes(resp.content)
                return str(local_path)
        except Exception:
            continue

    return None  # Thumbnail is optional; never blocks the save flow


# ---------------------------------------------------------------------------
# Audio download (fallback for missing captions)
# ---------------------------------------------------------------------------
def download_audio(video_id: str) -> Optional[str]:
    """
    Download audio-only from a YouTube video using yt-dlp.

    Saves to recall_db/audio/{video_id}.m4a
    Returns the file path string, or None if download fails.
    """
    output_path = AUDIO_DIR / f"{video_id}.%(ext)s"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "outtmpl": str(output_path),
        "postprocessors": [],  # No conversion needed
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/shorts/{video_id}", download=True
            )
            ext = info.get("ext", "m4a")
            final_path = AUDIO_DIR / f"{video_id}.{ext}"
            if final_path.exists():
                return str(final_path)
    except Exception:
        pass

    # Check if any file was created with the video_id prefix
    for f in AUDIO_DIR.iterdir():
        if f.stem == video_id:
            return str(f)

    return None


# ---------------------------------------------------------------------------
# Audio transcription via Gemini
# ---------------------------------------------------------------------------
def transcribe_audio(audio_path: str) -> Optional[str]:
    """
    Transcribe an audio file using Gemini's audio understanding.

    Steps:
      1. Upload the audio file via the Gemini File API
      2. Send it to Gemini with a transcription prompt
      3. Clean up the uploaded file
      4. Return the plain text transcription

    Returns the transcription text, or None on failure.
    """
    client = genai.Client(api_key=GEMINI_API_KEY)

    uploaded_file = None
    try:
        # Upload audio to Gemini File API
        uploaded_file = client.files.upload(file=audio_path)

        # Wait for file to be processed (it may take a moment)
        delay = 1
        for _ in range(10):
            file_status = client.files.get(name=uploaded_file.name)
            if file_status.state and file_status.state.name == "ACTIVE":
                break
            time.sleep(delay)
            delay = min(delay * 1.5, 5)

        # Transcribe with retry on transient errors
        prompt = (
            "Transcribe this audio verbatim. Output ONLY the spoken words "
            "as plain text, no timestamps, no speaker labels, no formatting."
        )

        response = None
        retry_delay = 2
        for attempt in range(1, 4):
            try:
                response = client.models.generate_content(
                    model=GEMINI_LLM_MODEL,
                    contents=[prompt, uploaded_file],
                )
                break
            except genai_errors.ServerError:
                if attempt < 3:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise
            except genai_errors.ClientError as exc:
                if "RESOURCE_EXHAUSTED" in str(exc) and attempt < 3:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise

        if response and response.text:
            return response.text.strip()
        return None

    except Exception:
        return None

    finally:
        # Clean up: delete uploaded file from Gemini
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass  # Non-fatal

        # Clean up: delete local audio file
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Transcript fetching (with audio fallback)
# ---------------------------------------------------------------------------
def fetch_transcript(video_id: str, use_audio_fallback: bool = True) -> Tuple[Optional[str], str]:
    """
    Fetch the video transcript, with automatic audio transcription fallback.

    Tries YouTube captions first (fast, free). If unavailable and
    use_audio_fallback is True, downloads audio and transcribes via Gemini.

    Returns:
      (transcript_text, source) where source is "captions" or "audio"
      If both fail, returns (None, "none")
    """
    # Attempt 1: YouTube captions (fast path)
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
        full_text = " ".join(snippet.text for snippet in transcript)
        text = full_text.strip()
        if text:
            return (text, "captions")
    except Exception:
        pass

    # Attempt 2: Audio transcription fallback
    if use_audio_fallback:
        audio_path = download_audio(video_id)
        if audio_path:
            transcription = transcribe_audio(audio_path)
            if transcription:
                return (transcription, "audio")

    return (None, "none")

