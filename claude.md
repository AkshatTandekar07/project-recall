# ProjectRecall — Full Context Document
# For transferring to a new chat session

---

## 1. What Is ProjectRecall?

A personal AI-powered knowledge base that lets you **save YouTube Shorts** and later **search/ask questions** about what you've watched. Like a second brain for short-form video content.

- You send a YouTube Shorts URL → it fetches the transcript (or downloads + transcribes audio), summarizes it with Gemini, generates vector embeddings, and stores everything locally.
- You ask a natural language question → it does semantic vector search and uses Gemini to synthesize a grounded answer with source links.

**Interfaces:**
- CLI (`recall.py`) — terminal, local machine
- Telegram Bot (`bot.py`) — deployed on Railway, accessible from phone

---

## 2. Repository

- **GitHub:** https://github.com/AkshatTandekar07/project-recall
- **Local path:** `C:\Users\tande\Projects\project-recall`
- **Language:** Python 3.12
- **Virtual env:** `.venv\` (managed by `uv`)

### Branches
| Branch | Status | What it contains |
|--------|--------|-----------------|
| `main` | Only README | Empty skeleton |
| `0.1.yt` | ✅ Complete | Core CLI + Gemini Cloud API |
| `0.2.yt` | ✅ Complete | + Audio transcription fallback |
| `0.3.yt` | ✅ Complete | + Telegram bot + Railway deployment |

**Currently on:** `0.3.yt`

---

## 3. Full Tech Stack & Dependencies

### `requirements.txt`
```
youtube-transcript-api>=0.6.2   # Fetch YouTube captions
yt-dlp>=2024.1.0                # Fetch metadata + download audio
chromadb>=0.5.0                  # Local vector database
google-genai>=0.5.0              # Gemini API (summarize, embed, transcribe)
python-dotenv>=1.0.1             # Load .env files
pydantic>=2.0.0                  # Structured LLM outputs
ddgs>=9.0.0                      # DuckDuckGo web verification
rich>=13.7.0                     # Terminal UI
python-telegram-bot>=21.0        # Telegram bot framework
```

### AI Models Used (all via Gemini free tier)
| Model | Used for |
|-------|---------|
| `gemini-2.5-flash` | Summarization, audio transcription, RAG answer generation |
| `gemini-embedding-2` | Vector embeddings (3072 dimensions) |

### External APIs
| Service | Purpose | Key required? |
|---------|---------|--------------|
| Google Gemini | Summarization, embedding, transcription | Yes — `GEMINI_API_KEY` |
| DuckDuckGo (ddgs) | Web verification of claims | No |
| Telegram | Bot interface | Yes — `TELEGRAM_BOT_TOKEN` |

---

## 4. File Structure

```
project-recall/
├── recall.py              # CLI interface (save, ask, list, filter, delete)
├── bot.py                 # Telegram bot interface
├── Procfile               # Railway: "web: python bot.py"
├── railway.json           # Railway build/deploy config
├── requirements.txt       # Python dependencies
├── .env                   # Local secrets (NOT in git)
├── .env.example           # Template (in git, no real key)
├── .gitignore             # Excludes .env, recall_db/, .venv/
├── settings.json          # (project editor settings)
│
├── src/
│   ├── __init__.py
│   ├── config.py          # All constants, paths, API keys
│   ├── ingestion.py       # URL parsing, metadata, thumbnails, transcripts, audio
│   ├── ai_processor.py    # Summarization, chunking, embeddings, web verify
│   ├── storage.py         # ChromaDB CRUD operations
│   └── retrieval.py       # RAG pipeline (embed query → search → LLM answer)
│
└── recall_db/             # LOCAL data (excluded from git)
    ├── thumbnails/        # Downloaded .jpg thumbnails
    ├── audio/             # Temporary .m4a files (deleted after transcription)
    └── [chromadb files]   # Vector DB (persists between runs)
```

---

## 5. Architecture — Full Data Flow

### Save Pipeline
```
User sends URL (CLI or Telegram)
        ↓
extract_video_id()          — regex parse YouTube URL → 11-char video ID
        ↓
fetch_metadata()            — yt-dlp: title, duration, thumbnail URL, channel
        ↓
