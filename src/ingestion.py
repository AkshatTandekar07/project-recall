"""
src/ingestion.py — ProjectRecall Data Ingestion Layer
Handles all URL parsing, metadata fetching, thumbnail downloading,
and transcript extraction.
"""
import re
import requests
from pathlib import Path
from typing import Optional

import yt_dlp
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    NoTranscriptFound,
)

from .config import THUMBNAIL_DIR, MAX_SHORT_DURATION

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


def fetch_transcript(video_id: str) -> Optional[str]:
    """
    Fetch and combine the video transcript into a single text block.
    """
    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
        # Combine all timed snippets into one continuous text
        full_text = " ".join(snippet.text for snippet in transcript)
        return full_text.strip() if full_text.strip() else None
    except Exception:
        return None
