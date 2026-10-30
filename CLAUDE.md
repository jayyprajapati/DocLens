# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DocLens is a NotebookLM-style document Q&A app. Users upload documents and ask questions answered
with grounded, cited responses — either in **free mode** (the server's own Ollama Cloud key, admin-chosen
model, daily quotas) or **BYOK** (their own OpenAI / Anthropic (Claude) / Ollama Cloud key).
Live settings and analytics are managed from the **Admin panel** (`~/Desktop/Projects/Admin`, DocLens
sections) through DocLens's internal API — never by editing env and redeploying.

DocLens delegates **all** RAG/LLM work to **Brain** — a standalone,
application-agnostic RAG engine (`/Users/jay/Desktop/Projects/Brain`). Brain owns
chunking, embeddings, vector search, reranking, and the BYOK LLM call.
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

### Tests & evals (run after ANY change to prompts, retrieval, guardrails or Brain)
```bash
cd backend && pip install -r requirements-dev.txt && python -m pytest tests -q   # offline, ~1s: guardrails + grounding
# End-to-end eval (needs Brain + Mongo running and a BYOK key; see EVALS.md):
export BRAIN_API_KEY=... EVAL_API_KEY=<provider key>
python evals/run_eval.py --label my-change --model gpt-oss:20b          # all cases
python evals/compare.py baseline my-change --split test                  # regression gate
python evals/retrieval_eval.py --split dev                               # retrieval only, no LLM
python evals/stress_eval.py --model gemma4:31b   # file formats: 2-column, long, tables, CJK/Hindi/Spanish, scans, hostile files
```
`EVALS.md` documents the method, the dataset (201 cases: answerable, unanswerable, adversarial; dev/test/holdout splits),
the metrics, and the measured results. Tune on the `dev` split only; report `test`.

## The accuracy pipeline (what `services/chat.py::run_chat` does per turn)

1. **Input guardrails** (`guardrails.screen_query`) — NFKC-normalise, refuse prompt-injection /
   jailbreak / system-prompt-exfiltration / credential-fishing / delimiter-forging messages with
   no LLM call; greetings get a canned reply.
2. **Scope** — global docs ∪ this chat's docs (explicit `doc_ids` must belong to the caller).
3. **Query planning** (`retrieval.plan_queries`) — rewrite a follow-up / split a compound
   question *only when needed* (self-contained questions skip the extra LLM call).
4. **Retrieve + select** (`retrieval.retrieve_context`) — Brain returns a wide reranked pool per
   query (parallel); DocLens keeps chunks within a score margin of the best, per query.
5. **Evidence gate** — best rerank score below `EVIDENCE_GATE_SCORE` ⇒ "not found" with **no LLM call**.
6. **Grounded generation** — sources are `<source id=n>` blocks (delimiter-escaped, injection
   sentences removed by `guardrails.neutralize_source`); the model first copies verbatim
   `<evidence>` quotes, then writes the `<answer>` (or `NOT_FOUND: …` / `CLARIFY: …`).
7. **Verification** — `grounding.py`: numbers not in the sources (or simple arithmetic on them)
   trigger one corrective retry; evidence quotes are checked against the sources; citation markers
   are repaired (never overriding verified evidence). `answerability.py`: when risk signals fire
   (`ANSWER_VERIFY=auto`) a short strict second call rejects answers that stretch a fact to a
   different time/place/situation.
8. **Output guardrails** — HTML stripped, remote images/links not in the sources removed, replies
   that echo the system prompt are blocked.
9. **Response** — only the sources the answer actually cites, renumbered `[1..k]` so
   `sources[n-1]` matches marker `[n]`, each with the verified `quote`; `grounded` = verified
   citations exist; `abstained` = nothing in the docs answered it; `blocked` = guardrail refusal;
   `meta` carries timings and `guardrails` flags (also persisted on the message row).

