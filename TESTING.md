> **Superseded for answer quality:** see `EVALS.md` for the repeatable end-to-end accuracy eval
> (126+ cases, metrics, regression gate). This file remains the manual local-infra/latency/audit runbook.

# Testing DocLens

How to test DocLens locally end-to-end: dependency checks, local self-hosted
datastore setup, ingestion, latency measurement, and the groundedness-audit
methodology. Written so a future agent (or human) can be told "refer to
TESTING.md and perform this testing" with no other context.

---

## 0. Prerequisites — check these BEFORE testing anything

Testing DocLens end-to-end requires three things to be healthy first. Check
them in this order; each layer's failure looks like the next layer's bug if
you skip straight to step 3.

### 0.1 Local Mongo (self-hosted, persistent)

DocLens's own state (chat threads, messages, document registry) lives in a
**local, self-hosted, persistent** Mongo container — never point local dev at
MongoDB Atlas or any other cloud cluster.

```bash
docker compose -f docker-compose.dev.yml up -d      # starts doclens-dev-mongo on :27019
docker ps --filter name=doclens-dev-mongo            # should show "Up"
```

`backend/.env` must have:
```
MONGO_URI=mongodb://doclens:doclens@localhost:27019/doclens?authSource=admin
MONGO_DB=doclens
```

The container is `restart: unless-stopped` with a named volume
(`doclens-dev-mongo`), so data survives `docker restart` / host reboot — it is
not a throwaway instance. Port `27019` was chosen because `27017` is often
taken by a local `mongod` and `27018` is the sister Offrloop repo's own dev
Mongo — check `docker ps` / `lsof -nP -iTCP:<port> -sTCP:LISTEN` before
reusing a port on a machine that runs multiple projects.

### 0.2 Brain must be healthy (DocLens has almost no RAG logic of its own)

DocLens delegates **all** extraction/embedding/retrieval/generation to Brain.
If Brain's vector store (Qdrant) is unreachable, every ingest and every chat
with documents in scope will fail — and it will look like a DocLens bug if
you don't check this first.

```bash
curl -s localhost:8000/health
# {"status":"ok","chat_model":"...","embed_model":"...","providers":[...]}
```

That only proves the *process* is up. Prove the vector path itself works with
a real retrieve call (an empty `chunks: []` on a fresh/unused namespace is a
healthy response — a 500 is not):

```bash
BRAIN_KEY=$(grep '^BRAIN_API_KEY=' backend/.env | cut -d= -f2-)
curl -s -X POST localhost:8000/v1/retrieve \
  -H "Authorization: Bearer $BRAIN_KEY" -H 'Content-Type: application/json' \
  -d '{"app_name":"doclens_probe_test","query":"test query","top_k":3}'
# {"chunks":[]}  <- healthy (empty because nothing is ingested under this app_name/namespace yet)
```

If Brain's own local Qdrant is misconfigured (e.g. pointed at a dead cloud
cluster), `/health` will still return `200` — the process-level check is not
sufficient. Always do the retrieve probe too. See Brain's own
`docker-compose.dev.yml` / `DEPLOY.md` if Brain's local Qdrant needs fixing —
that is Brain's concern, not DocLens's, but DocLens testing is blocked until
it's healthy.

### 0.3 BYOK key availability (what pays for `/chat` generation)

`/chat` is the only DocLens endpoint that calls an LLM, and it is BYOK-only —
there is no fallback key. Before running any latency/groundedness batch,
figure out what you can actually call for free vs. what costs real money:

```bash
# 1. Any OpenAI/Anthropic key in the shell env or backend/.env? (DocLens intentionally
#    keeps none server-side by design — this should normally come back empty)
env | grep -iE 'OPENAI_API_KEY|ANTHROPIC_API_KEY'

# 2. Is Ollama running locally, and what models are pulled?
curl -s localhost:11434/api/tags | python3 -c "import json,sys; print([m['name'] for m in json.load(sys.stdin)['models']])"
```

