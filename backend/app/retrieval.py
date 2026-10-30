"""Retrieval planning and context selection (DocLens side of the RAG pipeline).

Brain gives us vector search + a cross-encoder rerank. On top of that DocLens

  * rewrites follow-ups into standalone queries (only when the message needs it — a
    self-contained question skips the extra LLM call) and splits compound questions so
    every part is retrieved for,
  * fetches a *wide* reranked pool per query in parallel and merges them,
  * applies a relative score margin so the model sees the few chunks that matter instead of
    a fixed top-N dump,
  * exposes the best rerank score so chat.py can refuse to call the LLM when nothing in the
    user's documents is on topic.
"""
from __future__ import annotations

import math
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import brain_client, runtime
from .config import settings
from .prompts import CONTEXTUALIZE_SYSTEM

_WORD = re.compile(r"[a-z0-9][a-z0-9._@%-]*", re.IGNORECASE)
_STOP = frozenset(
    "a an the and or of to in on for with by from at as is are was were be been it its this that these those "
    "there their they them he she his her you your we our i me my do does did can could should would will may "
    "might has have had than then so if but also about which who whom what when where how why per each any all "
    "some more most other such only into over under between within across tell give show list please explain "
    "many much long often".split()
)
_REFERENCE = re.compile(
    r"\b(it|its|they|them|their|this|that|those|these|he|she|his|her|the (first|second|third|last|other|latter|former|same|one|ones)|"
    r"(first|second|third|last|other|former|latter) one|such|there)\b",
    re.IGNORECASE,
)
_ELLIPSIS_START = re.compile(r"^\s*(and|but|also|what about|how about|so|then|why|how come|more|else|anything else|ok(ay)?[, ]|and then)\b", re.IGNORECASE)
_WH = re.compile(r"\b(what|when|where|who|whom|which|why|how|does|do|is|are|can|will|did|was)\b", re.IGNORECASE)
_SUMMARY = re.compile(
    r"\b(summar(y|ise|ize)|overview|tl;?dr|key (points|takeaways|findings)|main (points|ideas|takeaways)|what is (this|the) (doc|document|file|report|paper|pdf)|"
    r"what('s| is) (it|this|the (doc|document|file|report)) about|tell me (about|everything)|walk me through|give me the gist)\b",
    re.IGNORECASE,
)


def keywords(text: str) -> list[str]:
    return [w.strip(".-_@") for w in _WORD.findall(text.lower()) if w.strip(".-_@") and w not in _STOP and len(w) > 1]


_BROAD = re.compile(
    r"\b(explain|describe|compare|comparison|difference|differences|walk me through|how (does|do|did|is|are|can|should)|"
    r"why|pros and cons|advantages|steps|process|elaborate|in detail|everything about|more about)\b",
    re.IGNORECASE,
)


def is_summary_request(query: str) -> bool:
    return bool(_SUMMARY.search(query))


def is_broad_request(query: str) -> bool:
    """Explain / compare / how-why questions: worth a little more context than a lookup."""
    return bool(_BROAD.search(query))


def needs_rewrite(query: str, history: list[dict]) -> bool:
    """A rewrite is only worth an LLM call when the message leans on the conversation."""
    if not any(m.get("content") for m in history):
        return False
    # leans on the conversation: a pronoun/ordinal reference, an elliptical opener ("and …",
    # "what about …"), or too few distinctive words to search on its own
    return bool(_REFERENCE.search(query)) or bool(_ELLIPSIS_START.match(query)) or len(set(keywords(query))) < 3


def looks_compound(query: str) -> bool:
    """Two or more distinct questions in one message ("when was X approved and what is its value?")."""
    if query.count("?") >= 2:
        return True
    return len(_WH.findall(query)) >= 3 and bool(re.search(r"\b(and|also|as well as|plus)\b", query, re.IGNORECASE)) and len(query.split()) >= 9


def _clean_query(line: str) -> str:
    q = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line)
    return q.strip().strip("\"'`").strip()[:300]


