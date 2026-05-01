# DocLens — Document Q&A Client

DocLens is a document intelligence app that lets you upload files, ask natural language questions, and get grounded answers with source references. It is a pure BYOK (Bring Your Own Key) client built on top of Cortex, a shared RAG platform. Every query uses your own OpenAI API key — no platform-provided model paths, no free tier, no usage limits.

**Version:** 2.0 — BYOK-only, Cortex-backed

```
Browser (React + Vite)
      |
      v
DocLens Backend  (FastAPI, port 8001)
      |  normalizes requests, enforces BYOK, tracks documents
      v
Cortex RAG Engine  (port 8000)
      |  ingestion → embedding → retrieval → reranking → LLM generation
      v
OpenAI API  (user's own key)
```

---

## Tech Stack

### Backend

| Component | Package | Version |
|---|---|---|
| API framework | FastAPI + Uvicorn | 0.115.0+ / 0.30.0+ |
| Data validation | Pydantic v2 | (via FastAPI) |
| File parsing | pypdf | latest |
| HTTP client | requests | 2.31.0+ |
| Python | — | 3.11+ |

### Frontend

| Component | Package | Version |
|---|---|---|
| UI framework | React | 19.2.4 |
| Build tool | Vite | 8.0.1 |
| Routing | React Router | 7.13.2 |
| Markdown rendering | react-markdown | 10.1.0 |
| Icons | lucide-react | 1.0.1 |
| Animation | framer-motion | 12.38.0 |
| Node.js | — | 18+ (20+ recommended) |

---

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm 9+
- **Cortex running at `http://localhost:8000`** with the `doclens` app registered
- An OpenAI API key

---

## One-Time Setup

### Backend

```bash
cd /path/to/DocLens

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt
```

### Frontend

```bash
cd /path/to/DocLens/frontend
npm install
```

---

## Environment Variables

### Backend (`backend/.env`)

```env
# URL of the Cortex RAG engine
CORTEX_BASE_URL=http://localhost:8000
```

That is the only required variable. DocLens does not manage LLM keys server-side — they are passed per request from the user's browser session.

### Frontend (`frontend/.env`)

```env
# URL of the DocLens backend
VITE_API_BASE_URL=http://localhost:8001
```

---

## Running Locally

Open two terminals.

**Terminal 1 — Backend**

```bash
cd /path/to/DocLens/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

**Terminal 2 — Frontend**

```bash
cd /path/to/DocLens/frontend
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## Using DocLens

1. Open `http://localhost:3000`.
2. Click **API Settings** in the top-right header.
3. Enter your OpenAI API key and select a model (`gpt-4o-mini`, `gpt-4o`, or `gpt-4.1-mini`).
4. Click the paperclip icon to upload a document (PDF, DOCX, or Markdown).
5. Once uploaded, type a question and press Enter.
6. Answers are grounded in your document with source references (section + page).

**Reset session:** Opens the API Settings dropdown → Reset session. This clears your document context, chat history, and API key from the browser.

---

## API Reference

The DocLens backend exposes four endpoints. All LLM calls require `api_key` and `model`.

### POST /query

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the main findings?",
    "user_id": "user_abc",
    "api_key": "sk-...",
    "model": "gpt-4o-mini"
  }'
```

**Response:**
```json
{
  "answer": "The main findings include...",
  "sources": [
    { "section": "Executive Summary", "page": 1, "text": "...", "score": 0.91 }
  ],
  "meta": { "retrieval_time": 312.4, "generation_time": 0 }
}
```

### POST /ingest

```bash
curl -X POST http://localhost:8001/ingest \
  -F "file=@/path/to/document.pdf" \
  -F "user_id=user_abc" \
  -F "api_key=sk-..."
