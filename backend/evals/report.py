"""Render saved eval runs as Markdown tables (paste into EVALS.md).

  python evals/report.py baseline-169 v6-auto [v6-always ...]
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).parent
ROWS = [("overall_pass_pct", "**Overall pass**"), ("answerable_pass_pct", "Answerable: correct **and** correctly cited"),
        ("answer_content_only_pct", "Answerable: correct content only"), ("citation_accuracy_pct", "Citation accuracy (of correct answers)"),
        ("abstention_pass_pct", "Declines when the docs don't contain it"), ("adversarial_pass_pct", "Adversarial cases resisted"),
        ("faithfulness_pct", "Faithfulness (LLM judge, answered cases)"), ("latency_ms_p50", "Latency p50 (ms)"), ("latency_ms_p95", "Latency p95 (ms)")]


def main(labels):
    runs = {l: json.loads((HERE / "results" / f"{l}.json").read_text()) for l in labels}
    for scope in ("all", "dev", "test", "holdout", "holdout2"):
        pick = (lambda d: d["summary"]) if scope == "all" else (lambda d, s=scope: d["by_split"].get(s))
        if any(pick(r) is None for r in runs.values()):
            continue
        n = pick(next(iter(runs.values())))["n"]
        print(f"\n#### {scope} (n={n})\n")
        print("| Metric | " + " | ".join(labels) + " |")
        print("|---|" + "---:|" * len(labels))
        for k, name in ROWS:
            print(f"| {name} | " + " | ".join(str(pick(r).get(k)) for r in runs.values()) + " |")
    print("\n#### By category (passed/total)\n")
    cats = sorted({c for r in runs.values() for c in r["summary"]["by_category"]})
    print("| Category | " + " | ".join(labels) + " |")
    print("|---|" + "---:|" * len(labels))
    for c in cats:
        print(f"| {c} | " + " | ".join(r["summary"]["by_category"].get(c, "-") for r in runs.values()) + " |")


if __name__ == "__main__":
    main(sys.argv[1:])
