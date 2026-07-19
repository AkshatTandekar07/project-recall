# ProjectRecall — Cloud API Migration Plan (v1.2)

> **Goal:** Migrate the AI capabilities (summarization, RAG, and embeddings) from the local Ollama setup to a Cloud API. This eliminates the need for you to install gigabytes of local models and provides vastly superior speed and reasoning capabilities.

---

## 🛑 User Review Required: Which API?

To proceed, I need to know which API you would like to use. Please reply and tell me **ONE** of the following options so I can implement the correct SDK:

1. **Google Gemini API** (Recommended — generous free tier, incredibly fast)
   - *Get a key here:* [aistudio.google.com](https://aistudio.google.com/)
2. **OpenAI API** (Industry standard, requires billing account)
   - *Get a key here:* [platform.openai.com](https://platform.openai.com/)

*(Do not paste the key directly in the chat if you want to keep it secure; you can create a `.env` file in the project folder and put it there, or just tell me which provider you want and I will set up the code to read it from your environment).*

---

## Proposed Changes

We will gut the local Ollama dependencies and replace them with the chosen Cloud SDK.

### 1. `requirements.txt`
#### [MODIFY] [requirements.txt](file:///c:/Users/tande/Projects/project-recall/requirements.txt)
- Remove `requests` (used for Ollama REST calls).
- Add `python-dotenv` for loading the API key securely.
- Add `google-genai` (if Gemini) OR `openai` (if OpenAI).

### 2. `src/config.py`
#### [MODIFY] [config.py](file:///c:/Users/tande/Projects/project-recall/src/config.py)
- Remove `OLLAMA_BASE_URL` and Ollama model names.
- Add logic to load the API key from a `.env` file via `os.getenv()`.
- Add Cloud model constants (e.g., `gemini-2.5-flash` or `gpt-4o-mini`).

### 3. `src/ai_processor.py`
#### [MODIFY] [ai_processor.py](file:///c:/Users/tande/Projects/project-recall/src/ai_processor.py)
- **Health Check:** Replace `check_ollama_health()` with `verify_api_key()` to ensure the key is present.
- **Embeddings:** Replace `get_embedding()` to call the cloud embedding API (e.g., `text-embedding-004` for Gemini or `text-embedding-3-small` for OpenAI).
- **Summarization:** Replace the `requests.post` logic with the official cloud SDK. Both Gemini and OpenAI natively support strict JSON outputs via Pydantic schemas, which will make our `summarize_transcript` function much cleaner and perfectly reliable without needing manual retry loops.

### 4. `src/retrieval.py`
#### [MODIFY] [retrieval.py](file:///c:/Users/tande/Projects/project-recall/src/retrieval.py)
- Update the RAG answer generation step to use the Cloud API SDK instead of the local REST call.

### 5. `recall.py`
#### [MODIFY] [recall.py](file:///c:/Users/tande/Projects/project-recall/recall.py)
- Update error messages to tell the user to configure their `.env` file rather than telling them to start Ollama.

---

## Verification Plan
1. I will rewrite the code to use the chosen API.
2. I will create a `.env.example` file for you.
3. You will put your actual API key into a `.env` file.
4. We will run `.venv\Scripts\python recall.py save https://www.youtube.com/shorts/dQw4w9WgXcQ` to verify it works instantly via the cloud.
