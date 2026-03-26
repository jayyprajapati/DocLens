# DocLens Backend README

## 1. Project Overview

The DocLens backend is the orchestration layer. It exposes stable API endpoints for the UI, validates request shapes, applies default LLM settings, and forwards requests to an upstream RAG service. This keeps the frontend simple while enabling a future path where DocLens becomes a full personal assistant with multi-tool execution, richer memory, and policy-aware automation.
It is responsible for application-specific behavior such as:

- user-scoped requests (`user_id`, `doc_id`)
- free-tier and BYOK usage policy enforcement
- request validation and error normalization
- CORS and deployment-facing API concerns

DocLens backend is intentionally not the retrieval engine. It does not implement:

- embedding generation
- chunking pipelines
- vector database indexing/search

Those responsibilities belong to Cortex (and its underlying vector stack).

## 2. Architecture

```text
Frontend (React)
    |
    v
DocLens Backend (FastAPI)
    |
    v
Cortex (RAG service)
    |
    v
Qdrant (vector database)
```

### Separation of concerns

- Frontend: UX, upload/chat interactions, session UI state
- DocLens: app-level policy, routing, request adaptation, operational controls
- Cortex: retrieval + generation execution
- Qdrant: vector storage and nearest-neighbor retrieval (managed by Cortex)

### Cortex integration contract

DocLens forwards requests to Cortex over HTTP using the `requests` library.
Current upstream mappings:

- DocLens `POST /ingest` -> Cortex `POST /ingest`
- DocLens `POST /query` -> Cortex `POST /query`
- DocLens `POST /delete` -> Cortex `POST /delete`
- DocLens `POST /delete_all` -> Cortex `POST /delete_all`

DocLens adds application-level metadata and policy checks before forwarding:

- `user_id` scoping
- app name tagging (`app_name=doclens`)
- optional BYOK-driven model/key configuration

### Operational workflow

Ingest flow:

1. Frontend uploads a file and `user_id` to DocLens.
2. DocLens enforces policy (quota/page checks) and stores temporary file data.
3. DocLens forwards the ingest request to Cortex.
4. Cortex handles indexing/retrieval-layer internals and returns `doc_id`.
5. DocLens returns normalized response and usage metadata to frontend.

Query flow:

1. Frontend sends query, `user_id`, and optional BYOK fields.
2. DocLens enforces query quota and builds upstream payload.
3. DocLens calls Cortex `/query`.
4. Cortex retrieves relevant chunks and generates an answer.
5. DocLens returns answer, sources, timing metadata, and usage state.

## 3. Tech Stack

- Python 3.10+
- FastAPI
- Uvicorn
- Requests (HTTP integration with Cortex)
- python-dotenv

## 4. Environment Setup

From repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
```

## 5. Environment Variables

Minimum required configuration:

```env
CORTEX_BASE_URL=http://localhost:8000
```

Optional:

```env
RAG_API_BASE_URL=http://localhost:8000
DEFAULT_MODEL=gpt-4o-mini
```

Behavior:

- `CORTEX_BASE_URL` is preferred for upstream calls.
- `RAG_API_BASE_URL` is a fallback.
- If neither is set, default is `http://localhost:8000`.

### Local vs production

- Local: point `CORTEX_BASE_URL` to local Cortex (for example `http://localhost:8000`).
- Production: point `CORTEX_BASE_URL` to a private internal Cortex address (not publicly exposed).

## 6. Running Locally

Current repo entrypoint:

```bash
cd backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

If your deployment layout uses `app/api/main.py` as entrypoint, use:

```bash
uvicorn app.api.main:app --reload
```

## 7. Production Deployment (systemd)

Run DocLens backend as a managed service for restart resilience and log collection.

Example unit file: `/etc/systemd/system/doclens.service`

```ini
[Unit]
Description=DocLens FastAPI Backend
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/doclens/backend
Environment="CORTEX_BASE_URL=http://127.0.0.1:8000"
Environment="DEFAULT_MODEL=gpt-4o-mini"
ExecStart=/opt/doclens/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8002
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable doclens
sudo systemctl start doclens
```

## 8. Nginx Setup (Reverse Proxy)

Example site config:

```nginx
server {
    listen 80;
    server_name api.your-domain.com;

    location / {
        proxy_pass http://localhost:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Domain mapping guidance:

- frontend app: `https://doclens.your-domain.com`
- backend API: `https://api.your-domain.com`
- Cortex: private network only (no public route)

## 9. HTTPS Setup

After Nginx is configured:

```bash
sudo certbot --nginx -d your-domain
```

For split domains, run certbot for each hostname (for example frontend and api subdomains).

## 10. CORS Configuration

CORS is required when frontend and backend are on different origins.

FastAPI middleware pattern:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://doclens.jayprajapati.dev"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Production rule: allow only trusted frontend origins, never wildcard all origins.

## 11. API Endpoints

### POST `/ingest`

Purpose: upload a document for user-scoped ingestion via Cortex.

Form fields:

- `file` (required)
- `user_id` (required)
- `api_key` (optional, enables BYOK path)

Example:

```bash
curl -X POST http://localhost:8001/ingest \
  -F "file=@/absolute/path/to/file.pdf" \
  -F "user_id=user-123" \
  -F "api_key=optional-key"
```

### POST `/query`

Purpose: ask grounded questions against ingested user documents.

JSON body:

```json
{
  "query": "Summarize section 2",
  "user_id": "user-123",
  "api_key": "optional-key",
  "model": "gpt-4o-mini"
}
```

Example:

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query":"Summarize section 2","user_id":"user-123"}'
```

Notes on policy behavior:

- Free tier limits are enforced by backend policy state.
- BYOK requests are treated with separate limits.
- Upstream failures are mapped to `502` responses with diagnostic details.

## 12. Deployment Workflow

Typical release flow:

```bash
cd /opt/doclens
git pull
source .venv/bin/activate
pip install -r backend/requirements.txt
sudo systemctl restart doclens
```

Recommended add-ons:

- run quick health probes after restart
- confirm CORS/preflight for the production frontend origin
- verify Cortex connectivity before opening traffic

## 13. Debugging and Operations

Service status:

```bash
sudo systemctl status doclens
```

Recent logs:

```bash
journalctl -u doclens -n 100 --no-pager
```

Live logs:

```bash
journalctl -u doclens -f
```

Common issues:

- CORS errors in browser:
  - frontend origin missing from `allow_origins`
  - preflight blocked by proxy or wrong API host
- `415 Unsupported Media Type` on ingest:
  - request sent as JSON instead of multipart form-data
  - missing `file` field
- Upstream Cortex failures (`502` from DocLens):
  - Cortex unavailable/unhealthy
  - wrong `CORTEX_BASE_URL`
  - network path blocked between DocLens and Cortex

## 14. Security Notes

- Do not expose Cortex directly to the public internet.
- Keep DocLens as the only public API boundary.
- Store configuration and keys in environment variables.
- Restrict CORS to trusted frontend origins.
- Enforce usage limits to reduce abuse and cost spikes.
- Run behind TLS (Nginx + certbot) in production.

## 15. Design Principles

- DocLens backend is the application layer, not the retrieval engine.
- Do not duplicate embedding/chunking/vector logic from Cortex.
- Keep business rules (quotas, BYOK, user scoping) in DocLens.
- Keep retrieval internals in Cortex.
- Preserve clean boundaries so each service can evolve independently.
