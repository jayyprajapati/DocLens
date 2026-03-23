# DocLens Frontend: Document Chat And Upload Interface

The frontend is the interactive face of DocLens. It provides a streamlined workflow for uploading documents, running grounded Q&A, and iterating quickly with model selection and session controls. As DocLens evolves into a personal assistant, this UI is designed to grow into a multi-tool control surface where users can combine document intelligence with task execution across additional tools and services.

## What The Frontend Does

- Lets users upload documents to backend ingest endpoint.
- Supports chat-style queries against ingested content.
- Displays model responses and source metadata.
- Persists session id, model, and optional API key in local storage.

## Tech Stack

- React
- Vite
- ESLint

## Prerequisites

- Node.js `18+` (Node `20+` recommended)
- npm `9+`
- Backend running on `http://localhost:8001`

## Install

```bash
cd /Users/jay/Desktop/Projects/DocLens/frontend
npm install
```

## Run Frontend

```bash
cd /Users/jay/Desktop/Projects/DocLens/frontend
npm run dev
```

Default app URL: `http://localhost:3000`

## Backend Connection

Frontend API base URL is currently set in `src/services/api.js`:

```js
const API_BASE_URL = 'http://localhost:8001'
```

If your backend runs on a different host/port, update that value.

## Useful Commands

```bash
# Development server
npm run dev

# Linting
npm run lint

# Production build
npm run build

# Preview production build locally
npm run preview
```

## Debugging

### Start dev server with explicit host/port

```bash
cd /Users/jay/Desktop/Projects/DocLens/frontend
npm run dev -- --host 0.0.0.0 --port 3000
```

### Debug browser/API behavior

1. Open browser devtools Network tab.
2. Verify requests to `http://localhost:8001/query`, `/ingest`, and `/generate`.
3. Check response payloads and status codes.

### Common errors

- `Failed to fetch`:
	- Backend not running on `8001`.
	- CORS mismatch.
- 5xx responses in UI:
	- Backend cannot reach upstream RAG service.
- Upload appears stuck:
	- Large file or upstream timeout.

## Developer Notes

- Model options are currently defined in header component.
- API key is optional and stored locally per browser session.
- Reset clears local storage and starts a fresh client session id.

## Future Frontend Expansion

Planned assistant-oriented UI capabilities:

1. Tool palette for multi-tool actions (search, notes, workflows).
2. Explainable action timeline showing assistant decisions and tool calls.
3. Workspace memory panels (recent facts, saved context, preferences).
4. Multi-step task composer with approval checkpoints.
5. Team collaboration views and shared assistant sessions.