def plan_queries(query: str, history: list[dict], llm: dict) -> tuple[list[str], dict]:
    """Return (queries, info). Never fatal: any failure falls back to the raw query, plus the
    previous user turn for short follow-ups so the topic isn't lost."""
    info = {"rewritten": False, "llm_ms": 0}
    rewrite = needs_rewrite(query, history)
    if not (rewrite or looks_compound(query)):
        return [query], info
    transcript = "\n".join(
        f"{m['role']}: {re.sub(chr(10), ' ', m['content'])[:500]}" for m in history[-6:] if m.get("content")
    ) or "(none)"
    prompt = f"Conversation so far:\n{transcript}\n\nLatest message: {query}"
    t0 = time.perf_counter()
    try:
        out = brain_client.generate(
            system=CONTEXTUALIZE_SYSTEM, prompt=prompt, llm=llm, max_tokens=700, temperature=0.0,
            reasoning=settings.rewrite_reasoning or None,
        )
        lines = [_clean_query(x) for x in (out.get("text") or "").splitlines()]
        queries = list(dict.fromkeys(q for q in lines if q))[:3]
        info["llm_ms"] = round((time.perf_counter() - t0) * 1000)
        if queries and not rewrite:
            # a self-contained compound question: the split parts help each sub-question, but the
            # user's own wording is often the best vector query (a paraphrase can drop the passage
            # out of the candidate pool entirely), so search with it too
            queries = list(dict.fromkeys([query[:300]] + queries))[:4]
        if queries:
            info["rewritten"] = True
            return queries, info
    except brain_client.BrainError:
        info["llm_ms"] = round((time.perf_counter() - t0) * 1000)
    if rewrite:
        last_user = next((m["content"] for m in reversed(history) if m.get("role") == "user" and m.get("content")), "")
        if last_user:
            return [f"{last_user} {query}"[:400]], info
    return [query], info


@dataclass
class Retrieval:
    chunks: list[dict] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    top_score: float | None = None
    candidates: int = 0
    ms: int = 0


def _key(c: dict) -> str:
    # content key, not (doc, text): the same passage from two copies of a document (re-exported
    # file, or uploaded both as a resource and in a chat) is one source, not two
    return re.sub(r"\W+", " ", (c.get("text") or "").lower()).strip()[:240]


def _rr(c: dict) -> float:
    s = c.get("rerank_score")
    return float(s) if s is not None else -99.0


def gather(queries: list[str], namespace: str, doc_ids: list[str]) -> list[list[dict]]:
    """Retrieve for every query in parallel; one reranked list per query."""

    def one(q: str) -> list[dict]:
        return brain_client.retrieve(
            query=q, namespace=namespace, doc_ids=doc_ids, top_k=settings.retrieve_top_k, top_n=settings.retrieve_top_n
        )

    if len(queries) == 1:
        return [one(queries[0])]
    with ThreadPoolExecutor(len(queries)) as ex:
        return list(ex.map(one, queries))


def select(per_query: list[list[dict]], queries: list[str], summary: bool = False, broad: bool = False) -> list[dict]:
    """Pick the few chunks worth the model's attention.

    Per query: keep chunks within ``retrieval.score_margin`` of that query's best (at least
    ``context_min_chunks``, at most ``retrieval.max_chunks``); then union across queries, so each
    part of a compound question keeps its own evidence. Summary requests get a wider window,
    explain/compare questions a slightly wider one."""
    rcfg = runtime.current().retrieval
    cap = rcfg.max_chunks + (4 if summary else 2 if broad else 0)
    margin = rcfg.score_margin * (2.0 if summary else 1.0)
    chosen: dict[tuple, dict] = {}
    for q, cands in zip(queries, per_query):
        cands = sorted((dict(c) for c in cands), key=_rr, reverse=True)
        if not cands:
            continue
        best = _rr(cands[0])
        keep = [c for c in cands if _rr(c) >= best - margin][:cap]
        if len(keep) < settings.context_min_chunks:
            keep = cands[: settings.context_min_chunks]
        share = max(settings.context_min_chunks, math.ceil(cap / len(queries))) if len(queries) > 1 else cap
        for c in keep[:share]:
            k = _key(c)
            if k not in chosen or _rr(c) > _rr(chosen[k]):
                chosen[k] = c
    out = sorted(chosen.values(), key=_rr, reverse=True)
    return out[: cap + (2 * (len(queries) - 1))]


def retrieve_context(queries: list[str], namespace: str, doc_ids: list[str], summary: bool = False, broad: bool = False) -> Retrieval:
    t0 = time.perf_counter()
    per_query = gather(queries, namespace, doc_ids)
    chunks = select(per_query, queries, summary=summary, broad=broad)
    top = max((_rr(c) for lst in per_query for c in lst), default=None)
    return Retrieval(
        chunks=chunks,
        queries=queries,
        top_score=None if top is None or top <= -98 else round(top, 2),
        candidates=sum(len(x) for x in per_query),
        ms=round((time.perf_counter() - t0) * 1000),
    )
