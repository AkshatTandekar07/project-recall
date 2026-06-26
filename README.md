# ProjectRecall

> **AI-powered memory for YouTube Shorts.** Save a video, ask questions about it later — all locally, all free.

---

## What it does

1. **Save** a YouTube Short → the app extracts the transcript, summarizes it with a local LLM, verifies claims on the web, generates embeddings, and stores everything locally.
2. **Ask** anything → the app searches your saved videos semantically and generates a grounded answer citing its source.
3. **Filter** by tag or date → browse your saved content without natural language.
4. **List & Delete** → full control over your local knowledge base.

---

## Requirements

| Tool | Install |
|------|---------|
| Python 3.10+ | [python.org](https://www.python.org/downloads/) |
| Ollama | [ollama.com](https://ollama.com) |
| Llama 3 model | `ollama pull llama3` |
| nomic-embed-text | `ollama pull nomic-embed-text` |

### Minimum Hardware
| Component | Minimum | Recommended |
|-----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| Disk | 10 GB free | 20 GB free |
| GPU | Not required | NVIDIA 8GB VRAM (much faster) |

> **Note:** Llama 3 8B on CPU-only works but is slow (~30–90s per save). On GPU it drops to ~3–10s.

---

## Setup

```bash
# 1. Clone the repo
git clone https://github.com/yourname/project-recall.git
cd project-recall

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Start Ollama
ollama serve

# 4. Pull the required models (one-time setup)
ollama pull llama3
ollama pull nomic-embed-text
```

---

## Usage

### Save a YouTube Short
```bash
python recall.py save https://www.youtube.com/shorts/dQw4w9WgXcQ
python recall.py save https://youtu.be/dQw4w9WgXcQ
```

### Ask a question about your saved videos
```bash
# ⚠️  Always wrap your question in quotes!
python recall.py ask "What was the Python tip video about?"
python recall.py ask "How do I make sourdough bread?"
```

### List all saved videos
```bash
python recall.py list
```

### Filter by tag
```bash
python recall.py filter --tag cooking
python recall.py filter --tag python
```

### Filter by save date
```bash
python recall.py filter --date 2025-06
python recall.py filter --date 2025
```

### Delete a saved video
```bash
# Use the video ID shown in the `list` output
python recall.py delete dQw4w9WgXcQ
```

---

## Project Structure

```
project-recall/
├── recall.py               # CLI entry point (all commands)
├── requirements.txt        # Python dependencies
├── README.md
├── .gitignore
├── src/
│   ├── config.py           # All constants, paths, model names
│   ├── ingestion.py        # URL parsing, yt-dlp, transcript fetching, thumbnails
│   ├── ai_processor.py     # Ollama health, summarization, chunking, embeddings, web search
│   ├── storage.py          # ChromaDB operations (save, list, filter, delete, search)
│   └── retrieval.py        # RAG pipeline — chat-ready, no CLI dependencies
└── recall_db/              # Created automatically on first save
    └── thumbnails/         # Downloaded thumbnail images
```

---

## Known Limitations (Prototype v1.1)

- Videos with **captions disabled** cannot be processed (no transcript = no data).
- **Non-English** transcripts are fetched but the LLM may summarize them in English.
- Summarization on CPU-only can take **30–90 seconds** per video.
- Web verification is **best-effort** — it will silently skip if DuckDuckGo is unavailable.
- No GUI — this is a CLI prototype validating the core AI loop.

---

## Roadmap

- [ ] Phase 2: Web UI (React/Next.js) with chat interface
- [ ] Phase 3: Instagram Reels + Reddit support
- [ ] Phase 4: Mobile share-sheet integration
