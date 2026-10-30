# DocLens Test Results

**Date:** 2026-08-15
**Scope:** local-infra remediation, real-document ingestion retest, latency
measurement, groundedness audit, production usage re-check.
**Methodology:** see `TESTING.md`.

---

## 1. What was blocked last time, and why

The previous session (also 2026-08-15, see
`/Users/jay/Desktop/Projects/_stress-test-reports/doclens-stress-report.html`)
found two separate problems, both now resolved:

1. **Local `backend/.env` `MONGO_URI` pointed at MongoDB Atlas** — a cloud
   cluster shared with unrelated personal projects, not self-hosted. This
   violated the "local dev must point to self-hosted Docker, persistently"
   requirement (production was already correct — see §4).
2. **Brain's local Qdrant was a dead Qdrant Cloud cluster** (a free-tier
   cluster that appears to have been reclaimed — every path 404'd with a
   plain-text, non-Qdrant-shaped response). This made every `POST /v1/extract`
   and `POST /v1/retrieve` call on Brain return `500`, which DocLens correctly
   remapped to `502 upstream_error` — but it meant zero ingestion, zero
   retrieval, and therefore zero latency/groundedness data was obtainable.

**Root-cause conclusion, now verified empirically: the earlier failure was
100% attributable to Brain's dead Qdrant Cloud cluster, not to any
DocLens-side bug.** After a sister fix repointed Brain's local Qdrant at a
persistent self-hosted container, the *exact same* DocLens ingestion code
path (`POST /resources` → `backend/app/services/documents.py::ingest_document`
→ `brain_client.extract_and_ingest`), with zero DocLens code changes, ingested
4 real documents cleanly (144 total chunks, see §3). No separate DocLens-side
issue was found.

## 2. Local infra fix