download_thumbnail()        — HTTP GET from YouTube CDN → recall_db/thumbnails/
        ↓
fetch_transcript()          — youtube-transcript-api: try captions first
        ↓ [if no captions]
download_audio()            — yt-dlp: download .m4a to recall_db/audio/
transcribe_audio()          — upload to Gemini File API → generate_content → delete
        ↓
summarize_transcript()      — Gemini 2.5 Flash + Pydantic schema → {summary, tags}
        ↓
verify_with_web()           — DuckDuckGo search → list of source URLs (best-effort)
        ↓
chunk_text()                — split transcript into 128-word chunks, 20-word overlap
get_embedding(chunk)        — gemini-embedding-2 → 3072-float vector per chunk
        ↓
save_content()              — ChromaDB: store chunks + embeddings + all metadata
```

### Ask/RAG Pipeline
```
User asks question (CLI or Telegram)
        ↓
get_embedding(question)     — gemini-embedding-2 → query vector
        ↓
semantic_search()           — ChromaDB cosine similarity → top 3 chunks
        ↓
Build RAG prompt            — system prompt + retrieved chunks + user question
        ↓
generate_content()          — Gemini 2.5 Flash → grounded answer text
        ↓
Return {answer, sources}    — answer text + source metadata (title, URL, tags)
```

### Component Interaction Diagram
```
                    ┌─────────────────────────────────────────┐
                    │            recall.py (CLI)              │
                    │   save / ask / list / filter / delete   │
                    └──────────────┬──────────────────────────┘
                                   │ imports
                    ┌──────────────▼──────────────────────────┐
                    │             bot.py (Telegram)           │
                    │  /start /list /delete + URL + question  │
                    └──────────────┬──────────────────────────┘
                                   │ imports from src/
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
  ┌───────▼──────┐    ┌────────────▼──────┐    ┌───────────▼──────┐
  │ ingestion.py │    │  ai_processor.py  │    │   retrieval.py   │
  │              │    │                   │    │                   │
  │ URL parsing  │    │ summarize()       │    │ ask_question()   │
  │ metadata     │    │ get_embedding()   │    │ embed query      │
  │ thumbnail    │    │ chunk_text()      │    │ vector search    │
  │ captions     │    │ verify_with_web() │    │ LLM synthesis    │
  │ audio dl     │    │                   │    │                   │
  │ transcribe   │    └────────┬──────────┘    └────────┬─────────┘
  └──────────────┘             │                        │
                               │                        │
                    ┌──────────▼────────────────────────▼──────┐
                    │              storage.py                   │
                    │  ChromaDB: save / get / search / delete   │
                    └──────────────────────────────────────────┘
                               │
                    ┌──────────▼──────────────────────────────┐
                    │           config.py                     │
                    │  All constants, env vars, paths         │
                    └─────────────────────────────────────────┘
