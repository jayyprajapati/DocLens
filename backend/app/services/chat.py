"""Chat orchestration: the DocLens RAG flow.

Per turn:  screen the message (guardrails) → resolve the chat → scope documents (global ∪ this
chat) → plan queries (rewrite follow-ups / split compound questions only when needed) →
retrieve + select context from Brain → *evidence gate* (nothing on topic ⇒ "not found",
no LLM call) → grounded generation (the model quotes its evidence, then answers) →
verification (quotes must exist in the sources, numbers must be supported, citations are
repaired) → persist → respond with only the sources the answer actually used.

Brain stays stateless — DocLens supplies the conversation. The eval harness in ``evals/``
measures every stage of this pipeline end to end; run it after any change here.
"""
from __future__ import annotations

import logging
import re
import time

from .. import brain_client, runtime
from ..config import settings
from ..grounding import (
    best_sources,
    cited_numbers,
    ensure_markers,
    parse_model_output,
    repair_citations,
    unsupported_numbers,
    verify_evidence,
    quote_support,
)
from ..guardrails import (
    GREETING_REPLY,
    REFUSAL_REPLY,
    leaks_system_prompt,
    normalize_text,
    sanitize_answer,
    screen_query,
)
from ..prompts import (
    NO_DOCS_REPLY,
    NOT_FOUND_REPLY,
    answer_system,
    build_user_prompt,
    clean_answer_text,
)
from .. import answerability, retrieval
from . import documents, threads

logger = logging.getLogger("doclens.chat")
_CITE_RE = re.compile(r"\[(\d+)\]")


def build_llm(provider: str, api_key: str, model: str, fallback_model: str | None = None) -> dict:
    """Assemble Brain's ``llm`` override. The key is always forwarded — there is no fallback to
    Brain's own credentials (hosted mode passes the server's own Ollama key explicitly)."""
    llm: dict = {"provider": provider, "api_key": api_key}
    if model:
        llm["model"] = model
    if fallback_model and fallback_model != model:
        llm["_fallback"] = fallback_model
    return llm


def _citation_payload(i: int, chunk: dict, fname: str, quote: str | None) -> dict:
    heading = (chunk.get("heading") or "").strip()
    return {
        "index": i,
        "section": heading or fname,
        "filename": fname,
        "doc_id": chunk.get("doc_id", ""),
        "page": None,
        "score": chunk.get("rerank_score", chunk.get("score")),
        "text": chunk.get("text", ""),
        "quote": quote,
    }


def _cite(answer: str, used: list[int], chunks: list[dict], filename_for: dict[str, str],
          quotes: dict[int, str] | None = None) -> tuple[str, list[dict]]:
    """Renumber the cited sources 1..k in order of first use, merging sources that are the same
    section of the same document (neighbouring chunks) into one citation — otherwise the user
    sees "handbook.pdf · Leave" listed twice. ``sources[n-1]`` always matches marker ``[n]``."""
    quotes = quotes or {}
    groups: list[list[int]] = []
    where: dict[tuple, int] = {}
    for n in used:
        c = chunks[n - 1]
        key = (c.get("doc_id", ""), (c.get("heading") or "").strip().lower())
        if key in where:
            groups[where[key]].append(n)
        else:
            where[key] = len(groups)
            groups.append([n])
    mapping = {n: gi for gi, g in enumerate(groups, start=1) for n in g}
    answer = _CITE_RE.sub(lambda m: f"[{mapping[int(m.group(1))]}]" if int(m.group(1)) in mapping else "", answer)
    answer = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", answer)
    citations = []
    for gi, g in enumerate(groups, start=1):
        parts = sorted((chunks[n - 1] for n in g), key=lambda c: c.get("chunk_index") or 0)
        merged = dict(parts[0])
        merged["text"] = "\n\n…\n\n".join((p.get("text") or "").strip() for p in parts)
        quote = next((quotes[n] for n in g if quotes.get(n)), None)
        citations.append(_citation_payload(gi, merged, filename_for.get(merged.get("doc_id", ""), "document"), quote))
    return answer, citations


def _finish(
    *, thread_id: str, user_id: str, is_new_thread: bool, query: str, answer: str, citations: list[dict],
    grounded: bool, abstained: bool, meta: dict, t_start: float, blocked: bool = False,
) -> dict:
    meta["total_ms"] = round((time.perf_counter() - t_start) * 1000)
    threads.add_message(thread_id, user_id, "assistant", answer, citations, meta={**meta, "abstained": abstained, "grounded": grounded})
    threads.touch_thread(user_id, thread_id, inc_messages=2, title=threads.derive_title(query) if is_new_thread else None)
    return {
        "answer": answer,
        "citations": citations,
        "thread_id": thread_id,
        "grounded": grounded,
        "abstained": abstained,
        "blocked": blocked,
        "meta": meta,
    }


