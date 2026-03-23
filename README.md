# DocLens: Retrieval-Augmented Document Copilot

DocLens is a personal document intelligence workspace that lets you upload files, ask natural language questions, and get grounded answers with source references. Today, it focuses on a clean end-to-end RAG loop (ingest, query, answer). The long-term direction is to expand DocLens into a full personal assistant that can orchestrate multiple tools, maintain long-running context, and execute practical workflows such as research synthesis, document drafting, and task automation across connected services.

## What This Project Contains

- `backend`: FastAPI service that exposes `/ingest`, `/query`, and `/generate`.
- `frontend`: React + Vite client for upload + chat workflows.
- External dependency: a RAG-compatible upstream service (default `http://localhost:8000`) that performs retrieval and generation.

## Architecture At A Glance

1. Frontend sends requests to backend at `http://localhost:8001`.
2. Backend normalizes requests and forwards them to the upstream RAG API.
3. Upstream returns answer + sources.
4. Frontend renders response, source metadata, and keeps session state in local storage.

## Prerequisites

- macOS/Linux shell (commands below use `zsh`/`bash` syntax)
- Python `3.10+`
- Node.js `18+` (Node `20+` recommended)
- npm `9+`

## Environment Variables

Create a `.env` file in project root or in `backend`.

```env
# Backend -> upstream RAG service URL
CORTEX_BASE_URL=http://localhost:8000

# Fallback if CORTEX_BASE_URL is not set
RAG_API_BASE_URL=http://localhost:8000

# Default model used by backend generate/query paths
DEFAULT_MODEL=gpt-4o-mini
```

Notes:

- `CORTEX_BASE_URL` takes precedence over `RAG_API_BASE_URL`.
- Frontend also allows entering `api_key` and model per session in the UI header.

## One-Time Setup

From project root:

```bash
# 1) Python environment
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 2) Frontend dependencies
cd frontend
npm install
cd ..
```

## Run The Full Stack

Use two terminals.

Terminal A (backend):

```bash
cd /Users/jay/Desktop/Projects/DocLens/backend
source ../.venv/bin/activate
uvicorn app.main:app --reload --port 8001
```

Terminal B (frontend):

```bash
cd /Users/jay/Desktop/Projects/DocLens/frontend
npm run dev
```

Open `http://localhost:3000`.

## Debug Commands

### Backend Debug

```bash
cd /Users/jay/Desktop/Projects/DocLens/backend
source ../.venv/bin/activate
python -m uvicorn app.main:app --reload --port 8001 --log-level debug
```

Quick health check style calls:

```bash
curl -X POST http://localhost:8001/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What is this document about?","user_id":"debug-user"}'

curl -X POST http://localhost:8001/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Summarize retrieval augmented generation in 2 lines"}'
```

Upload test:

```bash
curl -X POST http://localhost:8001/ingest \
  -F "file=@/absolute/path/to/your/file.pdf" \
  -F "user_id=debug-user"
```

### Frontend Debug

```bash
cd /Users/jay/Desktop/Projects/DocLens/frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

Other useful frontend commands:

```bash
npm run lint
npm run build
npm run preview
```

## Common Troubleshooting

- Frontend cannot reach backend:
  - Ensure backend is running on `8001`.
  - Check CORS allows `http://localhost:3000`.
- Backend returns 502:
  - Verify upstream RAG service is running at `CORTEX_BASE_URL` / `RAG_API_BASE_URL`.
- Upload/query works in backend but not in UI:
  - Confirm frontend API base URL points to `http://localhost:8001`.

## Future Expansion: Personal Assistant Roadmap

Planned capabilities to evolve DocLens beyond document QA:

1. Multi-tool orchestration: call search, calendar, notes, code, and automation tools in one workflow.
2. Agentic planning: break goals into steps, execute, and recover from failures automatically.
3. Memory layers: short-term conversational memory + long-term user/workspace memory.
4. Action connectors: integrate email, task managers, cloud drives, and internal APIs.
5. Guardrails and governance: permissioned tool access, traceable actions, and audit logs.
6. Collaboration mode: shared workspaces and team-level assistant context.

## Additional Docs

- Backend details: `backend/README.md`
- Frontend details: `frontend/README.md`
