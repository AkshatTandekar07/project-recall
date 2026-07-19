# ProjectRecall v1.1 — Prototype Walkthrough

The local-first AI CLI prototype for YouTube Shorts is completely built and tested.

## 📁 What Was Built

The project has been structured into clean, modular Python files:

- **`recall.py`**: The polished main CLI interface (uses Rich for UI).
- **`src/config.py`**: All constants, chunking sizes, and settings.
- **`src/ingestion.py`**: Robust URL parsing, metadata (`yt-dlp`), thumbnail downloading, and transcript fetching.
- **`src/ai_processor.py`**: Llama 3 summarization with strict JSON validation, `nomic` embeddings, and web verification via DuckDuckGo.
- **`src/storage.py`**: ChromaDB vector operations, deduplication, and JSON metadata handling.
- **`src/retrieval.py`**: The RAG pipeline isolated for future chat UI reuse.

## 📦 Dependencies

I've installed the dependencies into a local virtual environment (`.venv`) using **`uv`**. This bypassed the Windows compilation errors with `chromadb` by fetching the correct pre-built wheels for Python 3.12 automatically.

## 🚀 How to Use It

All you need is to ensure **Ollama is running** (`ollama serve`) in the background.

Then, open your terminal in the `C:\Users\tande\Projects\project-recall` directory and run:

### 1. Save a Video
```powershell
.venv\Scripts\python recall.py save https://youtube.com/shorts/YOUR_ID
```
*(This will fetch the transcript, summarize it, verify it on DuckDuckGo, save the thumbnail, generate embeddings, and store it in the local vector DB).*

### 2. Ask the AI
```powershell
.venv\Scripts\python recall.py ask "What was the video about Python?"
```

### 3. List and Filter
```powershell
.venv\Scripts\python recall.py list
.venv\Scripts\python recall.py filter --tag python
.venv\Scripts\python recall.py filter --date 2026-06
```

### 4. Delete
```powershell
.venv\Scripts\python recall.py delete YOUR_ID
```

---

> [!TIP]
> The database is saved locally in `recall_db/` (which is safely `.gitignore`d).