def _not_found_text(model_text: str) -> str:
    """What to tell the user when the answer isn't in their documents: the model's own
    explanation of what the documents do/don't say, or a generic fallback."""
    text = (model_text or "").strip()
    return text if len(text) >= 12 else NOT_FOUND_REPLY


def _generate(system: str, prompt: str, llm: dict) -> str:
    acfg = runtime.current().answer
    out = brain_client.generate(
        system=system,
        prompt=prompt,
        llm=llm,
        max_tokens=acfg.max_tokens,
        temperature=acfg.temperature,
        reasoning=acfg.reasoning or None,
    )
    return out.get("text") or ""


def run_chat(
    *,
    user_id: str,
    query: str,
    provider: str,
    api_key: str,
    model: str,
    thread_id: str | None,
    explicit_doc_ids: list[str] | None,
    fallback_model: str | None = None,
) -> dict:
    llm = build_llm(provider, api_key, model, fallback_model)
    cfg = runtime.current()
    system = answer_system(cfg.answer.style)
    t_start = time.perf_counter()
    query = normalize_text(query).strip()[: settings.max_query_chars]

    # 1. Resolve / create the chat session.
    is_new_thread = not thread_id or threads.get_thread_raw(user_id, thread_id) is None
    if is_new_thread:
        thread = threads.create_thread(user_id, title=threads.derive_title(query))
        thread_id = thread["id"]

    # 2. Capture context BEFORE recording this turn, then record the user message.
    history = threads.recent_messages(thread_id, limit=6)
    threads.add_message(thread_id, user_id, "user", query)
    meta: dict = {"retrieved_count": 0, "retrieve_ms": 0, "generate_ms": 0, "guardrails": [], "model": model, "style": cfg.answer.style}
    common = dict(thread_id=thread_id, user_id=user_id, is_new_thread=is_new_thread, query=query, t_start=t_start)

    # 3. Input guardrails (no LLM, no retrieval for clear attacks / small talk).
    screen = screen_query(query)
    if screen.blocked:
        meta["guardrails"] = [f"input:{c}" for c in screen.categories]
        logger.warning("blocked query categories=%s user=%s", screen.categories, user_id[:8])
        return _finish(**common, answer=REFUSAL_REPLY, citations=[], grounded=False, abstained=True, meta=meta, blocked=True)
    if screen.smalltalk:
        return _finish(**common, answer=GREETING_REPLY, citations=[], grounded=False, abstained=False, meta=meta)

    # 4. Scope: global docs (every chat) ∪ this chat's docs — or an explicit pick (only the
    #    caller's own documents are ever honoured).
    own = set(documents.global_doc_ids(user_id)) | set(documents.thread_doc_ids(user_id, thread_id))
    if explicit_doc_ids:
        scope_ids = [d for d in list(dict.fromkeys(explicit_doc_ids))[:50] if d in own or documents.owns(user_id, d)]
    else:
        scope_ids = list(own)
    if not scope_ids:
        return _finish(**common, answer=NO_DOCS_REPLY, citations=[], grounded=False, abstained=True, meta=meta)

    # 5. Plan queries + retrieve + select context.
    queries, plan = retrieval.plan_queries(query, history, llm)
    meta["queries"] = queries
    meta["rewrite_ms"] = plan.get("llm_ms", 0)
    r = retrieval.retrieve_context(
        queries, user_id, scope_ids,
        summary=retrieval.is_summary_request(query), broad=retrieval.is_broad_request(query),
    )
    meta.update(retrieved_count=len(r.chunks), retrieve_ms=r.ms, top_score=r.top_score, candidates=r.candidates)

    # 6. Evidence gate: nothing on topic in the user's documents ⇒ don't spend an LLM call
    #    (and don't let the model improvise).
    if not r.chunks or r.top_score is None or r.top_score < cfg.retrieval.evidence_gate:
        meta["guardrails"].append("gate:no_evidence")
        return _finish(**common, answer=NOT_FOUND_REPLY, citations=[], grounded=False, abstained=True, meta=meta)

    # 7. Grounded generation with the user's BYOK model.
    filename_for = documents.filename_map(user_id, [c.get("doc_id", "") for c in r.chunks])
    prompt, shown = build_user_prompt(query, r.chunks, filename_for, history)
    t1 = time.perf_counter()
    raw = _generate(system, prompt, llm)
    parsed = parse_model_output(clean_answer_text(raw))
    if settings.debug_trace:
        meta["trace"] = {"raw": raw[:4000], "sources": [x[:240] for x in shown]}

    # 8. Verification (+ one corrective retry when numbers aren't supported by the sources).
    bad = []
    if not parsed.not_found and not parsed.clarify:
        bad = unsupported_numbers(parsed.answer, shown, query)
        if bad:
            meta["guardrails"].append("verify:unsupported_numbers")
            fix = (
                prompt
                + f"\n\nYour previous draft stated these values that do not appear in the SOURCES: {', '.join(bad)}. "
                "Rewrite the reply using only values that appear in the SOURCES (or simple arithmetic on them). "
                "If the SOURCES do not state the answer, reply NOT_FOUND."
            )
            parsed = parse_model_output(clean_answer_text(_generate(system, fix, llm)))
            bad = [] if (parsed.not_found or parsed.clarify) else unsupported_numbers(parsed.answer, shown, query)
    meta["generate_ms"] = round((time.perf_counter() - t1) * 1000)
    if llm.get("_fell_back"):
        meta["model"] = llm["_fallback"]
        meta["guardrails"].append("model:fallback")

    answer, flags = sanitize_answer(parsed.answer, "\n".join(shown))
    meta["guardrails"] += [f"output:{f}" for f in flags]
    if leaks_system_prompt(answer, system):
        meta["guardrails"].append("output:system_prompt_leak")
        return _finish(**common, answer=REFUSAL_REPLY, citations=[], grounded=False, abstained=True, meta=meta, blocked=True)

    if parsed.not_found or bad:
        text = _not_found_text(answer) if parsed.not_found else (
            "I found related text in your documents, but I couldn't verify the specific figure you asked about, so I won't guess."
        )
        # A "not found" that states what the documents DO say (a correction, a status) cites it.
        cites: list[dict] = []
        if parsed.not_found and not cited_numbers(text) and len(text) >= 12:
            # the model corrected a premise or stated the closest fact but forgot the marker
            near = best_sources(text, shown, k=1, floor=0.35)
            if near:
                text = ensure_markers(text, near)
        if parsed.not_found and cited_numbers(text):
            text = repair_citations(text, shown)
            used_nf = [n for n in cited_numbers(text) if 1 <= n <= len(r.chunks)]
            text, cites = _cite(text, used_nf, r.chunks, filename_for)
        return _finish(**common, answer=text, citations=cites, grounded=False, abstained=True, meta=meta)

    if parsed.clarify:
        return _finish(**common, answer=answer, citations=[], grounded=False, abstained=False, meta=meta)

    # Second opinion: does the cited text itself answer the question, or did the model stretch?
    if not parsed.clarify and answerability.should_verify(query, answer, [q for _, q in parsed.evidence]):
        t2 = time.perf_counter()
        cited_idx = [n for n in cited_numbers(answer) if 1 <= n <= len(shown)] or [
            n for n, _, _ in verify_evidence(parsed.evidence, shown)
        ] or list(range(1, min(len(shown), 3) + 1))
        labels = [
            f"{filename_for.get(r.chunks[n - 1].get('doc_id', ''), 'document')} — {(r.chunks[n - 1].get('heading') or '').strip()}".rstrip(" —")
            for n in cited_idx
        ]
        ok, why = answerability.check(query, answer, [shown[n - 1] for n in cited_idx], llm, labels)
        meta["verify_ms"] = round((time.perf_counter() - t2) * 1000)
        if not ok:
            # Decline, but show the closest evidence (with citations) so the user can see what
            # the documents do say and judge for themselves.
            meta["guardrails"].append("verify:unsupported_answer")
            text = ("I couldn't find a direct answer to that in your documents. " + why).strip()
            cites = []
            if cited_idx:
                text, cites = _cite(text + " " + "".join(f"[{n}]" for n in cited_idx), cited_idx, r.chunks, filename_for)
            return _finish(**common, answer=text, citations=cites, grounded=False, abstained=True, meta=meta)

    # Groundedness: every claim must trace to a verified quote, or the answer must itself be
    # lexically supported by the sources (models sometimes skip the evidence block).
    verified = verify_evidence(parsed.evidence, shown)
    meta["evidence"] = {"quoted": len(parsed.evidence), "verified": len(verified)}
    if not verified:
        support = max((_answer_support(answer, s) for s in shown), default=0.0)
        meta["evidence"]["answer_support"] = round(support, 2)
        if support < 0.45:
            meta["guardrails"].append("verify:ungrounded")
            return _finish(**common, answer=NOT_FOUND_REPLY, citations=[], grounded=False, abstained=True, meta=meta)

    # 9. Citations: repair wrong markers, make sure there are some, keep only what was used.
    answer = repair_citations(answer, shown, trusted={n for n, _, _ in verified})
    if not cited_numbers(answer):
        by_evidence = sorted({n for n, _, _ in verified}, key=lambda n: -max(s for m, _, s in verified if m == n))
        answer = ensure_markers(answer, by_evidence or best_sources(answer, shown, k=1))
    used = [n for n in cited_numbers(answer) if 1 <= n <= len(r.chunks)]
    quotes: dict[int, str] = {}
    for n, q, _ in verified:
        quotes.setdefault(n, q)
    answer, citations = _cite(answer, used, r.chunks, filename_for, quotes)
    return _finish(**common, answer=answer, citations=citations, grounded=bool(citations), abstained=False, meta=meta)


def _answer_support(answer: str, source: str) -> float:
    return quote_support(re.sub(r"\[\d+\]", "", answer), source)
