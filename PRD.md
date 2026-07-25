# DocLens — Product Requirements Document

**Version:** 1.0
**Last updated:** 2026-07-25
**Owner:** Jay Prajapati
**Status:** Live (production) — `https://doclens.jayprajapati.dev`

---

## 1. Executive Summary

DocLens is a **NotebookLM-style, BYOK (Bring Your Own Key) document Q&A application**.
Users upload their own documents (PDF, DOCX, Markdown), ask natural-language
questions about them, and get **grounded, cited answers** — powered by the LLM
provider and API key *they* supply. There is no shared/fallback key and no
document processing happens without a document being explicitly uploaded by the
user.

DocLens is deliberately architected as a **thin orchestration and state layer**
sitting in front of a separate, standalone RAG engine called **Brain**. DocLens
owns *application* state (chat sessions, messages, and the document registry);
Brain owns *all* RAG/ML mechanics (extraction, chunking, embeddings, vector
search, reranking, and the actual BYOK LLM call). This separation means DocLens
itself has almost no ML surface area — its job is product experience, state
management, and orchestration, not model plumbing.

---

## 2. Problem Statement

### 2.1 The problem

Knowledge workers, students, researchers, and professionals routinely need to
"talk to" a document — a contract, a research paper, meeting notes, a report —
rather than read it linearly. Existing solutions fall into two unsatisfying
camps:

1. **Consumer tools (e.g. NotebookLM)** are excellent UX but are closed
   platforms: users can't choose their model, can't control cost, and their
   documents/questions flow through a vendor's own backend and default model,
   with no visibility into or control over which LLM actually answers.
2. **Roll-your-own RAG scripts** are flexible but require real engineering
   effort per use case — no persistent chat sessions, no document scoping, no
   polished UI, and usually a hardcoded single LLM key baked into the backend
   (a security and cost-control problem for anyone who wants to self-host or
   share the tool).

### 2.2 Why BYOK matters

Because DocLens never holds an LLM key of its own:
- **No standing cost liability** for the operator — every generation call is
  billed to the user's own OpenAI/Anthropic/Ollama account.
- **No vendor lock-in for the user** — they can switch providers/models
  per-conversation.
- **Reduced trust burden** — the key lives only in the browser and is sent
  per-request; it is never persisted server-side by DocLens or by Brain.

### 2.3 Why answers must be grounded and cited

A document Q&A tool is only useful if it can be trusted. An assistant that
"sounds right" but silently fabricates facts, page references, or figures is
worse than no tool at all for the target use cases (contracts, research,
compliance-adjacent reading). DocLens' core product bet is:

> **Answer only from what's actually in the retrieved source text, cite it
> inline, and ask a clarifying question rather than guess when the source
> doesn't say enough.**

This is enforced structurally (a numbered SOURCES block is the only knowledge
the model is given per turn) and stylistically (the system prompt's
"clarify-before-assuming" rule), not just as a suggestion.

### 2.4 Goals / non-goals

**Goals**
- Let a user go from "I have a PDF" to "I have a cited answer" in under a
  minute, with zero backend setup on their part beyond pasting an API key.
- Support two natural upload scopes: documents relevant to *everything* you
  discuss, and documents relevant to *one specific conversation*.
