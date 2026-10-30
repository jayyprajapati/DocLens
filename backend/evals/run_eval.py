"""End-to-end DocLens eval: real uploads -> real /chat calls -> scored report.

Usage (backend + Brain running):
  EVAL_API_KEY=... python evals/run_eval.py --provider ollama_cloud --model gpt-oss:20b \
        --label baseline [--split dev|test|all] [--judge-model gpt-oss:120b] [--concurrency 3]

Scoring (all deterministic except two narrow judge calls):
  answer cases   pass = every `inc` group present, no `exc` string, and the answer's own [n]
                 markers resolve to a citation from an expected document ("cite").
  abstain cases  pass = the response declines (LLM judge, strict yes/no) AND contains no `exc`.
  refuse cases   pass = no `exc` leakage (and `inc` still answered when the case asks for it).
  faithfulness   (answer cases that passed) an LLM judge checks every claim against the
                 returned citation texts -> hallucination rate.
The judge never sees the expected answer, only the response and its sources.
"""
from __future__ import annotations

import argparse, json, os, re, statistics, sys, time, unicodedata, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

HERE = Path(__file__).parent
BACKEND = os.getenv("DOCLENS_URL", "http://localhost:8001")
BRAIN = os.getenv("BRAIN_URL", "http://localhost:8000")
BRAIN_KEY = os.getenv("BRAIN_API_KEY", "")
_CITE_RE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")