- Added `docker-compose.dev.yml` at the repo root: a persistent, self-hosted
  Mongo container (`doclens-dev-mongo`, `mongo:7`, named volume
  `doclens-dev-mongo`, `restart: unless-stopped`, host port `27019` — `27017`
  was taken by an unrelated local `mongod`, `27018` by the sister Offrloop
  repo's own dev Mongo).
- Updated `backend/.env`: `MONGO_URI` now points at
  `mongodb://doclens:doclens@localhost:27019/doclens?authSource=admin`
  instead of the Atlas cluster. (Value not reproduced here — see the
  credential-safety note in `TESTING.md`.)
- Killed the running local backend process (uvicorn on `:8001`, PID from the
  Atlas-backed session) and restarted it fresh against the new config, per
  explicit instruction to restart rather than hot-swap.
- Verified clean boot: `GET /health` → `{"status":"ok","service":"doclens","brain":"http://localhost:8000"}`.
- Verified persistence intent: named volume + `restart: unless-stopped` (not
  an ephemeral/throwaway container — mirrors the pattern already used by
  Brain's own `docker-compose.dev.yml` for its dev Qdrant).

**Production was not touched.** It was already correct before this session —
`backend.env` on the server has `MONGO_URI=mongodb://<creds>@mongo:27017`
(shared self-hosted Mongo on `/srv/infra`) and
`BRAIN_BASE_URL=http://brain-backend:8000` — confirmed read-only via SSH.

## 3. Brain health verification

```
GET localhost:8000/health
{"status":"ok","chat_model":"gpt-oss:20b","embed_model":"BAAI/bge-base-en-v1.5",
 "providers":["openai","anthropic","ollama_cloud","ollama_local"]}
```

That alone doesn't prove the vector path works (the previous outage also
returned a healthy `/health` at the process level). A real `POST /v1/retrieve`
against an unused namespace returned `{"chunks":[]}` — a healthy empty result,
not a 500 — confirming Brain's Qdrant is genuinely reachable now, before any
DocLens-side testing began.

## 4. Real-document ingestion retest

Ingested 4 genuinely real, already-on-disk technical documents (not
lorem-ipsum) via `POST /resources` (global scope), under a throwaway test
`user_id`/namespace:

| File | Source | Chunks |
|---|---|---|
| `PRD.md` | this repo | 42 |
| `DEPLOYMENT.md` | this repo | 18 |
| `CLAUDE.md` | this repo | 17 |
| `DEPLOY.md` | sibling Brain repo | 67 |

All four returned `200`/`chunk_count > 0` on the first attempt — no retries,
no partial failures. **Ingestion is unblocked and confirmed working
end-to-end.**

## 5. Latency

BYOK-key check (per `TESTING.md` §0.3): no OpenAI/Anthropic key found in the
shell env or `backend/.env` (DocLens intentionally keeps none server-side —
by design, not a gap). Ollama **was** running locally
(`ollama serve`, several models already pulled, including `llama3.2:3b`).
Brain's `ollama_local` default model is `llama3.1`, which wasn't pulled, so
`model: "llama3.2:3b"` was passed explicitly on every `/chat` call — this is
the zero-cost path; **no BYOK-billed calls were made this session.**

28 real questions were fired at `POST /chat` against the 4 ingested documents
(direct lookups + light cross-document synthesis — see the question list
used at
`/private/tmp/claude-501/-Users-jay-Desktop-Projects-ReachFlow/6b4ebec9-a968-4713-9a49-c0834ec5c9b9/scratchpad/doclens_questions.txt`
for the exact prompts). All 28 succeeded (0 errors). `meta.retrieved_count`
was `5` on every call (the top-`k` reranked set Brain returned).

| Field | N | min | p50 | p95 | max | mean |
|---|---|---|---|---|---|---|
| `retrieve_ms` | 28 | 366 | 636 | 722 | 776 | 638 |
| `generate_ms` | 28 | 1172 | 2240 | 2974 | 3121 | 2255 |
| `total_ms` | 28 | 1912 | 2878 | 3616 | 3743 | 2901 |

Caveats:
- `generate_ms`/`total_ms` reflect a **3B-parameter local Ollama model**
  (`llama3.2:3b`) — a frontier BYOK model (GPT-4o, Claude) will have a
  different latency profile (likely higher `generate_ms` for a hosted API
  round-trip, but this wasn't tested — no key was available, and none was
  purchased for this audit per the zero-cost-path instruction).
- `retrieve_ms` (Brain's `/v1/retrieve`, local embeddings + Qdrant + rerank)
  is provider-independent and is the more broadly representative number.
- Confirmed via source read: none of `retrieve_ms`/`generate_ms`/`total_ms`
  are persisted on the message row — every future latency report will again
  be a live reproduction unless that's changed (see Recommendations in the
  artifact).

## 6. Groundedness audit

**N = 28** real answers audited (target was 30–50; 28 is the actual count
produced — each of the 28 `/chat` calls above was also graded for
groundedness, one audit pass over the same batch). Every claim was checked
against the *full* (untruncated) text of its cited chunk(s), not a preview.

**Critical finding: DocLens's `grounded` response field is not a
faithfulness check.** Reading `backend/app/services/chat.py::run_chat`, the
field is literally `grounded: bool(chunks)` — "did retrieval return
anything," not "does the answer actually match what was retrieved." All 28 of
28 answers in this batch had `grounded: true`, **including all 5 answers this
audit found to be factually wrong or fabricated.** A product surface (or a
future automated check) that trusts this field as a hallucination signal
would be wrong 100% of the time it matters.

### Result

- **23 / 28 (82%)** — core factual claim correct and supported by its cited
  chunk text.
  - Of these, **2 / 28 (7%)** had the *fact* right but the *citation index*
    wrong — the true supporting chunk was elsewhere in the SOURCES block, not
    at the `[n]` the model pointed to. Tracked separately per `TESTING.md`
    §3 — a real citation-accuracy defect, not a hallucination.
- **5 / 28 (18%)** — not grounded: wrong, fabricated, or an unwarranted
  refusal despite the answer being present in the model's own cited text.

### Concrete examples

**Clean grounded (for contrast):**
> Q: "What PDF extraction library does Brain use, and what is its fallback?"
> A: "...it uses `pdfplumber` for PDFs, which renders tables as Markdown. But
> ...if `pdfplumber` can't parse a file, Brain falls back on `pypdf`."
> Cited [1] `PRD.md §7.6`: "PDF extraction uses pdfplumber (renders tables as
> Markdown) with a pypdf fallback for files pdfplumber can't parse." — exact
> match.

**Hallucination — wrong number, contradicting its own cited source:**
> Q: "What is the default ANSWER_MAX_TOKENS value?"
> A: **"The default ANSWER_MAX_TOKENS value is 40."** (Correct answer: 1400.)
> Its own citation [1] (`PRD.md §7.1`, quoted in full in the response) reads:
> `` `ANSWER_MAX_TOKENS` (1400) ``. The model had the right number sitting in
> its own context window and stated a different, wrong one — apparent
> confusion with `RETRIEVE_TOP_K`'s value (40) from an adjacent line in the
> same table.

**Hallucination — fabricated a wrong product name over a correct one in the
first line of its own top citation:**
> Q: "What consumer product is DocLens compared to as its closest analog?"
> A: **"DocLens seems to be most closely compared to a digital document
> summarization tool like Simplenote."** (Correct answer: NotebookLM.)
> Citation [1] (`CLAUDE.md`, the model's *own* highest-ranked source, quoted
> in the response) begins: *"DocLens is a **NotebookLM-style**, BYOK... app."*
> "Simplenote" appears nowhere in any of the 5 retrieved chunks. This is the
> starkest failure in the batch — not a synthesis gap, an outright
> fabrication in place of an answer that was the literal first sentence
> available to the model.