```

---

## 6. Each Source File — Full Detail

### `src/config.py`
```python
# Key constants:
DATA_DIR = Path(os.getenv("DATA_DIR")) or BASE_DIR / "recall_db"
DB_DIR = DATA_DIR               # ChromaDB root
THUMBNAIL_DIR = DATA_DIR / "thumbnails"
AUDIO_DIR = DATA_DIR / "audio"
CHROMA_COLLECTION_NAME = "youtube_shorts_gemini"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_LLM_MODEL = "gemini-2.5-flash"
GEMINI_EMBED_MODEL = "gemini-embedding-2"
CHUNK_SIZE = 128       # words per chunk
CHUNK_OVERLAP = 20     # overlap between chunks
TOP_K_RESULTS = 3      # chunks retrieved per query
MAX_SHORT_DURATION = 180  # seconds (longer = not a Short)
MAX_WEB_RESULTS = 2    # DuckDuckGo results
```

**Railway support:** When `DATA_DIR=/data` env var is set, all data writes to the Railway persistent volume. Locally, defaults to `recall_db/`.

---

### `src/ingestion.py`
Key functions:
- `extract_video_id(url)` — regex, supports shorts/watch/youtu.be/mobile URLs
- `fetch_metadata(video_id)` — yt-dlp, no API key
- `download_thumbnail(video_id, url)` — tries maxresdefault → hqdefault → fallback
- `fetch_transcript(video_id, use_audio_fallback=True)` → `(text, source)` where source = `"captions"` or `"audio"` or `"none"`
- `download_audio(video_id)` — yt-dlp, `noprogress=True`, saves to AUDIO_DIR
- `transcribe_audio(audio_path)` — Gemini File API upload → transcribe → delete file + local audio

**Audio fallback detail:**
1. Uploads `.m4a` to `client.files.upload()`
2. Polls until `file.state == "ACTIVE"` (up to 10 retries × 1-5s)
3. Sends to `gemini-2.5-flash` with verbatim transcription prompt
4. Deletes from Gemini + deletes local file in `finally` block

---

### `src/ai_processor.py`
Key functions:
- `verify_api_key()` — checks if `GEMINI_API_KEY` is set
- `chunk_text(text)` — word-based sliding window (128 words, 20 overlap)
- `summarize_transcript(transcript, title)` — Gemini structured output → `ContentSummary(summary, tags)`
- `get_embedding(text)` — `gemini-embedding-2` → `list[float]` (3072 dims)
- `verify_with_web(summary)` — DuckDuckGo first claim search → `list[str]` URLs
- `_retry_api_call(fn, max_attempts=3)` — exponential backoff for 503/429

**Structured output:** Uses `response_mime_type="application/json"` + `response_schema=ContentSummary` for guaranteed Pydantic parsing.

---

### `src/storage.py`
ChromaDB operations. Collection uses cosine similarity space.

Key functions:
- `get_client()` → `chromadb.PersistentClient(path=DB_DIR)`
- `get_collection(client)` → collection named `youtube_shorts_gemini`
- `check_duplicate(collection, video_id)` → returns existing metadata or None
- `save_content(...)` → stores chunks with embeddings + shared metadata
- `list_all_items(collection)` → fetches `chunk_index=0` only (one per video)
- `delete_video(collection, video_id)` → deletes all chunks for a video
- `filter_by_tag(collection, tag)` → Python-side filter (tags stored as JSON string)
- `filter_by_date(collection, year_month)` → filters by `saved_at` prefix
- `semantic_search(collection, query_embedding, top_k=3)` → ChromaDB cosine search

**ChromaDB metadata schema per chunk:**
```python
{
  "video_id": str,
  "source_url": str,
  "title": str,
  "duration_seconds": int,
  "summary": str,
  "tags": str,                    # JSON-stringified list
  "thumbnail_local_path": str,
  "web_verification_urls": str,   # JSON-stringified list
  "saved_at": str,                # ISO datetime
  "chunk_index": int,
}
```

---

### `src/retrieval.py`
RAG pipeline. Completely decoupled from CLI/bot — both interfaces import it directly.

`ask_question(question) → {"answer": str, "sources": list[dict]}`

System prompt rules: answer only from context, cite source URL at end, say "I couldn't find that" if not found.

Retry logic: exponential backoff (2s → 4s → 8s) on 503/429 from Gemini.

---

### `recall.py`
CLI using `rich` for styled terminal output.

Commands:
```bash
python recall.py save <youtube_url>
python recall.py ask "your question"
python recall.py list
python recall.py filter --tag <tag>
python recall.py filter --date <YYYY-MM>
python recall.py delete <video_id>
```

Step 7 of save (transcript) uses a **two-phase approach**:
1. Try captions inside `console.status()` spinner
2. If none: print "trying audio transcription...", call `download_audio()` outside spinner (avoids yt-dlp progress bar conflict with Rich live display), then `transcribe_audio()` inside a new spinner

---

### `bot.py`
Telegram bot using `python-telegram-bot` v21+ (fully async).

**Commands:**
- `/start` — welcome message with instructions
- `/list` — show all saved videos with titles, tags, video IDs
- `/delete <video_id>` — delete a video

**Message handling:**
- If message contains a YouTube URL → save pipeline
- Otherwise → RAG question pipeline

**Key design:**
- `_run_save_pipeline()` is **synchronous** — called via `asyncio.to_thread()` so the event loop isn't blocked
- Sends immediate "⏳ Processing..." message, then edits it with result when done
- Auth via `ALLOWED_USER_IDS` env var — if empty, bot is public; if set, only listed IDs can use it
- Currently: **SHARED database** (all users see the same videos)

---

## 7. Environment Variables

### Local (`.env` file)
```env
GEMINI_API_KEY=your_key_here
```

### Railway (set in dashboard)
```env
TELEGRAM_BOT_TOKEN=your_bot_token
GEMINI_API_KEY=your_gemini_key
ALLOWED_USER_IDS=123456789          # comma-separated Telegram user IDs; empty = public
DATA_DIR=/data                      # Railway persistent volume mount path
```

---

## 8. Deployment — Railway

### Files for Railway
- `Procfile` → `web: python bot.py`
- `railway.json` → Nixpacks builder, restart on failure

### Setup steps (not yet done by user)
1. Create Telegram bot via @BotFather → get `TELEGRAM_BOT_TOKEN`
2. Sign up at railway.app → New Project → Deploy from GitHub → branch `0.3.yt`
3. Add environment variables (see above)
4. Add Persistent Volume → mount at `/data`
5. Deploy

### Data persistence
- Railway's default filesystem is ephemeral (wiped on redeploy)
- Solution: Railway Persistent Volume at `/data`, `DATA_DIR=/data` env var
- ChromaDB + thumbnails both write there → survive redeploys

---

## 9. Versioning Roadmap

| Version | Feature | Status |
|---------|---------|--------|
| `0.1.yt` | Core CLI with Gemini Cloud API | ✅ Done |
| `0.2.yt` | Audio transcription fallback | ✅ Done |
| `0.3.yt` | Telegram bot + Railway deployment | ✅ Built, not yet deployed |
| `0.4.yt` | TBD — see open decisions below | Planned |

---

## 10. Open Decisions / Next Steps

### Immediate (before testing bot):
1. **Deploy to Railway** — user needs to complete the Railway setup checklist
2. **Get Telegram Bot Token** — from @BotFather
3. **Get Telegram User ID** — from @userinfobot

### Architecture decision pending:
- **Public bot with shared DB** (current) — anyone saves to same collection, can see each other's data
- **Public bot with per-user isolation** — namespace ChromaDB collection by `user_{telegram_id}`, pass `user_id` through entire pipeline — requires refactor of `storage.py`, `retrieval.py`, `bot.py`

### Future features discussed:
- Instagram Reels support (URL parser update + skip captions step)
- Web UI (Next.js) — visual cards, search bar, thumbnails
- Browser extension — save directly from YouTube/Instagram
- Multi-language support
- Export/backup of knowledge base

---

## 11. Known Issues & Fixes Applied

| Issue | Fix |
|-------|-----|
| `text-embedding-004` not found | Switched to `gemini-embedding-2` |
| `duckduckgo-search` deprecated | Migrated to `ddgs>=9.0.0` |
| 503 UNAVAILABLE from Gemini | Exponential backoff retry (2s, 4s, 8s) |
| yt-dlp progress bars crash Rich spinner | Added `noprogress: True` to ydl_opts |
| UTF-8 emoji rendering on Windows | `sys.stdout.reconfigure(encoding="utf-8")` |
| `youtube-transcript-api` v1.x breaking change | Switched to instance-based API: `YouTubeTranscriptApi().fetch()` |
| Real API key was in `.env.example` | Fixed — replaced with placeholder, committed security patch |

---

## 12. Token Cost Estimates (Gemini Free Tier)

| Scenario | Tokens per save+ask | Free tier limit |
|----------|---------------------|-----------------|
| Video with captions | ~1,300 | 1M tokens/min |
| Video without captions (audio) | ~2,400 | 1M tokens/min |

**Cost: effectively $0** — 100 videos/day ≈ 240K tokens, well under free tier.

---

## 13. Local Development Commands

```powershell
# Activate venv
.venv\Scripts\Activate.ps1

# Save a video
python recall.py save https://www.youtube.com/shorts/9-fXT4fo-tE

# Ask a question
python recall.py ask "How did Steve Jobs run Apple?"

# List all saved
python recall.py list

# Run the Telegram bot locally
python bot.py    # requires .env with TELEGRAM_BOT_TOKEN + GEMINI_API_KEY

# Install dependencies
python -m pip install -r requirements.txt
```
