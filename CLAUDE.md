# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DocLens is a NotebookLM-style, BYOK (Bring Your Own Key) document Q&A app. Users
upload documents, supply their own OpenAI / Anthropic (Claude) / Ollama Cloud key,
and ask questions answered with grounded, cited responses.

DocLens delegates **all** RAG/LLM work to **Brain** — a standalone,
application-agnostic RAG engine (`/Users/jay/Desktop/Projects/Brain`). Brain owns
extraction, chunking, embeddings, vector search, reranking, and the BYOK LLM call.
DocLens owns its **own application state** (chat sessions, messages, and the
global-vs-per-chat document registry) in MongoDB. Brain never sees any DocLens
state — only vectors keyed by an opaque `namespace` (the user id) and `doc_id`.

> DocLens previously used a different RAG backend that exposed threads/workspaces/
> credentials endpoints. That is fully removed — Brain has none of those, so don't
> reintroduce them. Brain is a stateless primitive provider.

Request flow:
```
Browser (React/Vite :3000)
      │
      ▼
DocLens Backend (FastAPI :8001)  ── owns Mongo state, enforces BYOK
      │   /v1/extract · /v1/retrieve · /v1/generate · /v1/delete  (Bearer BRAIN_API_KEY)
      ▼
Brain (FastAPI :8000) ──► OpenAI / Anthropic / Ollama  (user's BYOK key, no fallback)
                     └──► Qdrant (collection "doclens", namespace = user id)
```

## Two upload flows (the core product behavior)

1. **Global resources** — the left-panel "Resources" uploader (`POST /resources`).
   Ingested with `scope="global"`. Queryable in **every** chat for that user.
2. **Per-chat attachments** — the in-composer paperclip (`POST /ingest`).
   Ingested with `scope="thread"` tied to a `thread_id`. Queryable **only** in that
   chat. Uploading in a brand-new chat makes the server create the thread and return
   its `thread_id`, which the frontend adopts.

At query time, retrieval is scoped to `namespace=user_id` AND
`doc_ids = (this user's global docs) ∪ (this chat's docs)`, so a chat sees global
resources + its own attachments, and never another chat's private docs.

## Commands

### Backend
```bash
source .venv/bin/activate
pip install -r backend/requirements.txt          # first-time
cd backend && uvicorn app.main:app --reload --port 8001
```
Brain must be running (default `http://localhost:8000`) and MongoDB reachable.

### Frontend
```bash
cd frontend
npm install
npm run dev      # :3000
npm run build
```

No automated test suite yet.

## Backend architecture (`backend/app/`)

- `main.py` — FastAPI app, CORS, Mongo index creation on startup (lifespan).
- `config.py` — env settings: `BRAIN_BASE_URL`, `BRAIN_API_KEY`, `BRAIN_APP_NAME`
  (default `doclens`), `MONGO_URI`, `MONGO_DB`, `CORS_ALLOWED_ORIGINS`, `ENV`.
- `auth.py` — `user_id_from_request`: decodes the frontend bearer token's `sub`
  claim (unsigned dev JWT) → the user id used as Brain's `namespace`.
- `brain_client.py` — sync httpx client for Brain (`extract_and_ingest`, `retrieve`,
  `generate`, `delete`, `ping`). All calls carry `app_name` + Bearer key; BYOK `llm`
  override is forwarded on every generation. Raises `BrainError(status, detail)`.
- `db.py` — pymongo client + `doclens_threads` / `doclens_messages` /
  `doclens_documents` collections (+ indexes). DocLens state only.
- `prompts.py` — the domain prompts: grounded-but-expansive answer system prompt
  with **clarify-before-assuming** rules, the follow-up contextualizer, and the
  numbered SOURCES / history prompt builders.
- `schemas.py` — request models; `VALID_PROVIDERS = {openai, anthropic, ollama_cloud, ollama_local}`.
- `services/threads.py` — chat-session + message CRUD.
- `services/documents.py` — registry mapping `doc_id → {user, filename, scope, thread}`;
  ingest/list/delete; `global_doc_ids` / `thread_doc_ids` / `filename_map`.
- `services/chat.py` — `run_chat`: resolve/create thread → load recent history →
  scope docs → (LLM) contextualize follow-up → Brain retrieve → grounded+cited
  Brain generate (BYOK) → persist turns → return `{answer, citations, thread_id, meta, grounded}`.
- `api/routes.py` — endpoints (below).

### Endpoints
`GET /health` · `GET /models?provider=&api_key=` · `POST /chat` ·
`POST /ingest` (per-chat upload) · `GET /documents?thread_id=` ·
`POST /delete` · `POST /delete_all` ·
`POST /resources` · `GET /resources` · `DELETE /resources/{doc_id}` (global) ·
`GET /threads` · `GET /threads/{id}` · `PATCH /threads/{id}` · `DELETE /threads/{id}`.

BYOK rule: only LLM calls (`/chat`) require provider+api_key+model; there is **no**
fallback to Brain's own keys. Uploads/retrieval need no key (embeddings are local
to Brain). Brain 4xx (e.g. bad key) → 400 to the browser; 5xx/unreachable → 502.

## Frontend (`frontend/src/`)

- `App.jsx` — owns shared state; `documents` = active thread's attachments,
  `resources` = global resources. Per-chat docs load on thread hydrate/select.
- `components/Header.jsx`, `components/ThreadSidebar.jsx` — BYOK settings
  (providers: OpenAI, Claude/Anthropic, Ollama Cloud) + global Resources uploader.
- `components/InputBar.jsx` — composer with paperclip (per-chat upload).
- `components/MessageBubble.jsx` — renders answers; inline `[n]` markers map to
  `message.sources[n-1]`; citation shape is `{ index, section, page, text, doc_id, filename, score }`.
- `services/api.js` — all fetch calls; `services/auth.js` mints the bearer token.

**Component note:** import bare (`./components/Header`) resolves to the `.jsx`.
Do not recreate empty `.js` siblings — they shadow the real component under Vite.

## Environment

`backend/.env`: `BRAIN_BASE_URL`, `BRAIN_API_KEY`, `BRAIN_APP_NAME=doclens`,
`MONGO_URI`, `MONGO_DB=doclens`, `CORS_ALLOWED_ORIGINS`, `ENV`.
`frontend/.env`: `VITE_API_BASE_URL=http://localhost:8001`.

## Supported documents & providers
- Files: **PDF, DOCX, Markdown** (Brain also accepts plain text; legacy `.doc` is rejected).
  Brain uses pdfplumber for PDFs (renders tables as Markdown) with a pypdf fallback.
- Providers (BYOK): **OpenAI**, **Anthropic (Claude)**, **Ollama Cloud**.
