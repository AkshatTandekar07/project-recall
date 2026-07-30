"""
bot.py — ProjectRecall Telegram Bot
Connects the existing save/retrieval pipeline to Telegram.

Usage:
  python bot.py

Required env vars:
  TELEGRAM_BOT_TOKEN  — from @BotFather
  GEMINI_API_KEY      — from aistudio.google.com
  ALLOWED_USER_IDS    — comma-separated Telegram user IDs (leave empty for public)
  DATA_DIR            — (Railway only) persistent volume mount path, e.g. /data
"""

import asyncio
import json
import logging
import os
import sys

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

from src.ingestion import (
    extract_video_id,
    fetch_metadata,
    download_thumbnail,
    fetch_transcript,
    download_audio,
    transcribe_audio,
)
from src.ai_processor import (
    verify_api_key,
    summarize_transcript,
    chunk_text,
    get_embedding,
    verify_with_web,
)
from src.storage import (
    get_client,
    get_collection,
    check_duplicate,
    save_content,
    list_all_items,
    delete_video,
)
from src.retrieval import ask_question
from src.config import GEMINI_API_KEY, MAX_SHORT_DURATION

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ProjectRecall.bot")

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

_raw_ids = os.getenv("ALLOWED_USER_IDS", "")
ALLOWED_USER_IDS: set[int] = {
    int(uid.strip()) for uid in _raw_ids.split(",") if uid.strip().isdigit()
}


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------
def _is_authorized(update: Update) -> bool:
    """Return True if the user is allowed to use the bot."""
    if not ALLOWED_USER_IDS:
        return True  # No whitelist configured → open access (useful locally)
    return update.effective_user.id in ALLOWED_USER_IDS


async def _deny(update: Update) -> None:
    await update.message.reply_text(
        "⛔ Sorry, this is a private bot. You are not authorized to use it."
    )


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _deny(update)

    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 Hi {name}! I'm *ProjectRecall* — your personal YouTube Shorts brain.\n\n"
        "Here's what I can do:\n\n"
        "📥 *Save a video* — just send me any YouTube Shorts URL\n"
        "🔍 *Ask a question* — type anything and I'll search your saved videos\n"
        "📚 /list — see all saved videos\n"
        "🗑 /delete `<video_id>` — remove a saved video\n\n"
        "_Send me a URL to get started!_",
        parse_mode="Markdown",
    )


# ---------------------------------------------------------------------------
# /list
# ---------------------------------------------------------------------------
async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _deny(update)

    client = get_client()
    collection = get_collection(client)
    items = list_all_items(collection)

    if not items:
        await update.message.reply_text(
            "📭 No videos saved yet.\nSend me a YouTube Shorts URL to save one!"
        )
        return

    lines = [f"📚 *Your saved videos ({len(items)}):*\n"]
    for i, meta in enumerate(items, 1):
        title = meta.get("title", "Unknown")
        vid_id = meta.get("video_id", "")
        tags = json.loads(meta.get("tags", "[]"))
        tag_str = ", ".join(tags[:3]) if tags else "no tags"
        lines.append(f"{i}\\. [{title}](https://youtube.com/shorts/{vid_id})\n   🏷 _{tag_str}_\n   ID: `{vid_id}`")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )


# ---------------------------------------------------------------------------
# /delete <video_id>
# ---------------------------------------------------------------------------
async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _deny(update)

    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage: /delete `<video_id>`\n"
            "Example: `/delete 9-fXT4fo-tE`\n\n"
            "Use /list to find video IDs.",
            parse_mode="Markdown",
        )
        return

    video_id = args[0].strip()
    client = get_client()
    collection = get_collection(client)

    count = delete_video(collection, video_id)
    if count == 0:
        await update.message.reply_text(f"❌ Video ID `{video_id}` not found.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"✅ Deleted `{video_id}` ({count} chunk(s) removed).", parse_mode="Markdown")


# ---------------------------------------------------------------------------
# Save pipeline (runs in a thread to avoid blocking the event loop)
# ---------------------------------------------------------------------------
def _run_save_pipeline(video_id: str, url: str) -> dict:
    """
    Synchronous save pipeline — mirrors recall.py's save flow.
    Returns a result dict with keys: success, title, tags, summary, error.
    """
    try:
        # 1. API key check
        if not verify_api_key():
            return {"success": False, "error": "Gemini API key is missing or invalid."}

        # 2. Duplicate check
        client = get_client()
        collection = get_collection(client)
        existing = check_duplicate(collection, video_id)
        if existing:
            return {
                "success": False,
                "error": f"Already saved: *{existing.get('title', video_id)}*",
            }

        # 3. Fetch metadata
        meta = fetch_metadata(video_id)
        title = meta["title"]
        duration = meta["duration"]

        # 4. Duration guard (skip very long videos silently on bot)
        if duration > MAX_SHORT_DURATION:
            return {
                "success": False,
                "error": (
                    f"Video is {duration}s long (max {MAX_SHORT_DURATION}s). "
                    "This doesn't look like a Short. Not saved."
                ),
            }

        # 5. Thumbnail
        thumb_path = download_thumbnail(video_id, meta["thumbnail_url"]) or ""

        # 6. Transcript (captions → audio fallback)
        transcript, transcript_source = fetch_transcript(video_id, use_audio_fallback=False)
        if not transcript:
            # Audio fallback
            audio_path = download_audio(video_id)
            if audio_path:
                transcript = transcribe_audio(audio_path)
                transcript_source = "audio" if transcript else "none"

        if not transcript:
            return {
                "success": False,
                "error": (
                    "⚠️ No transcript available.\n\n"
                    "This video has captions disabled and audio download failed "
                    "(YouTube blocks audio downloads from cloud servers).\n\n"
                    "Try a video that has captions enabled, or one where the creator "
                    "enabled auto-generated captions."
                ),
            }

        # 7. Summarize
        content_summary = summarize_transcript(transcript, title)

        # 8. Web verification (best-effort)
        web_urls = verify_with_web(content_summary.summary)

        # 9. Chunk + embed
        chunks = chunk_text(transcript)
        embeddings = [get_embedding(chunk) for chunk in chunks]

        # 10. Save
        saved_at = save_content(
            collection=collection,
            video_id=video_id,
            source_url=meta["webpage_url"],
            title=title,
            duration_seconds=duration,
            summary=content_summary.summary,
            tags=content_summary.tags,
            thumbnail_local_path=thumb_path,
            web_verification_urls=web_urls,
            chunks=chunks,
            embeddings=embeddings,
        )

        return {
            "success": True,
            "title": title,
            "tags": content_summary.tags,
            "summary": content_summary.summary,
            "source_url": meta["webpage_url"],
            "transcript_source": transcript_source,
        }

    except Exception as exc:
        logger.exception("Save pipeline error")
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Message handler — URL or question
# ---------------------------------------------------------------------------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update):
        return await _deny(update)

    text = update.message.text.strip()
    video_id = extract_video_id(text)

    if video_id:
        await _handle_save(update, context, video_id, text)
    else:
        await _handle_question(update, context, text)


async def _handle_save(
    update: Update, context: ContextTypes.DEFAULT_TYPE, video_id: str, url: str
) -> None:
    """Handle a YouTube URL — run the save pipeline with progress messages."""
    status_msg = await update.message.reply_text(
        f"⏳ Got it! Processing `{video_id}`...\n"
        "_Fetching metadata & transcript — this takes ~30–60 seconds_",
        parse_mode="Markdown",
    )

    # Run the blocking pipeline in a thread
    result = await asyncio.to_thread(_run_save_pipeline, video_id, url)

    if result["success"]:
        tags_str = ", ".join(result.get("tags", []))
        source = result.get("transcript_source", "captions")
        source_label = "🎙 Audio transcription" if source == "audio" else "📝 Captions"

        reply = (
            f"✅ *Saved successfully!*\n\n"
            f"📌 *{result['title']}*\n"
            f"🏷 _{tags_str}_\n"
            f"{source_label}\n\n"
            f"💬 {result['summary']}\n\n"
            f"📎 {result['source_url']}"
        )
    else:
        reply = f"❌ {result['error']}"

    await status_msg.edit_text(reply, parse_mode="Markdown", disable_web_page_preview=True)


async def _handle_question(
    update: Update, context: ContextTypes.DEFAULT_TYPE, question: str
) -> None:
    """Handle a free-text question — run the RAG pipeline."""
    thinking_msg = await update.message.reply_text("🔍 Searching your saved videos...")

    result = await asyncio.to_thread(ask_question, question)

    answer = result.get("answer", "No answer generated.")
    sources = result.get("sources", [])

    # Format sources
    source_lines = []
    for s in sources:
        source_lines.append(f"📎 [{s['title']}]({s['url']})")

    full_reply = answer
    if source_lines:
        full_reply += "\n\n" + "\n".join(source_lines)

    await thinking_msg.edit_text(
        full_reply,
        parse_mode="Markdown",
        disable_web_page_preview=False,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Exiting.")
        sys.exit(1)

    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not set. Exiting.")
        sys.exit(1)

    logger.info("Starting ProjectRecall bot...")
    if ALLOWED_USER_IDS:
        logger.info(f"Access restricted to user IDs: {ALLOWED_USER_IDS}")
    else:
        logger.warning("No ALLOWED_USER_IDS set — bot is open to anyone!")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("list", cmd_list))
    app.add_handler(CommandHandler("delete", cmd_delete))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running — press Ctrl+C to stop")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