If Ollama is running with at least one model pulled, use DocLens's
`ollama_local` provider — it is the **one** provider explicitly exempted from
the API-key requirement (`backend/app/api/routes.py::_require_llm`), and
Brain forwards it straight to your local Ollama daemon, so it's zero-cost.
**Brain's default `ollama_local` model is `llama3.1`** — if that specific tag
isn't pulled, you must pass whatever tag *is* pulled explicitly as `model` in
the `/chat` request body (e.g. `"model": "llama3.2:3b"`), or the call will
fail against a model Ollama doesn't have.

If Ollama isn't running and no OpenAI/Anthropic key is available: **report
`retrieve_ms` only** (retrieval needs no LLM — Brain's embeddings are local)
and state plainly that `generate_ms` / `total_ms` need a real key. Do not
skip the latency section entirely; the retrieval half is still real signal.

---

## 1. Real-document ingestion

Use genuinely real documents, not lorem-ipsum placeholders — 3–5 is enough.
Good sources: real technical docs/READMEs already on the machine (this
repo's own `PRD.md`/`CLAUDE.md`/`DEPLOYMENT.md`, a sibling project's
`DEPLOY.md`, etc.) or well-known public URLs. Avoid anything private/personal.

Ingest via the **global** scope so every test chat can see them without
per-thread wiring:

```bash
TESTUSER="stresstest-$(date +%s)"      # any stable string; used as the Brain namespace + Mongo user_id
curl -s -X POST localhost:8001/resources -F "file=@PRD.md" -F "user_id=$TESTUSER"
# {"status":"ok","doc_id":"...","filename":"PRD.md","chunk_count":42}
```

A `chunk_count > 0` confirms the full path worked: extract → chunk → embed →
store in Qdrant → record in `doclens_documents`. If this 500s, re-check §0.2
before assuming it's a DocLens bug — in the one prior incident this project
hit, ingestion failures were 100% attributable to Brain's dead Qdrant, not to
any DocLens-side defect (confirmed by re-running the identical ingest call
immediately after Brain's Qdrant was fixed, with zero code changes on the
DocLens side).

## 2. Latency

`retrieve_ms` and `generate_ms` are computed inside `run_chat()` in
`backend/app/services/chat.py` (~lines 119–136) and returned under the
response's `meta` object. `total_ms` is added one layer up in
`backend/app/api/routes.py` (`chat_endpoint`), wrapping the whole `run_chat()`
call — it is not set inside `chat.py` itself. **None of the three fields are
persisted anywhere** (confirmed against `doclens_messages`' schema in
`backend/app/services/threads.py::add_message`) — every latency report is a
live reproduction, not a query against historical data, unless that's changed
since this was written.

Methodology:
1. Ingest 3–5 real documents globally (§1).
2. Fire a batch of real questions (20–30 is plenty) at `POST /chat` with a
   consistent `user_id`/namespace, using the BYOK path identified in §0.3.
   Each question should be answerable from the ingested docs — mix direct
   lookups ("what port does X run on") with light cross-document synthesis.
3. Collect `meta.retrieve_ms` / `meta.generate_ms` / `meta.total_ms` from
   every response into three arrays; compute p50/p95 (and min/max/mean for
   context) per field.
4. Report the actual N. Don't extrapolate from a handful of calls.

## 3. Groundedness audit

DocLens's product bet is "answer only from retrieved source text, cite it
inline." The `grounded` field on a `/chat` response is **not** a faithfulness
check — read `backend/app/services/chat.py::run_chat`, the field is literally
`bool(chunks)`, i.e. "did retrieval return anything." It says nothing about
whether the model's actual answer stayed inside those chunks. A real
groundedness number requires manually checking answer content against cited
source text.

Methodology, per answer:
1. Read the `answer` text and identify its checkable factual claims (a
   number, a name, a port, a file path, a described behavior — anything with
   a definite right/wrong).
2. For each claim, find the citation(s) `[n]` attached to it and read that
   citation's `text` field in full (don't rely on truncated previews).