- Keep per-user data strictly isolated (one user can never retrieve another
  user's vectors or chat history).
- Keep the product layer (DocLens) swappable from the RAG engine (Brain) so
  either can evolve independently.

**Non-goals**
- DocLens is not a general-purpose agent platform — it does not run tools,
  execute code, or browse the web on the user's behalf.
- DocLens does not implement its own embedding/reranking/vector-search stack
  — that is explicitly Brain's responsibility.
- No multi-user collaboration / sharing of chats or documents between
  different users (each browser-generated identity is its own silo).
- No accounts, passwords, or OAuth — identity is a lightweight anonymous
  per-browser id, not a real auth system.

---

## 3. Users & Use Cases

There is a single user type — an individual bringing their own documents and
their own LLM key. Representative scenarios:

- **Research reading** — upload a paper (or several) as global resources and
  interrogate them across multiple chat sessions.
- **Single-document deep dive** — attach one contract/report to a single chat
  via the paperclip and ask questions scoped only to that document, without
  polluting other conversations' context.
- **Comparative Q&A** — upload multiple documents and ask a question that
  spans them; if the question ambiguously refers to "this document" while
  several are in scope, DocLens asks the user to disambiguate rather than
  guessing which one.
- **Cost/model control** — a user who wants to use a cheaper/faster model
  (`gpt-4o-mini`, `claude-haiku-4-5`) for casual browsing and a stronger model
  for a high-stakes read, switching per session via their own key.

---

## 4. Core Product Concepts

### 4.1 Two upload flows (the central product decision)

| | Global Resources | Per-chat Attachments |
|---|---|---|
| **Entry point** | Left sidebar "Resources" uploader | Paperclip icon in the message composer |
| **API** | `POST /resources` | `POST /ingest` |
| **Scope tag** | `scope="global"` | `scope="thread"`, tied to a `thread_id` |
| **Visibility** | Every chat for that user | Only the chat it was uploaded into |
| **Use case** | "Things I always want the assistant to know" | "This one document, this one conversation" |

At query time, retrieval scope for a chat = `(user's global docs) ∪ (this
chat's docs)`. Uploading via the paperclip into a brand-new (not-yet-created)
chat causes the backend to create the chat session on the fly and return its
`thread_id`, which the frontend adopts transparently.

### 4.2 Grounded, cited, clarify-before-assuming answers

Every answer is generated from a numbered `SOURCES` block built from the
top reranked chunks Brain retrieves for the query. The system prompt
("Lume," DocLens' assistant persona) is constrained to:
1. Cite every factual claim inline as `[n]` (ASCII brackets only).
2. Never introduce facts/numbers/names/dates not present in the sources.
3. Ask a short clarifying question when the question is ambiguous or the
   sources don't cover it, instead of fabricating an answer.
4. Write in natural conversational prose (not a bulleted "report dump"),
   with formatting only where it genuinely helps.

If a chat has **no documents in scope at all**, DocLens short-circuits before
ever calling the LLM and returns a canned instructional reply — saving an
unnecessary (and BYOK-billed) generation call.

### 4.3 Conversational memory & query rewriting

Brain is intentionally stateless per call — it has no concept of a
"conversation." DocLens supplies memory by:
- Persisting every turn (`doclens_messages`) and loading the last 8 messages
  of a thread as history for each new turn.
- Before retrieval, rewriting an elliptical follow-up ("what about the second
  one?", "and the cost?") into a standalone search query using a small,
  cheap, deterministic (`temperature=0.0`) LLM call against the conversation
  history — falling back silently to the raw query text if this call fails,
  so a rewrite hiccup never blocks the main answer.

### 4.4 Ambiguous single-document detection (frontend heuristic)

When a brand-new chat has more than one document in scope and the user's
message matches a pattern like *"summarize **this** document"* / *"what does
**the** file say"*, the frontend intercepts the message client-side (before
ever calling `/chat`) and renders a document-picker prompt so the user can
disambiguate which file they mean. This only fires pre-thread-creation —
once a thread exists its document scope is fixed server-side.

### 4.5 BYOK enforcement

- `/chat` is the only endpoint that touches an LLM, and it is the only
  endpoint that requires `{provider, api_key, model}`. Ollama running fully
  locally (`ollama_local`) is the one exception where no key is required.
  Missing/invalid BYOK fields are rejected with a 400 before Brain is ever
  called.
- Uploads and retrieval need **no** API key — embeddings and vector search
  run inside Brain using its own local embedding model, not the user's key.
- The user's key is held only in browser `localStorage` and is sent per
  request; it is never written to DocLens' database, logs, or Brain's
  storage.
- "Reset session" wipes the local key, all local UI state, and asks the
  backend to delete every document/vector/thread/message for that user id.

---

## 5. End-to-End Flow

### 5.1 Identity (no accounts)

On first load, the frontend (`services/auth.js`) generates a random
`crypto.randomUUID()` and stores it in `localStorage` as `doclens_user_id`.
It mints a lightweight, **unsigned**, JWT-*shaped* bearer token (`{sub:
userId, iat, exp}`, base64url header/payload/"signature", never actually
HMAC-signed) and sends it as `Authorization: Bearer <token>` on every
request. The backend (`auth.py`) decodes the `sub` claim — it does not
verify a signature, because there is no password/account system to
authenticate against. This user id becomes the vector `namespace` for every
Brain call, which is what keeps one browser's documents invisible to
another.

### 5.2 Upload → ingest

1. User drops a file into either the Resources panel or the chat paperclip.
2. Frontend calls `POST /resources` (global) or `POST /ingest` (per-chat,
   multipart, optionally with `thread_id`).
3. Backend generates a `doc_id` (UUID) and calls Brain's
   `POST /v1/extract` with `ingest=true`, `app_name=doclens`,
   `namespace=user_id`, `doc_id`. Brain extracts text (pdfplumber → pypdf
   fallback for PDFs; native parsing for DOCX/Markdown), chunks it, embeds
   locally, and stores vectors in its Qdrant collection under
   `(app_name, namespace, doc_id)`.
4. DocLens records the mapping in `doclens_documents` — `{doc_id, user_id,
   filename, content_type, scope, thread_id?, chunk_count, char_count,
   created_at}`. Brain never learns any of this metadata; it only ever sees
   opaque ids.
5. Response returns `{doc_id, filename, chunk_count[, thread_id]}` to the
   frontend, which appends the document to the active document list and
   (for a brand-new chat) adopts the server-created `thread_id`.

### 5.3 Ask a question → `/chat`

1. Frontend validates BYOK fields client-side; if incomplete, blocks the
   send with an inline warning.
2. `POST /chat` with `{query, provider, api_key, model, thread_id?,
   doc_ids?}`.
3. Backend (`services/chat.py::run_chat`):
   a. Resolves or creates the thread.
   b. Loads the last 8 messages as history, then persists the new user
      message.
   c. Computes scope: explicit `doc_ids` override, otherwise `global ∪
      thread` document ids for this user/thread. If scope is empty, returns
      the canned "no documents" reply without calling Brain or any LLM.
   d. Rewrites the query for retrieval if there's history
      (`CONTEXTUALIZE_SYSTEM`, cheap/deterministic LLM call, fail-open to
      raw query).
   e. Calls Brain `POST /v1/retrieve` with `{query, namespace, doc_ids,
      top_k}` → gets back reranked chunks `{text, heading, score, doc_id}`.
   f. Builds the full prompt: conversation history block + numbered SOURCES
      block (chunk text + filename + heading) + the question + formatting
      instructions.
   g. Calls Brain `POST /v1/generate` with `{system: ANSWER_SYSTEM, prompt,
      llm: {provider, api_key, model}, max_tokens, temperature}` — this is
      the one call that spends the user's BYOK budget.
   h. Cleans stray HTML artifacts from the model output
      (`clean_answer_text`), maps chunks → citation objects `{index,
      section, filename, doc_id, page, score, text}`, persists the
      assistant turn + citations, updates thread metadata (title on first
      turn, `updated_at`, `message_count`).
4. Response: `{answer, citations[], thread_id, grounded, meta: {
   retrieved_count, retrieve_ms, generate_ms, total_ms }}`.
5. Frontend renders the answer as Markdown (`react-markdown` + `remark-gfm`),
   maps `[n]` markers to `message.sources[n-1]`, drives an animated
   multi-stage progress UI (embedding → searching → reranking → generating)
   during the wait, and — on error — surfaces the most specific error string
   available (upstream Brain detail if present, else the raw message).

### 5.4 Delete / reset

- `POST /delete` — removes one document: best-effort Brain vector delete
  (a Brain hiccup doesn't strand the registry row) + registry row removal.
- Deleting a thread (`DELETE /threads/{id}`) removes that thread's
  chat-scoped documents (and their vectors) first, then the thread and its
  messages. Global resources are untouched by thread deletion.
- `POST /delete_all` — full per-user wipe: one Brain namespace-level vector
  delete, then all Mongo documents/threads/messages for that user id. Used
  by the frontend's "Reset session," which also clears `localStorage` and
  reloads.

---

## 6. System Architecture

```
Browser (React 19 + Vite, :3000 / static hosting)
      │  fetch + Bearer <unsigned dev JWT>
      ▼
DocLens Backend (FastAPI, :8001)
  - Owns Mongo state: threads, messages, document registry
  - Enforces BYOK on /chat only
  - No ML/embedding code of its own
      │  Bearer BRAIN_API_KEY · app_name=doclens
      │  /v1/extract · /v1/retrieve · /v1/generate · /v1/delete · /v1/llm/ping
      ▼
Brain (FastAPI, :8000) — standalone, application-agnostic RAG engine
  - Extraction (pdfplumber/pypdf, DOCX, Markdown), chunking, local embeddings
  - Vector storage/search + reranking (Qdrant, collection "doclens")
  - The one BYOK LLM call: forwards {provider, api_key, model} to —
      ├─► OpenAI
      ├─► Anthropic (Claude)
      └─► Ollama Cloud / Ollama Local
```

**Why this split exists:** Brain is a separate repository/service designed to
be reused by *other* applications beyond DocLens (e.g. Admin/Portfolio use
the same shared-infra pattern with their own Brain-backed RAG needs). DocLens
never re-implements chunking/embeddings/reranking; it only ever talks to
Brain's four stable primitives. This means DocLens' entire backend is
essentially "state + orchestration + prompts," which keeps it small and easy
to reason about, and lets Brain's RAG quality improve independently of any
one consuming app.

**Per-user isolation:** every Brain call is scoped by `namespace=<user_id>`.
Retrieval additionally filters by the exact `doc_ids` in scope for the
current chat, so even within one namespace, a chat only ever sees its own
global + thread-scoped documents.

---

## 7. Technical Implementation

### 7.1 Backend — `backend/app/`

| File | Responsibility |
|---|---|
| `main.py` | FastAPI app instance, CORS config, Mongo index creation on startup (lifespan hook) |
| `config.py` | Env-driven `Settings`: `BRAIN_BASE_URL`, `BRAIN_API_KEY`, `BRAIN_APP_NAME` (default `doclens`), `BRAIN_TIMEOUT`, `MONGO_URI`, `MONGO_DB`, `RETRIEVE_TOP_K` (40), `ANSWER_MAX_TOKENS` (1400), `ANSWER_TEMPERATURE` (0.4), `CORS_ALLOWED_ORIGINS`, `ENV` |
| `auth.py` | `user_id_from_request`: decodes the bearer token's `sub` claim (unsigned, dev-grade); 401 if none resolvable |
| `brain_client.py` | Sync `httpx` client wrapping Brain's 5 endpoints; raises `BrainError(status, detail)` uniformly for both connectivity failures and upstream HTTP errors |
| `db.py` | `pymongo.MongoClient` + 3 collections (`doclens_threads`, `doclens_messages`, `doclens_documents`) + index creation (best-effort, non-fatal on startup) |
| `prompts.py` | `ANSWER_SYSTEM` (Lume persona + grounding rules), `CONTEXTUALIZE_SYSTEM` (query rewriting), `NO_DOCS_REPLY`, `clean_answer_text` (strips model-emitted HTML), `build_sources_block` / `build_history_block` / `build_user_prompt` |
| `schemas.py` | Pydantic request models (`ChatRequest`, `ThreadPatchRequest`, `DeleteRequest`, `DeleteAllRequest`); `VALID_PROVIDERS = {openai, anthropic, ollama_cloud, ollama_local}` |
| `services/threads.py` | Thread + message CRUD, title derivation from the first question |
| `services/documents.py` | Document registry CRUD; `global_doc_ids` / `thread_doc_ids` / `filename_map` scope helpers |
| `services/chat.py` | `run_chat` — the full RAG orchestration described in §5.3 |
| `api/routes.py` | All HTTP endpoints (table below); uniform error mapping — Brain 4xx → 400 to the browser, Brain 5xx/unreachable → 502 |

**Endpoints**

| Method | Path | Auth/Key required | Purpose |
|---|---|---|---|
| GET | `/health` | – | Liveness + configured Brain URL |
| GET | `/models?provider=&api_key=` | – | Suggested model list per provider (Ollama Cloud calls `ollama.com/api/tags` live if a key is given) |
| POST | `/chat` | provider+key+model | Ask a question |
| POST | `/ingest` | – | Per-chat (paperclip) upload, multipart |
| GET | `/documents?thread_id=` | – | A chat's attachments |
| POST/GET/DELETE | `/resources[/{id}]` | – | Global resource upload/list/delete |
| GET/GET/PATCH/DELETE | `/threads[/{id}]` | – | Chat session list/detail/rename/delete |
| POST | `/delete` | – | Remove one document (registry + vectors) |
| POST | `/delete_all` | – | Full per-user reset |

### 7.2 MongoDB schema (DocLens-owned state; `doclens_`-prefixed collections
so the database can safely be shared with other apps)

- **`doclens_threads`**: `{_id, user_id, title, message_count, created_at, updated_at}`, indexed on `(user_id, updated_at desc)`.
- **`doclens_messages`**: `{_id, thread_id, user_id, role, content, citations[], created_at}`, indexed on `(thread_id, created_at asc)`.
- **`doclens_documents`**: `{_id (=doc_id), user_id, filename, content_type, scope, thread_id?, chunk_count, char_count, created_at}`, indexed on `(user_id, scope)` and `(thread_id)`.

### 7.3 Frontend — `frontend/src/`

| File | Responsibility |
|---|---|
| `App.jsx` | All shared state: BYOK settings, active thread, chat transcript, documents/resources, upload/query stage-progress animation, thread cache for instant tab switching, single-document ambiguity detection regex, title auto-generation heuristics |
| `components/Header.jsx` | Top bar BYOK controls (provider/key/model) |
| `components/ThreadSidebar.jsx` (+`.css`) | Chat list, new-chat, rename/delete, theme toggle, global Resources uploader/list |
| `components/InputBar.jsx` | Composer: text input, paperclip per-chat upload, per-chat attachment chips |
| `components/ChatWindow.jsx` | Transcript rendering, timeline (upload/query progress) messages, doc-select disambiguation prompt |
| `components/MessageBubble.jsx` | Renders assistant Markdown answers; `[n]` inline citation markers map to `message.sources[n-1]` |
| `components/CitationDrawer.jsx` | Expandable citation detail (section/page/text/score) |
| `components/InfoModal.jsx` | Confirm-delete dialogs (document / thread) |
| `components/AppFooter.jsx` | Footer, links to Privacy/Terms pages |
| `pages/PrivacyPage.jsx`, `pages/TermsPage.jsx` | Static legal pages (React Router) |
| `services/api.js` | All `fetch` calls to the DocLens backend |
| `services/auth.js` | Anonymous user id + unsigned dev-JWT minting (`getAuthHeaders`) |

**Client-side persistence** (`localStorage`): user id, BYOK key/model/provider,
theme, active thread id, sidebar open state, and a cached thread-summary list
for instant sidebar rendering before the network round-trip resolves.

### 7.4 Tech stack

**Backend**
- Python, **FastAPI** (`>=0.115`), **Uvicorn** (standard extras) as ASGI server
- **httpx** — sync client for all Brain calls
- **PyMongo** (`>=4.6`) + `dnspython` (SRV URIs) — MongoDB driver
- **Pydantic** (`>=2.0`) — request validation
- `python-multipart` — file upload parsing
- `python-dotenv` — `.env` loading

**Frontend**
- **React 19** + **Vite 8** (dev server + static build)
- **react-router-dom 7** — Privacy/Terms routing
- **react-markdown 10** + **remark-gfm** — answer rendering incl. GFM tables/lists
- **framer-motion** — stage-progress and transition animations
- **lucide-react** — icon set
- **uuid** — client-side id generation
- **ESLint 9** (flat config) — linting

**Infrastructure / deployment**
- **Docker** — backend packaged as a container image; frontend built as a
  static export (no container)
- **GitHub Actions → GHCR** — CI builds and pushes the backend image; the
  server only ever `docker compose pull`s, never compiles
- **Caddy** — reverse proxy + automatic HTTPS on a shared Hetzner box
- **MongoDB** (shared instance, dedicated `doclens` database/user) — DocLens'
  own state
- **Qdrant** (shared instance, `doclens` collection, owned/managed by Brain)
  — vector storage, created lazily on first ingest
- **Brain** — sibling service (own repo/deployment) providing all RAG
  primitives; reached in-cluster at `http://brain-backend:8000`

**Production URLs**
- Web: `https://doclens.jayprajapati.dev` (static `dist/` served by Caddy)
- API: `https://doclens-api.jayprajapati.dev` → `doclens-backend:8001`
- Brain: `https://brain.jayprajapati.dev` (public) / `http://brain-backend:8000` (in-cluster)

### 7.5 LLM providers & models (BYOK)

| Provider | Suggested models surfaced by `/models` |
|---|---|
| OpenAI | `gpt-4o-mini`, `gpt-4o`, `gpt-4.1-mini`, `gpt-4.1`, `o4-mini` |
| Anthropic (Claude) | `claude-sonnet-4-6`, `claude-opus-4-8`, `claude-haiku-4-5-20251001` |
| Ollama Cloud | Live-fetched from the user's `ollama.com/api/tags` if a key is supplied; falls back to `gpt-oss:120b` / `gpt-oss:20b` |
| Ollama Local | No key required; model list is caller-supplied |

### 7.6 Supported document types

PDF, DOCX, Markdown (`.md`); Brain also accepts plain text. Legacy binary
`.doc` is rejected. PDF extraction uses pdfplumber (renders tables as
Markdown) with a pypdf fallback for files pdfplumber can't parse.

---

## 8. Security & Privacy Model

- **No passwords/accounts** — identity is an anonymous per-browser
  `localStorage` UUID; there is nothing to breach because there is no
  credential store.
- **BYOK key never persisted** — lives only in the browser, sent per-request,
  never written to Mongo, disk logs, or Brain's storage.
- **Per-user data isolation** — every Brain call is namespaced by `user_id`;
  Mongo queries are always filtered by `user_id`, so cross-user document/chat
  access is structurally impossible through the API surface.
- **Upstream error hygiene** — Brain 4xx (bad key, bad request) is relayed to
  the browser as 400 with the upstream detail; Brain 5xx/unreachable is
  normalized to a generic 502 rather than leaking internals.
- **Brain API key** (`BRAIN_API_KEY`) is a server-side secret shared between
  DocLens and Brain, never exposed to the browser.
- **Full user-initiated erasure** — "Reset session" is a real, complete wipe
  (vectors + Mongo state), not a soft/local-only reset.

---

## 9. Current Limitations / Explicit Non-Goals

- No automated test suite yet (manual/local verification only).
- Identity is not real authentication — a cleared browser/localStorage is a
  new "user" with no recovery of prior chats/documents.
- No real-time streaming of the answer token-by-token — the current UX shows
  staged progress (embedding/searching/reranking/generating) while the full
  response is awaited, then renders it as a whole.
- No collaboration/sharing — chats and documents are single-browser-identity
  private by construction.
- No usage/cost dashboard for the user's own BYOK spend.

---

## 10. Glossary

- **BYOK** — Bring Your Own Key; the user supplies their own LLM provider API
  key for every generation call.
- **Brain** — the standalone RAG engine DocLens delegates all extraction/
  embedding/retrieval/generation work to.
- **Namespace** — Brain's per-user vector isolation key; DocLens always sets
  this to the user id.
- **Scope (`global` / `thread`)** — whether a document is visible to every
  chat (`global`, i.e. a Resource) or only one chat (`thread`, i.e. a
  per-chat attachment).
- **Grounded answer** — an answer generated strictly from retrieved source
  excerpts, with inline `[n]` citations back to those excerpts.
- **Lume** — the product's assistant persona/name as defined in the system
  prompt.
