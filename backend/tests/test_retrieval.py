from app import retrieval, runtime
from app.config import settings


def chunk(text, score, doc="d"):
    return {"doc_id": doc, "text": text, "rerank_score": score}


def test_needs_rewrite_only_for_context_dependent_messages():
    hist = [{"role": "user", "content": "What is the Pro plan limit?"}, {"role": "assistant", "content": "600 per minute."}]
    assert retrieval.needs_rewrite("And Enterprise?", hist)
    assert retrieval.needs_rewrite("How many of those can I carry over?", hist)
    assert not retrieval.needs_rewrite("How long until an Aurora API key expires?", hist)
    assert retrieval.needs_rewrite("Why?", hist)
    assert not retrieval.needs_rewrite("And Enterprise?", [])  # nothing to resolve against


def test_compound_detection():
    assert retrieval.looks_compound("When was Brightline approved and what is its annual contract value?")
    assert retrieval.looks_compound("What is the limit? And the burst?")
    assert not retrieval.looks_compound("What is the Pro plan rate limit per minute?")


def test_summary_detection():
    assert retrieval.is_summary_request("Summarize the vendor notes")
    assert retrieval.is_summary_request("what is this document about?")
    assert not retrieval.is_summary_request("What is the PTO policy?")


def test_select_keeps_chunks_within_margin_and_caps(monkeypatch):
    runtime.current().retrieval.score_margin = (5.0)
    runtime.current().retrieval.max_chunks = (3)
    monkeypatch.setattr(settings, "context_min_chunks", 1)
    cands = [chunk("a", 9), chunk("b", 8), chunk("c", 7), chunk("d", 6), chunk("far", -3)]
    out = retrieval.select([cands], ["q"])
    assert [c["text"] for c in out] == ["a", "b", "c"]


def test_select_always_returns_min_chunks_and_unions_subqueries(monkeypatch):
    runtime.current().retrieval.score_margin = (1.0)
    runtime.current().retrieval.max_chunks = (4)
    monkeypatch.setattr(settings, "context_min_chunks", 2)
    q1 = [chunk("x1", 9), chunk("x2", 2), chunk("x3", 1)]
    q2 = [chunk("y1", 7), chunk("y2", 6)]
    out = retrieval.select([q1, q2], ["q1", "q2"])
    texts = {c["text"] for c in out}
    assert {"x1", "x2", "y1", "y2"} <= texts  # each sub-question keeps at least its minimum evidence


def test_compound_split_keeps_original_question(monkeypatch):
    from app import brain_client

    monkeypatch.setattr(brain_client, "generate", lambda **kw: {"text": "trial location\nnumber of trial sites"})
    q = "Where was the trial run and at how many sites?"
    queries, info = retrieval.plan_queries(q, [], {"provider": "x"})
    assert queries[0] == q and "number of trial sites" in queries and info["rewritten"]


def test_followup_rewrite_replaces_ambiguous_question(monkeypatch):
    from app import brain_client

    monkeypatch.setattr(brain_client, "generate", lambda **kw: {"text": "Enterprise plan rate limit"})
    hist = [{"role": "user", "content": "What is the Pro plan limit?"}, {"role": "assistant", "content": "600 per minute."}]
    queries, _ = retrieval.plan_queries("And Enterprise?", hist, {"provider": "x"})
    assert queries == ["Enterprise plan rate limit"]
