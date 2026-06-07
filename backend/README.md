# DocLens Backend

FastAPI orchestration + state layer (port 8001). It validates requests, resolves
the user, owns DocLens application state in MongoDB, and delegates all RAG/LLM work
to **Brain** (the application-agnostic engine). It holds no embeddings and no model
keys: the user's BYOK key is forwarded to Brain per request, with **no fallback**.

## Run

```bash
source ../.venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Requires Brain running and MongoDB reachable. See `.env` for configuration.

## Layout

```text
app/
  main.py            FastAPI app, CORS, Mongo index creation (lifespan)
  config.py          env settings (BRAIN_*, MONGO_*, CORS, ENV)
  auth.py            user id from the bearer token's `sub` claim
  brain_client.py    sync httpx client for Brain (extract/retrieve/generate/delete/ping)
  db.py              pymongo: doclens_threads / doclens_messages / doclens_documents
  prompts.py         grounded + clarify-before-assuming answer prompt; contextualizer
  schemas.py         request models; VALID_PROVIDERS
  services/
    threads.py       chat-session + message CRUD
    documents.py     doc registry (global vs per-thread scope), ingest/list/delete
    chat.py          run_chat: scope -> retrieve -> grounded+cited generate -> persist
  api/routes.py      HTTP endpoints
```

## State model (MongoDB)

- `doclens_threads` — `{_id, user_id, title, created_at, updated_at, message_count}`
- `doclens_messages` — `{_id, thread_id, user_id, role, content, citations[], created_at}`
- `doclens_documents` — `{_id (=Brain doc_id), user_id, filename, scope, thread_id, chunk_count, ...}`
  - `scope = "global"` → queryable in every chat; `scope = "thread"` → only in `thread_id`.

Per-user isolation is enforced in Brain via `namespace = user_id`; document scope is
enforced by passing the right union of `doc_ids` (global ∪ this chat's) to retrieve.

## Brain calls used

- `POST /v1/extract` (multipart, `ingest=true`) — extract + chunk + embed + store.
- `POST /v1/retrieve` — embed query → vector search → rerank (local; no BYOK key).
- `POST /v1/generate` — grounded answer with the BYOK `llm` override (user's key).
- `POST /v1/delete` — remove vectors by `doc_id` and/or `namespace`.

## Endpoints

`GET /health` · `GET /models` · `POST /chat` · `POST /ingest` ·
`GET /documents?thread_id=` · `POST /delete` · `POST /delete_all` ·
`POST /resources` · `GET /resources` · `DELETE /resources/{doc_id}` ·
`GET /threads` · `GET /threads/{id}` · `PATCH /threads/{id}` · `DELETE /threads/{id}`.

Error mapping: Brain 4xx (bad key / bad request) → 400; Brain 5xx / unreachable → 502.