Documents are ingested as `sniff type → sandboxed extract → sha256 dedup → injection scan →
/v1/ingest(title=filename)` so every chunk is embedded as "title > heading" and re-uploads don't create
duplicate chunks. **Parsing never happens in Brain** (shared with other projects): `extraction.py` verifies
the real file type from bytes, rejects zip bombs / macros / encrypted files, then runs
`extract_worker.py` as a child process with CPU/memory/no-write/no-fork rlimits, an empty environment and
a timeout (one at a time by default). The worker reads PDFs column-aware (two-column papers), marks
headings from font size, places tables inline as Markdown, drops invisible text (white, <2 pt,
off-page — classic injection hiding) and flags scanned/image-only pages. Images are not OCR'd.
Refused with a clear "please upload another file" message: password-protected PDFs (RC4/AES) and DOCX
(OLE `EncryptedPackage`), documents mostly in a non-Latin script (`latin_script`: only English and other
Latin-alphabet languages are supported — the embedder is English), scanned-only PDFs, fake/mismatched
types. Permissions-only ("owner password") PDFs open normally. Tables are attached to the paragraph that
introduces them so caption + table stay in one chunk. Uploads that index 0 chunks are errors. Documents expire after `uploads.expire_hours` (sweeper thread).

**Brain compatibility:** DocLens only depends on Brain's public API. The additive Brain changes
(optional `reasoning` on `/v1/generate`, extra `chunk_index` on retrieved chunks) are opt-in and
do not change behaviour for Offrloop or Portfolio.

## Backend architecture (`backend/app/`)

- `main.py` — FastAPI app, CORS, Mongo index creation on startup (lifespan).
- `config.py` — env settings: Brain/Mongo/CORS, secrets (`SESSION_SECRET`, `ADMIN_API_TOKEN`,
  `HOSTED_OLLAMA_API_KEY`) and the hard sandbox ceilings (`EXTRACT_*`, `HARD_MAX_*`). Tunables here only seed
  defaults.
- `runtime.py` — **live, admin-editable settings** (one validated Mongo doc `doclens_settings`, cached
  10 s): hosted model/fallback/quotas, BYOK providers + suggested models, answer style
  (concise|balanced|detailed), verifier, retrieval thresholds, upload limits, expiry, kill switches, banner.
  Read via `runtime.current()`; never read these from `settings`.
- `auth.py` — server-signed anonymous sessions (`POST /session` → `dl1.<payload>.<hmac>`); old unsigned
  browser tokens are upgraded once (same UUID). Dev without `SESSION_SECRET` still accepts unsigned tokens
  (evals). `client_ip` = right-most X-Forwarded-For (Caddy); `ip_hash` for quotas/analytics.
- `extraction.py` + `extract_worker.py` — the upload sandbox (above).
- `analytics.py` — `record()` events into `doclens_events` (TTL), atomic daily quotas in `doclens_usage`,
  and the stats/event/user views the admin API serves.
- `api/admin.py` — `/internal/admin/*` (config get/put, stats, events, users, hosted model list,
  test-model, sweep). `X-Admin-Token` == `ADMIN_API_TOKEN`; 404 when unset; Caddy blocks it publicly.
- `brain_client.py` — sync httpx client for Brain (`ingest_text`, `retrieve`, `generate`, `delete`,
  `ping`). All calls carry `app_name` + Bearer key; the `llm` override is forwarded on every generation
  (free mode adds a private `_fallback` model tried once on 402/403/404/410/429/5xx). Raises
  `BrainError(status, detail)`.
- `db.py` — pymongo client + `doclens_threads` / `doclens_messages` /
  `doclens_documents` collections (+ indexes). DocLens state only.
- `prompts.py` — the domain prompts: the evidence-then-answer system prompt (security rules,
  answer-only-what-was-asked, NOT_FOUND / CLARIFY protocol), the query-planning prompt, and the
  tagged `<sources>` / `<history>` / `<question>` prompt builders.
- `guardrails.py` — input screen, document-text neutralisation, output sanitiser (see above).
- `grounding.py` — parse the tagged model reply, verify evidence quotes, numeric-hallucination
  check, citation repair/renumbering. Pure functions, unit-tested in `tests/`.
