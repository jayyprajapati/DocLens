# DocLens Backend: FastAPI Gateway For RAG Workflows

The backend is the orchestration layer for DocLens. It exposes stable API endpoints for the UI, validates request shapes, applies default LLM settings, and forwards requests to an upstream RAG service. This keeps the frontend simple while enabling a future path where DocLens becomes a full personal assistant with multi-tool execution, richer memory, and policy-aware automation.

## Responsibilities

- Accept chat, ingest, and generation requests from frontend.
- Normalize and forward requests to upstream RAG endpoints.
- Apply defaults such as model selection.
- Return structured responses and source metadata.

## Tech Stack

- FastAPI
- Uvicorn
- Requests
- python-dotenv

## Prerequisites

- Python `3.10+`
- A running upstream RAG service (default `http://localhost:8000`)

## Install

From repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## Configuration

Set env vars in `.env` (repo root or backend directory):

```env
CORTEX_BASE_URL=http://localhost:8000
RAG_API_BASE_URL=http://localhost:8000
DEFAULT_MODEL=gpt-4o-mini
```

Resolution rules:

- `CORTEX_BASE_URL` is preferred.
- If not set, `RAG_API_BASE_URL` is used.
- If neither is set, backend defaults to `http://localhost:8000`.

## Run Backend

```bash
cd /Users/jay/Desktop/Projects/DocLens/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

API base URL: `http://localhost:8001`

## API Endpoints

### `POST /query`

Request body:

```json
{
  "query": "What does this document say about retention?",
  "user_id": "user-123",
  "api_key": "optional",
  "model": "optional"
}
```

Returns answer payload from upstream, including `sources` when available.

### `POST /ingest`

Multipart form fields:

- `file`: uploaded document
- `user_id`: session/user id

Returns ingest result from upstream.

### `POST /generate`

Request body:

```json
{
  "prompt": "Write a concise summary"
}
```

Uses backend `DEFAULT_MODEL` when forwarding.

### `POST /delete`

Request body:

```json
{
  "user_id": "user-123",
  "doc_id": "doc-abc"
}
```

Deletes a single document by forwarding to upstream `/delete`.

### `POST /delete_all`

Request body:

```json
{
  "user_id": "user-123"
}
```

Deletes all user documents by forwarding to upstream `/delete_all`.

## Automatic Document Expiry

- Uploaded documents are tracked in a local registry (`backend/app/data/document_registry.json`).
- Backend runs an hourly cleanup task.
- Documents older than 24 hours are deleted automatically via upstream `/delete`.

## Debugging

### Start with verbose logs

```bash
cd /Users/jay/Desktop/Projects/DocLens/backend
source ../.venv/bin/activate
python -m uvicorn app.main:app --reload --port 8001 --log-level debug
```

### Curl smoke tests

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query":"test","user_id":"debug-user"}'

curl -X POST http://localhost:8001/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Say hello"}'

curl -X POST http://localhost:8001/ingest \
  -F "file=@/absolute/path/to/file.pdf" \
  -F "user_id=debug-user"
```

## Common Issues

- `502` errors from backend:
  - Upstream RAG service is unreachable or failing.
  - Check `CORTEX_BASE_URL` / `RAG_API_BASE_URL`.
- CORS/browser call issues:
  - Frontend must run from `http://localhost:3000` unless CORS config is expanded.
- Timeouts on large docs:
  - Ingest path uses a longer timeout, but upstream may still need tuning.

## Future Backend Expansion

Planned assistant-focused backend growth:

1. Tool registry and plugin contracts for multi-tool actions.
2. Session planning engine for multi-step task execution.
3. Memory APIs for persistent user/workspace context.
4. Structured observability: traces, cost tracking, latency budgets.
5. Stronger authorization and per-tool permission scopes.
