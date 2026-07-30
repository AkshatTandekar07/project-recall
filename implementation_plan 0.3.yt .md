# ProjectRecall v0.3 — Telegram Bot on Railway

## Goal
Replace the terminal as the interface. You interact with your saved YouTube Shorts knowledge base entirely through a Telegram chat — saving URLs and asking questions from your phone.

---

## ⚠️ Critical Design Decision — Data Persistence

Railway's default filesystem is **ephemeral** — it wipes on every redeploy. Your ChromaDB database (all saved videos) lives in `recall_db/`. Without a fix, **all saved videos would be lost on every deploy.**

**Solution: Railway Persistent Volume**
- A dedicated disk mounted at `/data` that survives restarts and redeploys
- Cost: ~$0.15/GB/month → for your use case (~50 videos ≈ a few MB) = **essentially free**
- ChromaDB and thumbnails both get stored there

---

## Architecture

```
Your Phone (Telegram)
        ↓  HTTP
  Telegram Servers
        ↓  webhook / polling
   Railway Server
   ┌─────────────────────────┐
   │  bot.py (new)           │
   │  ├─ /start handler      │
   │  ├─ URL handler         │──→ src/ingestion.py (existing)
   │  └─ question handler    │──→ src/retrieval.py  (existing)
   │                         │
   │  src/ (all unchanged)   │
   │  recall_db/ (on volume) │
   └─────────────────────────┘
        ↓
   Gemini API (cloud)
```

**Key insight: All `src/` modules stay 100% unchanged.** `bot.py` is purely a new interface layer.

---

## User Requirements Checklist (you need to do these)

### Before I write any code:
- [ ] **Create a Telegram Bot** — message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow prompts → get a `TELEGRAM_BOT_TOKEN`
- [ ] **Create a Railway account** — sign up at [railway.app](https://railway.app) (free tier available, GitHub login recommended)
- [ ] **Connect GitHub to Railway** — Railway will auto-deploy from your repo

### When deploying:
- [ ] Add `TELEGRAM_BOT_TOKEN` as an environment variable in Railway
- [ ] Add `GEMINI_API_KEY` as an environment variable in Railway
- [ ] Add a **Persistent Volume** in Railway and mount it at `/data`

---

## Proposed Changes

### New Files

#### [NEW] `bot.py` — Telegram Bot (main entry point)
The core new file. Uses `python-telegram-bot` library (async).

**Handles:**
- `/start` → Welcome message with instructions
- `/list` → Show all saved videos
- `/delete <video_id>` → Delete a video
- Any YouTube URL → Trigger save pipeline (with progress updates)
- Any other text → Treat as a question, run RAG, return answer + source

**Long-operation handling:** Since saving takes 30-60s, the bot will:
1. Reply "⏳ Saving... this takes ~30 seconds"
2. Process in the background
3. Send a follow-up message when done

#### [NEW] `Procfile` — Railway process definition
```
web: python bot.py
```

#### [NEW] `railway.json` — Railway config
Tells Railway how to build and run the project.

---

### Modified Files

#### [MODIFY] `requirements.txt`
Add: `python-telegram-bot>=21.0`

#### [MODIFY] `src/config.py`
- Add `DATA_DIR` — reads from env var `RAILWAY_VOLUME_MOUNT_PATH` if set, falls back to `recall_db/` locally
- All paths (`DB_DIR`, `THUMBNAIL_DIR`, `AUDIO_DIR`) derive from `DATA_DIR`
- This means **zero code changes needed** when running locally vs on Railway

---

## Bot Conversation Flow

```
User: /start
Bot:  👋 Hi! I'm ProjectRecall.
      Send me a YouTube Shorts URL to save it,
      or ask me anything about your saved videos.

User: https://youtube.com/shorts/9-fXT4fo-tE
Bot:  ⏳ Saving "this is how Steve jobs rules over apple"...
      (30 seconds later)
Bot:  ✅ Saved!
      📌 Title: this is how Steve jobs rules over apple
      🏷 Tags: Steve Jobs, Apple, Leadership
      💬 Steve Jobs kept design and supply chain teams separate...

User: How did Steve Jobs run Apple?
Bot:  Steve Jobs structured Apple so that only he understood both
      the design and supply chain teams...
      📎 Source: https://youtube.com/shorts/9-fXT4fo-tE

User: /list
Bot:  📚 Your saved videos (2):
      1. How Much Skin Humans Shed Is Crazy 😭
      2. this is how Steve jobs rules over apple 😮
```

---

## Open Questions (need your input)

> [!IMPORTANT]
> **Who can use this bot?**
> - **Personal only** (just you) — I add a whitelist check using your Telegram user ID. Anyone else who finds the bot gets blocked.
> - **Public** — anyone can use it and save to the same shared database.
>
> I recommend **personal only** since it's your personal knowledge base.

> [!NOTE]
> **Local data migration:** You have videos saved locally in `recall_db/`. Once deployed to Railway, the Railway volume starts empty. Do you want to migrate your existing saved videos, or start fresh on Railway?

---

## Verification Plan

1. Test locally first: `python bot.py` → chat with bot on Telegram
2. Push `0.3.yt` to GitHub → Railway auto-deploys
3. Verify `/start` works
4. Save a video via Telegram URL
5. Ask a question and verify answer + source link
6. Redeploy → verify data persists (volume test)
