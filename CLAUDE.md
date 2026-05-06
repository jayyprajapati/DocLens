# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DocLens is a BYOK (Bring Your Own Key) document Q&A application. Users upload PDFs, supply their own OpenAI/Ollama API key, and ask questions answered by a downstream RAG service called Cortex.

Request flow:
```
Browser (React) → DocLens Backend (FastAPI :8001) → Cortex RAG Service (:8000) → OpenAI / Ollama
```

The DocLens backend is a **thin orchestration layer** — it validates requests, scopes by `user_id`, and forwards to Cortex. Cortex owns embeddings, vector search, and LLM calls.

## Commands

### Backend
```bash
# From repo root
source .venv/bin/activate
cd backend
uvicorn app.main:app --reload --port 8001

# First-time setup
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### Frontend
```bash
cd frontend
npm install        # first-time setup
npm run dev        # dev server on :3000
npm run build      # production build
npm run lint       # ESLint
npm run preview    # preview production build
```

No test suite exists currently.

## Architecture

### Backend (`backend/`)

- `app/main.py` — FastAPI app, CORS config, startup hook that launches the background cleanup task
- `app/api/routes.py` — All HTTP endpoints; handles validation, error mapping, and calls into services
- `app/services/` — Business logic layer: `ingest_service`, `query_service`, `delete_service`, `document_registry`
- `services/rag_client.py` — Raw HTTP client for Cortex; all calls attach `app_name="doclens"` and `user_id` scoping
- `app/config.py` — `CORTEX_BASE_URL` and `ENV` loaded from `backend/.env`
- `app/data/document_registry.json` — File-based doc metadata store (thread-locked JSON); tracks `doc_id`, `filename`, `uploaded_at`
- `app/services/cleanup_service.py` — Async background task (runs every 60 min) that deletes documents older than 24 hours via Cortex

Error handling convention: `_handle_upstream_error()` maps Cortex 4xx → 400 and 5xx → 502. Use `_error_response()` for consistent JSON error format.

### Frontend (`frontend/src/`)

- `App.jsx` — Root component; owns all shared state and wires it to children via props
- `components/Header.jsx` — API settings modal (provider, key, model), theme toggle, session reset
- `components/ChatWindow.jsx` — Message list + document selection logic
- `components/InputBar.jsx` — File upload + text input; emits ingest/query events upward
- `components/MessageBubble.jsx` — Renders messages, sources, timeline stages
- `services/api.js` — All `fetch()` calls to the backend; returns structured results

**Message types** in the chat array: `'user'`, `'assistant'`, `'timeline'`, `'system'`, `'doc-select'`. Timeline messages animate upload/query stages with `startStageProgress()` / `completeStages()` / `failStages()`.

**Ambiguous query detection**: if the user has >1 uploaded doc and the query matches `\b(this|the)\s+(doc|file|pdf|report)\b`, a `doc-select` message is injected; the chosen doc IDs are sent as `doc_ids` on the real query.

**localStorage keys** (all prefixed `doclens_`): `user_id`, `api_key`, `selected_model`, `provider`, `theme`. Session reset clears all of these and reloads.

### Environment Configuration

**`backend/.env`**
```
CORTEX_BASE_URL=http://localhost:8000
ENV=development   # set to "production" to disable /docs and /redoc
```

**`frontend/.env`**
```
VITE_API_BASE_URL=http://localhost:8001
```

### CORS

Configured in `backend/app/main.py`; allows `http://localhost:3000` and the production domain. Update here when adding new origins.

### Supported Providers & Models

- **OpenAI**: `gpt-4o-mini`, `gpt-4o`, `gpt-4.1-mini`, `gpt-4.1`, `o4-mini`
- **Ollama Cloud**: `gpt-oss:120b` (fallback when Cortex returns no models)

Model lists are fetched from Cortex at runtime via `GET /models` (optionally authenticated with the user's API key).