3. Judge:
   - **Grounded** — the claim is actually stated in (or a reasonable
     restatement of) the cited chunk's text.
   - **Not grounded / hallucinated** — the claim contradicts the cited
     text, or isn't supported by any retrieved chunk at all, even if a
     citation marker is attached to it. This includes numeric transposition
     (e.g. citing the right chunk but stating the wrong number from it) and
     outright fabrication.
   - **Citation-misattributed but factually correct** — worth tracking
     separately: the stated fact is genuinely correct and *is* present
     somewhere in the SOURCES block, but the `[n]` marker points at a chunk
     that doesn't actually contain it. This is a real citation-accuracy bug
     even though it isn't a hallucination.
   - **Appropriately declined** — the model says it doesn't have enough
     information, and that's actually true of its retrieved context (the
     right chunk genuinely wasn't retrieved). This is correct
     "clarify-before-assuming" behavior per the product's own design goal —
     don't count it as a failure.
   - **Inappropriately declined** — the model declines or hedges even
     though the answer was sitting in its own cited chunk text. This is a
     real failure (a synthesis failure, not a retrieval failure).
4. Tally grounded vs. not-grounded claims; report the real percentage, the
   actual N, and 3–5 concrete examples of each category (quote the answer
   text and the relevant citation text side by side — that's the only way
   the number is checkable by someone else later).
5. Small local models (e.g. a 3B-parameter Ollama model) are expected to
   hallucinate more than a frontier BYOK model given the *identical* retrieved
   context — note the model used, and don't present a small-model failure
   rate as if it characterizes DocLens's pipeline quality in general. The
   useful signal is *whether retrieval put the right chunk in front of the
   model* (a DocLens/Brain concern) separately from *whether the model then
   used it correctly* (a model-quality concern).

## 4. Cleanup

Every test artifact should be removable through the app's own API — never
reach into Mongo directly to delete rows (that would mask a bug in the
delete path itself).

```bash
# Per-document (global resource):
curl -s -X DELETE "localhost:8001/resources/$DOC_ID?user_id=$TESTUSER"

# Per-thread (also removes that thread's own scoped documents + messages):
curl -s -X DELETE "localhost:8001/threads/$THREAD_ID?user_id=$TESTUSER"

# Full wipe for one user_id in one call (requires an Authorization: Bearer
# token whose decoded `sub` claim equals the user id — see backend/app/auth.py;
# the query-param fallback above does NOT apply to /delete_all):
curl -s -X POST localhost:8001/delete_all -H "Authorization: Bearer <token>"
```

After cleanup, verify local Mongo collection counts are back to whatever they
were before testing (a fresh `doclens-dev-mongo` container starts at
`0/0/0` — confirm against that, not an assumption):

```bash
docker exec doclens-dev-mongo mongosh -u doclens -p doclens --authenticationDatabase admin doclens --quiet --eval '
  JSON.stringify({
    threads: db.doclens_threads.countDocuments(),
    messages: db.doclens_messages.countDocuments(),
    documents: db.doclens_documents.countDocuments()
  })
'
```

## 5. Production usage check (read-only)

Production is a separate, already-correct deployment (self-hosted Mongo +
Brain on the shared Hetzner box) — local testing never touches it. To check
real usage without ever printing a credential:

```bash
ssh deploy@<hetzner-ip> 'docker exec doclens-backend python -c "
import os, pymongo
client = pymongo.MongoClient(os.environ[\"MONGO_URI\"])   # read from the container'"'"'s own env — never echoed
db = client[os.environ.get(\"MONGO_DB\",\"doclens\")]
print(\"threads:\", db[\"doclens_threads\"].count_documents({}))
print(\"messages:\", db[\"doclens_messages\"].count_documents({}))
print(\"documents:\", db[\"doclens_documents\"].count_documents({}))
"'
```

**Never** run `docker exec doclens-backend printenv` or similar and print the
output directly — that dumps `MONGO_URI` (with its password) and
`BRAIN_API_KEY` to your terminal/logs. Always read env vars from *inside* a
script executed in the container so the raw value never crosses back out
unredacted, or pipe through `sed -E 's/(=.*)/=<REDACTED>/'` if you must
inspect a var name/presence check locally.

## 6. Credential-safety reminder

Never print a Mongo URI, `BRAIN_API_KEY`, or any BYOK key to your own output
— not even partially, not even "just to confirm it's set." Check presence
(`grep -c '^BRAIN_API_KEY=' backend/.env`) or length (`${#VAR}`) instead of
value, and redact (`sed -E 's/(=.*)/=<REDACTED>/'`) whenever you must dump an
`.env`-shaped file for review.
