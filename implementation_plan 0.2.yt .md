# ProjectRecall v0.2 — Audio Transcription Fallback

> **Goal:** When YouTube captions are unavailable, automatically download the video audio and transcribe it using Gemini's audio API. This makes **every** video savable, not just ones with captions.

---

## How It Works (Current vs. New)

### Current Flow (fails on many Shorts):
```
YouTube URL → fetch captions → ❌ "No transcript available" → EXIT
```

### New Flow (never fails):
```
YouTube URL → try captions → ❌ captions missing?
                                 ↓
                  download audio via yt-dlp
                                 ↓
                  upload to Gemini File API
                                 ↓
                  Gemini transcribes audio → ✅ continue saving
```

---

## Proposed Changes

### 1. Config
#### [MODIFY] [config.py](file:///c:/Users/tande/Projects/project-recall/src/config.py)
- Add `AUDIO_DIR` path inside `recall_db/audio/` for temporary audio files
- Create the directory at startup

---

### 2. Ingestion — The Core Change
#### [MODIFY] [ingestion.py](file:///c:/Users/tande/Projects/project-recall/src/ingestion.py)

**New function: `download_audio(video_id)`**
- Uses `yt-dlp` to download audio-only (smallest format, mp3/m4a)
- Saves to `recall_db/audio/{video_id}.m4a`
- Returns the file path

**New function: `transcribe_audio(audio_path)`**
- Uploads audio to Gemini via `client.files.upload()`
- Sends to `gemini-2.5-flash` with prompt: "Transcribe this audio verbatim"
- Returns the plain text transcription
- Cleans up the uploaded file from Gemini after use

**Modified function: `fetch_transcript(video_id)` → `fetch_transcript(video_id, use_audio_fallback=True)`**
- First tries YouTube captions (existing logic)
- If that returns `None` and `use_audio_fallback=True`:
  1. Call `download_audio(video_id)`
  2. Call `transcribe_audio(audio_path)`
  3. Return the transcription
- Returns a tuple: `(transcript_text, source)` where source is `"captions"` or `"audio"`

---

### 3. CLI — Show the Fallback Status
#### [MODIFY] [recall.py](file:///c:/Users/tande/Projects/project-recall/recall.py)
- Update Step 7 (transcript fetch) to handle the new return format
- Show different status messages:
  - `OK Transcript fetched (captions, 86 words)`
  - `OK Transcript fetched (audio transcription, 120 words)` ← new
- Remove the `sys.exit(1)` on transcript failure (it now falls back instead of crashing)

---

### 4. Requirements
#### [MODIFY] [requirements.txt](file:///c:/Users/tande/Projects/project-recall/requirements.txt)
- No new dependencies needed! `yt-dlp` and `google-genai` are already installed

---

## Verification Plan

1. Test with a video that **has** captions → should use captions (fast path)
2. Test with a video that **doesn't** have captions → should download audio + transcribe via Gemini
3. Verify audio file is cleaned up after transcription
4. Run `ask` to confirm the transcription is searchable

---

> [!NOTE]
> This uses the same Gemini API key and free tier you already have. Audio transcription with Gemini 2.5 Flash is included in the free quota.
