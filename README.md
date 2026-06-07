# DocLens — Document Q&A (NotebookLM-style, BYOK)

DocLens lets you upload documents, ask natural-language questions, and get
**grounded, cited** answers. It is pure **BYOK** (Bring Your Own Key): every chat
uses *your* OpenAI, Anthropic (Claude), or Ollama Cloud key — there is no shared
fallback key.

DocLens is a thin orchestration + state layer in front of **Brain**, a standalone,
application-agnostic RAG engine. Brain does extraction, chunking, embeddings,
vector search, reranking, and the BYOK LLM call. DocLens owns only its own state
(chat sessions, messages, and the global-vs-per-chat document registry) in MongoDB.
Brain never stores DocLens application data — only vectors keyed by an opaque
`namespace` (your user id) and `doc_id`.

```text
Browser (React + Vite, :3000)
      │
      ▼
DocLens Backend (FastAPI, :8001)        owns Mongo state, enforces BYOK
      │   /v1/extract · /v1/retrieve · /v1/generate · /v1/delete
      ▼
Brain (FastAPI, :8000) ─► OpenAI / Anthropic / Ollama Cloud   (your key)
                       └─► Qdrant  (collection "doclens", namespace = user id)
```

## Two ways to add documents

- **Shared resources** (left panel) — available to **every** chat you start.
- **Per-chat attachments** (paperclip in the composer) — available **only** in that
  chat. Other chats can't see them.

A chat answers from your shared resources **plus** its own attachments. Answers are
grounded in the retrieved text and cited with `[n]` markers; if a question is
ambiguous or the documents don't actually contain the answer, DocLens asks a
clarifying question instead of guessing.

## Supported inputs

- **Documents:** PDF, DOCX, Markdown (`.md`). Complex PDFs with tables are handled —
  Brain extracts tables as Markdown (pdfplumber, with a pypdf fallback).
- **Providers (BYOK):** OpenAI, Anthropic (Claude), Ollama Cloud.

## Run it locally

Prerequisites: **Brain** running (default `http://localhost:8000`) and a reachable
**MongoDB**.

### Backend

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend && uvicorn app.main:app --reload --port 8001
```

`backend/.env`:

```env
BRAIN_BASE_URL=http://localhost:8000
BRAIN_API_KEY=<your Brain API key>
BRAIN_APP_NAME=doclens
MONGO_URI=<your mongodb uri>
MONGO_DB=doclens
CORS_ALLOWED_ORIGINS=http://localhost:3000
ENV=development
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
```

`frontend/.env`:

```env
VITE_API_BASE_URL=http://localhost:8001
```

## API (DocLens backend)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/models?provider=&api_key=` | Suggested models per provider |
| POST | `/chat` | Ask a question (BYOK; returns answer + citations + thread_id) |
| POST | `/ingest` | Upload a per-chat attachment (multipart) |
| GET | `/documents?thread_id=` | A chat's attachments |
| POST | `/resources` · GET `/resources` · DELETE `/resources/{id}` | Global resources |
| GET | `/threads` · GET `/threads/{id}` · PATCH · DELETE | Chat sessions |
| POST | `/delete` · `/delete_all` | Remove a document / reset everything |

Only `/chat` (an LLM call) requires a provider + API key + model. Uploads and
retrieval need no key (embeddings run locally inside Brain).

## Privacy

Your API key lives only in your browser and is sent per request to power your own
chats. It is never persisted by DocLens or Brain, and there is no shared fallback
key. "Reset session" clears your key, chats, and documents.
