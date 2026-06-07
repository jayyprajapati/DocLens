"""Chat orchestration: the DocLens RAG flow.

For each turn we (1) resolve or create the chat session, (2) scope retrieval to
the user's *global* documents plus *this chat's* documents, (3) optionally rewrite
an elliptical follow-up into a standalone query, (4) retrieve grounded excerpts
from Brain, and (5) generate a grounded, cited answer with the user's BYOK model.

Brain stays stateless — DocLens passes the recent conversation as context. The
answer prompt enforces "clarify before assuming": when the sources don't actually
answer the question, the model asks for clarification instead of inventing facts.
"""
from __future__ import annotations

import time

from .. import brain_client
from ..config import settings
from ..prompts import (
    ANSWER_SYSTEM,
    CONTEXTUALIZE_SYSTEM,
    NO_DOCS_REPLY,
    build_user_prompt,
    clean_answer_text,
)
from . import documents, threads


def build_llm(provider: str, api_key: str, model: str) -> dict:
    """Assemble Brain's BYOK ``llm`` override. The key is always forwarded — there
    is no fallback to Brain's own credentials for DocLens."""
    llm: dict = {"provider": provider, "api_key": api_key}
    if model:
        llm["model"] = model
    return llm


def _contextualize(query: str, history: list[dict], llm: dict) -> str:
    """Rewrite a follow-up into a standalone retrieval query. Never fatal — falls
    back to the raw query on any error."""
    if not history:
        return query
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in history if m.get("content"))
    if not transcript:
        return query
    prompt = f"Conversation so far:\n{transcript}\n\nLatest message: {query}"
    try:
        out = brain_client.generate(
            system=CONTEXTUALIZE_SYSTEM, prompt=prompt, llm=llm, max_tokens=80, temperature=0.0
        )
        rewritten = (out.get("text") or "").strip()
        return rewritten or query
    except brain_client.BrainError:
        return query


def _citations(chunks: list[dict], filename_for: dict[str, str]) -> list[dict]:
    """Map retrieved chunks to the frontend citation shape (section/page/text).
    Index order matches the [n] markers the model was given."""
    out = []
    for i, c in enumerate(chunks, start=1):
        doc_id = c.get("doc_id", "")
        fname = filename_for.get(doc_id, "document")
        heading = (c.get("heading") or "").strip()
        out.append(
            {
                "index": i,
                "section": heading or fname,
                "filename": fname,
                "doc_id": doc_id,
                "page": None,
                "score": c.get("score"),
                "text": c.get("text", ""),
            }
        )
    return out


def run_chat(
    *,
    user_id: str,
    query: str,
    provider: str,
    api_key: str,
    model: str,
    thread_id: str | None,
    explicit_doc_ids: list[str] | None,
) -> dict:
    llm = build_llm(provider, api_key, model)

    # 1. Resolve / create the chat session.
    is_new_thread = not thread_id
    if is_new_thread:
        thread = threads.create_thread(user_id, title=threads.derive_title(query))
        thread_id = thread["id"]

    # 2. Capture context BEFORE recording this turn, then record the user message.
    history = threads.recent_messages(thread_id, limit=8)
    threads.add_message(thread_id, user_id, "user", query)

    # 3. Scope: global docs (every chat) ∪ this chat's docs — or an explicit pick.
    if explicit_doc_ids:
        scope_ids = [d for d in explicit_doc_ids if d]
    else:
        scope_ids = list(dict.fromkeys(documents.global_doc_ids(user_id) + documents.thread_doc_ids(user_id, thread_id)))

    if not scope_ids:
        threads.add_message(thread_id, user_id, "assistant", NO_DOCS_REPLY, [])
        threads.touch_thread(user_id, thread_id, inc_messages=2)
        return {
            "answer": NO_DOCS_REPLY,
            "citations": [],
            "thread_id": thread_id,
            "grounded": False,
            "meta": {"retrieved_count": 0, "retrieve_ms": 0, "generate_ms": 0},
        }

    # 4. Retrieve grounded excerpts (local embeddings; no BYOK key needed).
    search_query = _contextualize(query, history, llm)
    t0 = time.perf_counter()
    chunks = brain_client.retrieve(
        query=search_query, namespace=user_id, doc_ids=scope_ids, top_k=settings.retrieve_top_k
    )
    retrieve_ms = round((time.perf_counter() - t0) * 1000)

    # 5. Generate a grounded, cited answer with the user's BYOK model.
    filename_for = documents.filename_map(user_id, [c.get("doc_id", "") for c in chunks])
    user_prompt = build_user_prompt(query, chunks, filename_for, history)
    t1 = time.perf_counter()
    out = brain_client.generate(
        system=ANSWER_SYSTEM,
        prompt=user_prompt,
        llm=llm,
        max_tokens=settings.answer_max_tokens,
        temperature=settings.answer_temperature,
    )
    generate_ms = round((time.perf_counter() - t1) * 1000)
    answer = clean_answer_text(out.get("text") or "") or "I couldn't generate a response. Please try again."

    citations = _citations(chunks, filename_for)
    threads.add_message(thread_id, user_id, "assistant", answer, citations)
    title = threads.derive_title(query) if is_new_thread else None
    threads.touch_thread(user_id, thread_id, inc_messages=2, title=title)

    return {
        "answer": answer,
        "citations": citations,
        "thread_id": thread_id,
        "grounded": bool(chunks),
        "meta": {
            "retrieved_count": len(chunks),
            "reranked_count": len(chunks),
            "retrieve_ms": retrieve_ms,
            "generate_ms": generate_ms,
        },
    }