```

**Response:**
```json
{
  "status": "success",
  "doc_id": "a1b2c3d4-...",
  "meta": { "retrieval_time": 1840.2, "generation_time": 0 }
}
```

### POST /delete

```bash
curl -X POST http://localhost:8001/delete \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_abc", "doc_id": "a1b2c3d4-..."}'
```

### POST /delete_all

```bash
curl -X POST http://localhost:8001/delete_all \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user_abc"}'
```

---

## Request Requirements

| Endpoint | Required fields |
|---|---|
| `/query` | `query`, `user_id`, `api_key`, `model` |
| `/ingest` | `file` (multipart), `user_id`, `api_key` |
| `/delete` | `user_id`, `doc_id` |
| `/delete_all` | `user_id` |

Missing `api_key` or `model` on `/query` returns HTTP 422. Missing `api_key` on `/ingest` returns HTTP 400 with `byok_required`.

---

## Supported File Types

| Format | Extension |
|---|---|
| PDF | `.pdf` |
| Word document | `.docx`, `.doc` |
| Markdown | `.md`, `.markdown` |

File size and page count are unlimited — Cortex handles chunking and ingestion.

---

## Document Lifecycle

- Documents are indexed into Cortex under the `doclens` collection, scoped by `user_id`.
- DocLens tracks each document in a local file registry (`backend/app/data/document_registry.json`).
- Documents older than 24 hours are automatically deleted from Cortex by the background cleanup task.
- Resetting the session calls `/delete_all` to remove all documents from Cortex immediately.

---

## Debug Mode

**Backend with verbose logs:**

```bash
cd /path/to/DocLens/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8001 --log-level debug
```

**Frontend on a custom host/port:**

```bash
cd /path/to/DocLens/frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

**Other frontend commands:**

```bash
npm run lint      # ESLint
npm run build     # production build → dist/
npm run preview   # serve the production build locally
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `422 Unprocessable Entity` on `/query` | `api_key` or `model` missing | Set both in API Settings before querying |
| `400 byok_required` on `/ingest` | `api_key` not sent | Set API key in API Settings before uploading |
| `502 Bad Gateway` on any endpoint | Cortex not running | Start Cortex on port 8000 |
| `Unknown application: 'doclens'` | `doclens` not in Cortex registry | Cortex ships with `doclens` pre-registered — check `app/registry/registry.json` |
| Frontend cannot reach backend | Backend not on port 8001 | Verify backend is running; check `VITE_API_BASE_URL` in `frontend/.env` |
| Upload succeeds but query returns no results | `user_id` mismatch | `user_id` is stored in browser localStorage — avoid clearing it between ingest and query |
| Answer is "No relevant information found" | Query doesn't match document content | Try a more specific question directly about the uploaded content |

---

## Project Structure

```
DocLens/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes.py          # /ingest, /query, /delete, /delete_all
│   │   ├── services/
│   │   │   ├── ingest_service.py  # forwards to Cortex /ingest
│   │   │   ├── query_service.py   # forwards to Cortex /query with BYOK llm config
│   │   │   ├── delete_service.py  # forwards to Cortex /delete, /delete_all
│   │   │   ├── document_registry.py  # file-based doc tracking for cleanup
│   │   │   └── cleanup_service.py    # background task: delete expired docs
│   │   ├── data/
│   │   │   └── document_registry.json
│   │   ├── config.py              # CORTEX_BASE_URL
│   │   └── main.py                # FastAPI app, startup/shutdown
│   ├── services/
│   │   └── rag_client.py          # HTTP client for Cortex API
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Header.jsx         # API settings (key + model + reset)
│   │   │   ├── ChatWindow.jsx     # message list + empty state
│   │   │   ├── InputBar.jsx       # upload + text input + attachment list
│   │   │   ├── MessageBubble.jsx  # individual message rendering
│   │   │   ├── InfoModal.jsx      # reusable modal
│   │   │   └── AppFooter.jsx
│   │   ├── services/
│   │   │   └── api.js             # fetch wrappers for all backend endpoints
│   │   ├── App.jsx                # root state: userId, apiKey, model, chat, docs
│   │   └── main.jsx
│   ├── vite.config.js             # dev server on port 3000
│   └── package.json
└── README.md
```