**Failure to use available information (declined despite having the fact):**
> Q: "What port does Brain run on?"
> A: "...there's no direct mention of what port Brain actually runs on... Can
> you point me at the specific section?"
> Citation [1] (`CLAUDE.md`, quoted in the response) reads: *"Brain must be
> running (default `http://localhost:8000`)"* — the answer was in the text
> the model itself displayed back.

**Dropped a fact present in its own cited text (incomplete, not fabricated):**
> Q: "What four things does the shared `/srv/infra` stack include?" (Note:
> the question's premise was actually off — ground truth is five components,
> not four — a flaw in the test question, not the app. The correct behavior
> per DocLens's own "clarify-before-assuming" design goal would have been to
> correct the premise.)
> A: "Caddy, Postgres, Redis, Qdrant" — **silently dropped Mongo**, which is
> explicitly present in the model's own cited chunk [2]: *"caddy + postgres +
> redis + **mongo** + qdrant."*

**Correctly declined (not a failure — this is the product working as
designed):**
> Q: "What must match between DocLens and Brain for the Brain API key
> authentication to work?"
> A: hedged and asked for a more specific source. Checked: none of the 5
> retrieved chunks for this query actually contained the
> `BRAIN_API_KEY (shared w/ DocLens)` statement (it lives in a file that
> wasn't part of this test's 4-document ingestion set) — this is a genuine
> retrieval-scope gap, not a model failure, and declining rather than
> guessing is exactly the "clarify-before-assuming" behavior the product's
> system prompt is designed to produce.

### Interpretation

The 18% hallucination rate reflects the **3B-parameter local model's**
reasoning quality on a well-retrieved context, not a retrieval or DocLens
pipeline defect — in 4 of the 5 failures, the correct chunk was retrieved and
even directly quoted in the response the model itself produced; the model
simply didn't extract/use it correctly. Retrieval quality (right chunk, right
rank) was strong across the whole batch: `retrieved_count` was always 5, and
manual review found the top-ranked chunk was topically on-point in all 28
cases. The one real DocLens/Brain-side finding is structural, not
model-quality: **the `grounded` field doesn't measure what its name implies**,
and nothing here should be read as "DocLens hallucinates 18% of the time" —
that number is specific to this small free model on this batch.

## 7. Production usage (re-checked, not assumed unchanged)

Re-checked read-only via SSH, same method as the prior report (a script
executed *inside* the `doclens-backend` container reading `MONGO_URI` from
its own process environment — never seen or printed by this session):

| Metric | Value |
|---|---|
| `doclens_threads` | 0 |
| `doclens_messages` | 0 |
| `doclens_documents` | 0 |
| Distinct users (by thread) | 0 |
| Content-route hits (`POST /chat`, `/resources`, `/ingest`) in last 30 days | 0 |
| Container running since | 2026-07-26T05:57:09Z (~3 weeks) |

**Unchanged from the prior report.** Production DocLens has been live and
reachable for about three weeks and has still not processed a single real
chat or document upload.

## 8. Cleanup verification

All 4 ingested test documents and all 29 chat threads created during the
latency/groundedness batch (a fresh thread per question) were deleted through
the app's own API (`DELETE /resources/{doc_id}?user_id=...`,
`DELETE /threads/{thread_id}?user_id=...` — all returned `200`). Local Mongo
counts after cleanup:

```json
{"threads": 0, "messages": 0, "documents": 0}
```

This matches the fresh `doclens-dev-mongo` container's actual starting state
(0/0/0 — the container was created fresh this session, so there was no prior
local baseline to preserve, unlike the previous session's Atlas-backed
environment which had a pre-existing 3/6/2 baseline).

## 9. Open items for a future session

- Persist `retrieve_ms`/`generate_ms`/`total_ms` on the assistant message row
  so future latency checks are a Mongo query, not a live reproduction.
- The `grounded: bool(chunks)` field is misleading by name — consider either
  renaming it (e.g. `retrieved: bool` ) or implementing an actual
  faithfulness check if a "grounded" signal is meant to be trustworthy
  downstream (e.g. surfaced in the UI).
- Seed real production usage — 3 weeks live with zero real chats means there
  is still no real citation data to audit outside of a synthetic test batch
  like this one.
- Consider re-running the same 28-question batch against a frontier BYOK
  model (GPT-4o-mini / Claude Haiku) to get a groundedness number that
  reflects what most real users will actually experience, not the
  zero-cost local-model floor measured here.
