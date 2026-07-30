"""
src/config.py — ProjectRecall Configuration
Central place for all constants, paths, and model settings.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# Root of the project (one level up from this file)
BASE_DIR = Path(__file__).parent.parent

# DATA_DIR — set this env var to a Railway persistent volume path (e.g. /data)
# Falls back to the local recall_db/ folder when running on your machine.
_env_data = os.getenv("DATA_DIR")
DATA_DIR = Path(_env_data) if _env_data else BASE_DIR / "recall_db"

# All persistent data lives under DATA_DIR
DB_DIR = DATA_DIR               # ChromaDB writes directly here
THUMBNAIL_DIR = DATA_DIR / "thumbnails"
AUDIO_DIR = DATA_DIR / "audio"

# Create directories if they don't exist yet
DB_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAIL_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------
CHROMA_COLLECTION_NAME = "youtube_shorts_gemini"

# ---------------------------------------------------------------------------
# Google Gemini API Settings
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_LLM_MODEL = "gemini-2.5-flash"
GEMINI_EMBED_MODEL = "gemini-embedding-2"

# ---------------------------------------------------------------------------
# Chunking — tuned for short-form content (60–90s shorts = ~100–300 words)
# ---------------------------------------------------------------------------
CHUNK_SIZE = 128     # words per chunk
CHUNK_OVERLAP = 20   # overlapping words between adjacent chunks

# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
TOP_K_RESULTS = 3    # number of chunks to retrieve per semantic search

# ---------------------------------------------------------------------------
# Duration guard
# Warn the user if the video exceeds this length (it's probably not a Short)
# ---------------------------------------------------------------------------
MAX_SHORT_DURATION = 180  # seconds (3 minutes)

# ---------------------------------------------------------------------------
# Web verification
# ---------------------------------------------------------------------------
MAX_WEB_RESULTS = 2  # DuckDuckGo results per claim (best-effort, non-blocking)

# ---------------------------------------------------------------------------
# YouTube cookies (Netscape format)
# Set YOUTUBE_COOKIES env var on Railway to bypass datacenter IP blocks.
# Export from your browser using the "cookies.txt" extension while on youtube.com
# ---------------------------------------------------------------------------
YOUTUBE_COOKIES = os.getenv("YOUTUBE_COOKIES", "")

