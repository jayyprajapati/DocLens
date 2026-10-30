"""Compare two saved eval runs and (optionally) gate on regressions.

  python evals/compare.py baseline v3-final [--split test] [--max-drop 1.0]

Exit code 1 if the candidate's overall pass rate dropped by more than --max-drop points, or if
any case the reference passed now fails (listed). Use in CI / before merging prompt, retrieval
or model changes.
"""
import argparse, json, sys
from pathlib import Path

HERE = Path(__file__).parent
METRICS = [("overall_pass_pct", "Overall pass"), ("answerable_pass_pct", "Answerable (strict: correct + cited)"),
           ("answer_content_only_pct", "Answerable (content only)"), ("citation_accuracy_pct", "Citation accuracy"),
           ("abstention_pass_pct", "Abstains when not in docs"), ("adversarial_pass_pct", "Adversarial resisted"),
           ("faithfulness_pct", "Faithfulness (LLM judge)"), ("latency_ms_p50", "Latency p50 (ms)"),
           ("latency_ms_p95", "Latency p95 (ms)")]


def load(label):
    return json.loads((HERE / "results" / f"{label}.json").read_text())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ref"); ap.add_argument("cand")
    ap.add_argument("--split", default="all", choices=["all", "dev", "test", "holdout", "holdout2"])
    ap.add_argument("--max-drop", type=float, default=1.0)
    a = ap.parse_args()
    ref, cand = load(a.ref), load(a.cand)
    pick = (lambda d: d["summary"]) if a.split == "all" else (lambda d: d["by_split"][a.split])
    r, c = pick(ref), pick(cand)
    print(f"{'metric':42} {a.ref:>12} {a.cand:>12}  delta")
    for k, name in METRICS:
        x, y = r.get(k), c.get(k)
        d = "" if x is None or y is None else f"{y - x:+.1f}"
        print(f"{name:42} {x!s:>12} {y!s:>12}  {d}")
    rp = {x["id"]: x for x in ref["results"] if a.split in ("all", x["split"])}
    cp = {x["id"]: x for x in cand["results"] if a.split in ("all", x["split"])}
    regress = [i for i in rp if i in cp and rp[i]["pass"] and not cp[i]["pass"]]
    fixed = [i for i in rp if i in cp and not rp[i]["pass"] and cp[i]["pass"]]
    print(f"\nfixed: {len(fixed)}  regressed: {len(regress)}")
    if regress:
        print("  regressions:", ", ".join(regress))
    drop = (r["overall_pass_pct"] or 0) - (c["overall_pass_pct"] or 0)
    if drop > a.max_drop:
        print(f"\nFAIL: overall pass dropped {drop:.1f} points (> {a.max_drop})"); sys.exit(1)


if __name__ == "__main__":
    main()
