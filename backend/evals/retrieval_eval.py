"""Retrieval-only eval (no LLM, free, ~1 min): does the evidence reach the model?

Ingests the corpus straight into a scratch Brain collection in two ways — plain (what DocLens
did originally) and with contextual title headers — caches Brain's reranked candidates for every
case, then scores selection strategies offline:

  ctx_recall@K   share of answerable cases whose required facts are ALL inside the top-K chunks
  top-score gap  rerank score of the best chunk for answerable vs off-topic/unanswerable cases
                 (this is what the "no evidence -> don't call the LLM" gate is calibrated on)

Gold evidence is derived from each case's `inc` groups: a group counts only if one of its
alternatives literally occurs in the corpus (words like "not"/"no" that only the *answer* would
contain are ignored). Calibrate only on --split dev; report test.
"""
from __future__ import annotations

import argparse, json, os, statistics, sys, uuid
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from run_eval import contains, norm  # noqa: E402

HERE = Path(__file__).parent
BRAIN = os.getenv("BRAIN_URL", "http://localhost:8000")
KEY = os.getenv("BRAIN_API_KEY", "")
H = {"Authorization": f"Bearer {KEY}"}
APP = "doclens_retr_eval"


def brain(path, **kw):
    r = httpx.post(f"{BRAIN}{path}", headers=H, timeout=300, **kw)
    r.raise_for_status()
    return r.json()


def ingest(spec, ns, titled):
    ids = {}
    for fn in spec["corpus"]:
        data = (HERE / "corpus" / fn).read_bytes()
        ex = httpx.post(f"{BRAIN}/v1/extract", headers=H, files={"file": (fn, data)}, data={"ingest": "false"}, timeout=300)
        ex.raise_for_status()
        did = str(uuid.uuid4()); ids[did] = fn
        body = {"app_name": APP, "doc_id": did, "namespace": ns, "text": ex.json()["text"], "dedup": False}
        if titled:
            body["title"] = Path(fn).stem.replace("_", " ")
        brain("/v1/ingest", json=body)
    for rel in spec.get("distractors", []):
        f = (HERE.parent / rel).resolve()
        if f.exists():
            ex = httpx.post(f"{BRAIN}/v1/extract", headers=H, files={"file": (f.name, f.read_bytes())}, data={"ingest": "false"}, timeout=300)
            ex.raise_for_status()
            body = {"app_name": APP, "doc_id": str(uuid.uuid4()), "namespace": ns, "text": ex.json()["text"], "dedup": False}
            if titled:
                body["title"] = f.stem
            brain("/v1/ingest", json=body)
    return ids


def candidates(case, ns, k, n):
    q = case["question"]
    if case["prior"]:
        q = f'{case["prior"][-1]} {q}'
    d = brain("/v1/retrieve", json={"app_name": APP, "query": q, "namespace": ns, "top_k": k, "top_n": n})
    return d["chunks"]


def gold_groups(case, corpus_text):
    return [g for g in case["inc"] if any(norm(a).strip() in corpus_text or contains(corpus_text, a) for a in g)]


def recall(chunks, groups):
    text = "\n".join(c["text"] for c in chunks)
    return all(any(contains(text, a) for a in g) for g in groups)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--top-k", type=int, default=40)
    ap.add_argument("--top-n", type=int, default=20)
    args = ap.parse_args()
    spec = json.loads((HERE / "cases.json").read_text())
    corpus_text = norm("\n".join((HERE / "corpus" / f).read_text() for f in spec["corpus"] if f.endswith(".md")) +
                       "\n" + "\n".join((HERE / "corpus" / f).read_text() for f in ("q3_financial_report.md", "kestrel_postmortem.md")))
    cases = [c for c in spec["cases"] if args.split in ("all", c["split"])]
    for titled in (False, True):
        ns = f"retr-{uuid.uuid4().hex[:8]}"
        ids = ingest(spec, ns, titled)
        ans_cases = [c for c in cases if c["expect"] == "answer"]
        cache = {c["id"]: candidates(c, ns, args.top_k, args.top_n) for c in cases}
        print(f"\n=== {'TITLED (contextual headers)' if titled else 'PLAIN (original ingest)'} · split={args.split} · {len(ans_cases)} answerable cases")
        for k in (3, 4, 5, 6, 8, 10, 14, 20):
            ok = [recall(cache[c["id"]][:k], gold_groups(c, corpus_text)) for c in ans_cases]
            print(f"  ctx_recall@{k:<2} {100*sum(ok)/len(ok):5.1f}%")
        miss = [c["id"] for c in ans_cases if not recall(cache[c["id"]][:8], gold_groups(c, corpus_text))]
        print("  missed@8:", miss)
        top = lambda cs: [cache[c["id"]][0]["rerank_score"] for c in cs if cache[c["id"]]]
        a = sorted(top(ans_cases))
        off = sorted(top([c for c in cases if c["expect"] == "abstain"]))
        print(f"  top rerank score — answerable: min {a[0]:.2f} p10 {a[len(a)//10]:.2f} median {statistics.median(a):.2f}")
        print("  top rerank score — unanswerable:", [round(x, 1) for x in off])
        (HERE / "results" / f"retrieval_cache_{'titled' if titled else 'plain'}.json").write_text(json.dumps(cache))
        brain("/v1/delete", json={"app_name": APP, "namespace": ns})


if __name__ == "__main__":
    main()