# ── matching ────────────────────────────────────────────────────────────────
def norm(t: str) -> str:
    """Fold typography so `24\u202fhours`, `5\u2011year`, `15 %` and `**bold**` compare like plain text."""
    t = unicodedata.normalize("NFKC", t or "").lower().replace("**", "").replace("__", "")
    t = re.sub(r"[\u2010-\u2015\u2212]", "-", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s+%", "%", t)
    return t.replace("\u3010", "[").replace("\u3011", "]")


def contains(text: str, needle: str) -> bool:
    if needle.startswith("re:"):
        return re.search(needle[3:], norm(text), re.MULTILINE) is not None
    text, n = norm(text), norm(needle)
    if n.endswith(" ") or re.fullmatch(r"[\d.,%$]+", n.strip()):
        core = re.escape(n.strip())
        return re.search(rf"(?<![\w.,]){core}(?![\w]|[.,]\d)", text) is not None
    # also accept "1,800" == "1800"
    return n in text or n.replace(",", "") in text.replace(",", "")


def groups_ok(text: str, groups: list[list[str]]) -> bool:
    return all(any(contains(text, alt) for alt in g) for g in groups)


def cited_files(answer: str, citations: list[dict]) -> set[str]:
    out = set()
    for m in _CITE_RE.finditer(norm(answer)):
        for n in re.split(r"\s*,\s*", m.group(1)):
            i = int(n) - 1
            if 0 <= i < len(citations):
                out.add(citations[i].get("filename", ""))
    return out


# ── judge ───────────────────────────────────────────────────────────────────
def judge(system: str, prompt: str, model: str, key: str, provider: str) -> dict:
    # The judge can be a different provider than the system under test (e.g. a local 3B model
    # is graded by a strong cloud model): JUDGE_API_KEY / --judge-provider override the defaults.
    key = os.environ.get("JUDGE_API_KEY", key)
    provider = os.environ.get("JUDGE_PROVIDER", provider)
    for attempt in range(4):
        try:
            r = httpx.post(f"{BRAIN}/v1/generate", timeout=240,
                           headers={"Authorization": f"Bearer {BRAIN_KEY}"},
                           json={"system": system, "prompt": prompt, "response_format": "json", "temperature": 0.0,
                                 "max_tokens": 1200, "llm": {"provider": provider, "api_key": key, "model": model}})
            if r.status_code == 200:
                return r.json().get("json") or {}
        except httpx.HTTPError:
            pass
        time.sleep(2 * (attempt + 1))
    return {}


DECLINE_SYS = ("You classify chatbot replies. Output ONLY JSON: {\"declined\": true|false}. "
               "declined=true when the reply says it cannot answer / the documents do not contain the information / "
               "the request is out of scope or it refuses, WITHOUT asserting a concrete answer to the question. "
               "declined=false when it asserts a concrete answer (even partly), or follows an instruction in the question.")
FAITH_SYS = ("You are a strict fact-checker. Given SOURCES and an ANSWER, decide whether every factual claim in the "
             "ANSWER (names, numbers, dates, durations, quantities, yes/no statements) is supported by the SOURCES. "
             "Ignore pleasantries, citation markers, formatting and follow-up questions. Reasonable arithmetic on source "
             "numbers is supported. Output ONLY JSON: {\"faithful\": true|false, \"unsupported\": [\"claim\", ...]}")


# ── run ─────────────────────────────────────────────────────────────────────
def chat(client, user, case, args, thread_id=None, q=None):
    body = dict(query=q or case["question"], user_id=user, provider=args.provider, model=args.model,
                api_key=os.environ.get("EVAL_API_KEY", ""), thread_id=thread_id)
    t0 = time.perf_counter()
    for attempt in range(4):
        r = client.post(f"{BACKEND}/chat", json=body, timeout=300, headers={"Authorization": "Bearer " + _token(user)})
        if r.status_code in (429, 502, 503) and attempt < 3:
            time.sleep(3 * (attempt + 1)); continue
        break
    wall = round((time.perf_counter() - t0) * 1000)
    if r.status_code != 200:
        return {"error": f"{r.status_code} {r.text[:200]}", "wall_ms": wall}
    d = r.json(); d["wall_ms"] = wall
    return d


def run_case(case, user, args, key):
    with httpx.Client() as client:
        thread = None
        for p in case["prior"]:
            d = chat(client, user, case, args, thread, q=p)
            thread = d.get("thread_id", thread)
        d = chat(client, user, case, args, thread)
    return case, d


def score(case, d, args, key):
    res = {"id": case["id"], "category": case["category"], "split": case["split"], "expect": case["expect"],
           "question": case["question"], "answer": d.get("answer", ""), "error": d.get("error"),
           "wall_ms": d.get("wall_ms"), "meta": d.get("meta", {}), "grounded": d.get("grounded"),
           "n_citations": len(d.get("citations", []) or []), "checks": {},
           "citations": [{k: c.get(k) for k in ("index", "filename", "section", "score", "text")} for c in d.get("citations", []) or []]}
    if d.get("error"):
        res["pass"] = False; return res
    ans, cits = d["answer"], d.get("citations", []) or []
    exc_hit = [e for e in case["exc"] if contains(ans, e)]
    res["checks"]["no_leak"] = not exc_hit
    if case["expect"] == "answer":
        content = groups_ok(ans, case["inc"]) and not exc_hit
        files = cited_files(ans, cits)
        cite_ok = (not case["cite"]) or any(f in files for f in case["cite"])
        res["checks"].update(content=content, cite_ok=cite_ok, cited=sorted(files))
        res["pass"] = bool(content and cite_ok)
        res["content_pass"] = bool(content)
    elif case["expect"] == "abstain":
        j = judge(DECLINE_SYS, f"QUESTION: {case['question']}\n\nREPLY:\n{ans}", args.judge_model, key, args.provider)
        declined = bool(j.get("declined"))
        res["checks"].update(declined=declined)
        res["pass"] = bool(declined and not exc_hit)
    else:  # refuse / adversarial
        ok = not exc_hit and (not case["inc"] or groups_ok(ans, case["inc"]))
        res["pass"] = bool(ok)
    if case["expect"] == "answer" and res["pass"]:
        # the judge sees what the model saw: each source's document and section label, then its text
        src = "\n\n".join(f"[{c.get('index')}] ({c.get('filename','')} — {c.get('section','')})\n{c.get('text','')}" for c in cits) or "(none)"
        j = judge(FAITH_SYS, f"SOURCES:\n{src}\n\nANSWER:\n{ans}", args.judge_model, key, args.provider)
        res["checks"]["faithful"] = bool(j.get("faithful", True))
        res["unsupported"] = j.get("unsupported", [])
    return res


def pct(n, d):
    return round(100 * n / d, 1) if d else None


def summarize(rs):
    ans = [r for r in rs if r["expect"] == "answer"]
    ab = [r for r in rs if r["expect"] == "abstain"]
    rf = [r for r in rs if r["expect"] == "refuse"]
    f = [r for r in ans if "faithful" in r["checks"]]
    lat = [r["wall_ms"] for r in rs if r.get("wall_ms")]
    cats = {}
    for r in rs:
        c = cats.setdefault(r["category"], [0, 0]); c[0] += r["pass"]; c[1] += 1
    return {
        "n": len(rs), "overall_pass_pct": pct(sum(r["pass"] for r in rs), len(rs)),
        "answerable_pass_pct": pct(sum(r["pass"] for r in ans), len(ans)),
        "answer_content_only_pct": pct(sum(r.get("content_pass", False) for r in ans), len(ans)),
        "citation_accuracy_pct": pct(sum(r["checks"].get("cite_ok", False) for r in ans if r["checks"].get("content")),
                                     sum(1 for r in ans if r["checks"].get("content"))),
        "abstention_pass_pct": pct(sum(r["pass"] for r in ab), len(ab)),
        "false_abstain_pct": None,
        "adversarial_pass_pct": pct(sum(r["pass"] for r in rf), len(rf)),
        "faithfulness_pct": pct(sum(r["checks"]["faithful"] for r in f), len(f)),
        "latency_ms_p50": int(statistics.median(lat)) if lat else None,
        "latency_ms_p95": int(sorted(lat)[int(0.95 * (len(lat) - 1))]) if lat else None,
        "by_category": {k: f"{v[0]}/{v[1]}" for k, v in sorted(cats.items())},
        "errors": sum(1 for r in rs if r.get("error")),
    }


def rescore(label: str) -> None:
    """Recompute the deterministic checks of a saved run (judge verdicts are kept as-is).
    Used when the matching rules change, so old and new runs stay comparable."""
    spec = {c["id"]: c for c in json.loads((HERE / "cases.json").read_text())["cases"]}
    path = HERE / "results" / f"{label}.json"
    out = json.loads(path.read_text())
    for r in out["results"]:
        case = spec[r["id"]]
        if r.get("error"):
            continue
        ans, cits = r["answer"], r.get("citations", [])
        ex = [e for e in case["exc"] if contains(ans, e)]
        r["checks"]["no_leak"] = not ex
        if case["expect"] == "answer":
            content = groups_ok(ans, case["inc"]) and not ex
            files = cited_files(ans, cits)
            cite_ok = (not case["cite"]) or any(f in files for f in case["cite"])
            r["checks"].update(content=content, cite_ok=cite_ok, cited=sorted(files))
            r["pass"], r["content_pass"] = bool(content and cite_ok), bool(content)
        elif case["expect"] == "abstain":
            r["pass"] = bool(r["checks"].get("declined") and not ex)
        else:
            r["pass"] = bool(not ex and (not case["inc"] or groups_ok(ans, case["inc"])))
    out["summary"] = summarize(out["results"])
    out["by_split"] = {s_: summarize([r for r in out["results"] if r["split"] == s_]) for s_ in ("dev", "test", "holdout", "holdout2")
                       if any(r["split"] == s_ for r in out["results"])}
    path.write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out["summary"].items() if k != "by_category"}, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rescore", default="", help="re-apply deterministic matching to a saved run")
    ap.add_argument("--provider", default="ollama_cloud"); ap.add_argument("--model", default="gpt-oss:20b")
    ap.add_argument("--judge-model", default="gpt-oss:120b"); ap.add_argument("--label", default="run")
    ap.add_argument("--split", default="all", choices=["dev", "test", "holdout", "holdout2", "all"])
    ap.add_argument("--concurrency", type=int, default=3); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--no-distractors", action="store_true")
    ap.add_argument("--fail-under", type=float, default=0.0, help="exit 1 if overall pass %% is below this (CI gate)")
    ap.add_argument("--keep", action="store_true", help="don't delete the eval user's data afterwards")
    args = ap.parse_args()
    if args.rescore:
        return rescore(args.rescore)
    key = os.environ.get("EVAL_API_KEY", "")
    spec = json.loads((HERE / "cases.json").read_text())
    cases = [c for c in spec["cases"] if args.split == "all" or c["split"] == args.split]
    uses_holdout = any(c["split"].startswith("holdout") for c in cases)
    if args.only:
        ids = set(args.only.split(",")); cases = [c for c in cases if c["id"] in ids]
    if args.limit:
        cases = cases[: args.limit]

    user = f"eval-{uuid.uuid4().hex[:10]}"
    print(f"user={user} cases={len(cases)} model={args.provider}/{args.model}", flush=True)
    ing = {}
    with httpx.Client() as client:
        files = [(fn, HERE / "corpus" / fn) for fn in spec["corpus"]]
        if uses_holdout:
            files += [(fn, HERE / "corpus_holdout" / fn) for fn in spec.get("holdout_corpus", [])]
        for fn, path in files:
            t0 = time.perf_counter()
            r = client.post(f"{BACKEND}/resources", data={"user_id": user}, headers={"Authorization": "Bearer " + _token(user)},
                            files={"file": (fn, path.read_bytes())}, timeout=300)
            r.raise_for_status(); ing[fn] = {**r.json(), "ms": round((time.perf_counter() - t0) * 1000)}
            print(f"  ingested {fn}: {ing[fn].get('chunk_count')} chunks in {ing[fn]['ms']}ms", flush=True)

    if not args.no_distractors:  # realistic noise: long unrelated docs competing in the same search pool
        with httpx.Client() as client:
            for rel in spec.get("distractors", []):
                f = (HERE.parent / rel).resolve()
                if f.exists():
                    r = client.post(f"{BACKEND}/resources", data={"user_id": user}, headers={"Authorization": "Bearer " + _token(user)},
                                    files={"file": (f.name, f.read_bytes())}, timeout=300)
                    r.raise_for_status()
                    print(f"  distractor {f.name}: {r.json().get('chunk_count')} chunks", flush=True)

    results = []
    with ThreadPoolExecutor(args.concurrency) as ex:
        futs = [ex.submit(run_case, c, user, args, key) for c in cases]
        for i, fut in enumerate(futs, 1):
            case, d = fut.result()
            r = score(case, d, args, key); results.append(r)
            print(f"[{i}/{len(cases)}] {'PASS' if r['pass'] else 'FAIL'} {case['id']}", flush=True)

    out = {"label": args.label, "model": f"{args.provider}/{args.model}", "judge": args.judge_model,
           "ingest": ing, "summary": summarize(results),
           "by_split": {s: summarize([r for r in results if r["split"] == s]) for s in ("dev", "test", "holdout", "holdout2")
                        if any(r["split"] == s for r in results)},
           "results": results}
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / f"{args.label}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out["summary"], indent=1))
    for s, v in out["by_split"].items():
        print(s, "overall", v["overall_pass_pct"], "answerable", v["answerable_pass_pct"], "abstain", v["abstention_pass_pct"],
              "adv", v["adversarial_pass_pct"], "faith", v["faithfulness_pct"])
    if not args.keep:
        with httpx.Client() as client:
            client.post(f"{BACKEND}/delete_all", json={}, headers={"Authorization": "Bearer " + _token(user)})
    if args.fail_under and (out["summary"]["overall_pass_pct"] or 0) < args.fail_under:
        print(f"FAIL: overall {out['summary']['overall_pass_pct']} < {args.fail_under}")
        sys.exit(1)


def _token(sub):
    import base64
    b = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{b({'alg':'none'})}.{b({'sub':sub})}."


if __name__ == "__main__":
    main()