- `retrieval.py` — query planning, parallel retrieval, lexical rescoring, margin-based selection.
- `answerability.py` — risk-triggered second-opinion verifier (`ANSWER_VERIFY=auto|always|off`).
- `limits.py` — in-process per-user rate limiter (`CHAT_RATE_PER_MIN`, `UPLOAD_RATE_PER_10MIN`).
- `schemas.py` — request models; `VALID_PROVIDERS = {openai, anthropic, ollama_cloud, ollama_local}`.
- `services/threads.py` — chat-session + message CRUD.
- `services/documents.py` — registry mapping `doc_id → {user, filename, scope, thread}`;
  ingest/list/delete; `global_doc_ids` / `thread_doc_ids` / `filename_map`.
- `services/chat.py` — `run_chat`: resolve/create thread → load recent history →
  scope docs → (LLM) contextualize follow-up → Brain retrieve → grounded+cited
  Brain generate (BYOK) → persist turns → return `{answer, citations, thread_id, meta, grounded}`.
- `api/routes.py` — endpoints (below).

### Endpoints
`POST /session` · `GET /config` (free-mode availability + remaining quota, providers, limits, banner) ·
`GET /health` · `GET /models?provider=` (key in `X-Provider-Key`) · `POST /chat` (`provider="hosted"` = free mode) ·
`POST /ingest` (per-chat upload; ≤`MAX_UPLOAD_MB`, pdf/docx/md/txt only) · `GET /documents?thread_id=` ·
`POST /delete` · `POST /delete_all` ·
`POST /resources` · `GET /resources` · `DELETE /resources/{doc_id}` (global) ·
`GET /threads` · `GET /threads/{id}` · `PATCH /threads/{id}` · `DELETE /threads/{id}`.

Key rule: only LLM calls (`/chat`) need a key — the user's (BYOK) or, in free mode, the server's
`HOSTED_OLLAMA_API_KEY` with the admin-chosen model (the client can't pick it); never Brain's own keys.
Uploads/retrieval need no key. Brain 4xx (e.g. bad key) → 400 to the browser; 5xx/unreachable → 502 with
a generic message (no internal hostnames). Every chat/upload/rejection/deletion is recorded in
`doclens_events` for the admin panel.

## Frontend (`frontend/src/`)

- `App.jsx` — owns shared state; `documents` = active thread's attachments,
  `resources` = global resources. Per-chat docs load on thread hydrate/select.
- `components/Header.jsx`, `components/ThreadSidebar.jsx` — BYOK settings
  (providers: OpenAI, Claude/Anthropic, Ollama Cloud) + global Resources uploader.
- `components/InputBar.jsx` — composer with paperclip (per-chat upload).
- `components/MessageBubble.jsx` — renders answers; inline `[n]` markers map to
  `message.sources[n-1]`; citation shape is `{ index, section, page, text, doc_id, filename, score }`.
- `services/api.js` — all fetch calls (auto re-session on 401); `services/auth.js` gets/refreshes the
  signed session; `services/providers.js` builds provider/model options from `/config` (free mode first).

**Component note:** import bare (`./components/Header`) resolves to the `.jsx`.
Do not recreate empty `.js` siblings — they shadow the real component under Vite.

## Environment

`backend/.env`: `BRAIN_BASE_URL`, `BRAIN_API_KEY`, `BRAIN_APP_NAME=doclens`,
`MONGO_URI`, `MONGO_DB=doclens`, `CORS_ALLOWED_ORIGINS`, `ENV`; production also needs
`SESSION_SECRET`, `ADMIN_API_TOKEN`, `HOSTED_OLLAMA_API_KEY` (see `backend.env.example`).
Optional seeds for the admin-editable settings (defaults are eval-calibrated, see `config.py`): `RETRIEVE_TOP_K/TOP_N`,
`CONTEXT_MAX_CHUNKS`, `CONTEXT_SCORE_MARGIN`, `EVIDENCE_GATE_SCORE`, `ANSWER_TEMPERATURE`,
`ANSWER_REASONING`, `ANSWER_VERIFY`, `DEBUG_TRACE` (eval only — puts raw model output in `meta`).
`frontend/.env`: `VITE_API_BASE_URL=http://localhost:8001`.

## Supported documents & providers
- Files: **PDF, DOCX, Markdown** (Brain also accepts plain text; legacy `.doc` is rejected).
  Brain uses pdfplumber for PDFs (renders tables as Markdown) with a pypdf fallback.
- Providers (BYOK): **OpenAI**, **Anthropic (Claude)**, **Ollama Cloud**.
