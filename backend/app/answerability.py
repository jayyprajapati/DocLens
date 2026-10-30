"""Second-opinion check that the evidence really answers the question.

Models occasionally stretch a related fact into an answer ("18 initial hires" → "18 employees
work there today"; "unused days are forfeited on Jan 31" → "no payout when you leave"). The
generation call can't reliably catch its own stretch, so a short, strict verification call
re-reads the question against the cited source text and rejects answers that need
extrapolation. It runs when risk signals fire (``ANSWER_VERIFY=auto``) or always
(``always``); a "not found" reply is far cheaper than a confident wrong answer.
"""
from __future__ import annotations

import re

from . import brain_client, runtime
from .config import settings
from .retrieval import keywords

VERIFY_SYSTEM = """\
You are a strict fact-checker for a document question-answering system. You are given a \
QUESTION, the SOURCE text the answer cites, and a PROPOSED ANSWER.

Judge ONLY whether the claims the PROPOSED ANSWER makes are stated in the SOURCE, taking the \
scope of the QUESTION into account (its time, place, person, product and situation). Do not \
judge completeness, helpfulness or whether the question was fully addressed: an answer that \
says something is not covered, or that corrects a mistaken assumption in the question, is fine \
when what it asserts is in the SOURCE. Simple arithmetic on stated numbers is fine. Do not \
nitpick wording: paraphrase, rounding, and threshold phrasing ("above X" answered as "X") are fine. Reject only when a claim is a different fact (another number, date, name, \
entity, product or situation) or needs an inference the SOURCE does not make.

Examples (unrelated documents). SUPPORTED: source "Trains do not run above 40 C" with answer \
"40 C is the cutoff"; source "Fees are due within 14 days" with answer "payment is due in 14 \
days". UNSUPPORTED: source "The shop opened in 2019 with 4 staff" with answer "the shop has 4 \
staff today"; source "Library fines are waived on public holidays" with answer "fines are \
waived for students"; source "general terms for all tenants: 30-day notice" with answer "your \
lease with Acme needs 30 days' notice"; source "Gift cards expire 12 months after purchase" \
with answer "No, gift cards can't be refunded" (an expiry rule says nothing about refunds).

A yes/no answer is UNSUPPORTED unless the SOURCE addresses that exact question: a related rule \
(an expiry, a limit, a general policy, another party's terms) quoted correctly next to the "Yes" \
or "No" does not make the "Yes" or "No" supported.

Reply UNSUPPORTED if any asserted claim is a guess, a default, a figure or name missing from \
the SOURCE, or a fact stretched to a different time, place, person or situation than the one \
asked about (including using a rule about one situation as the answer for another). \
Otherwise reply SUPPORTED.

Reply on the first line with exactly SUPPORTED or UNSUPPORTED. If UNSUPPORTED, add a second \
line (max 35 words) saying what the documents do say that is closest and what is missing."""

_NEGATION = re.compile(r"\b(not|no|never|cannot|can't|isn't|aren't|doesn't|don't|won't|without|unavailable|prohibited|forfeit\w*|n/?a)\b", re.I)
_QUALIFIER = re.compile(r"\b(today|currently|now|still|as of|latest|ever|always|never|all|every|any|only|exactly|average|total|per|when (someone|an? \w+) leaves|after)\b", re.I)
_YESNO = re.compile(r"^\s*(is|are|was|were|do|does|did|can|could|will|would|should|has|have|had)\b", re.I)


def _stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def quote_coverage(question: str, quotes: list[str]) -> float:
    """Share of the question's distinctive terms present in the evidence quotes."""
    terms = [_stem(w) for w in keywords(question)]
    if not terms:
        return 1.0
    hay = {_stem(w) for w in keywords(" ".join(quotes))} | {_stem(w) for w in re.findall(r"[a-z0-9]+", " ".join(quotes).lower())}
    return sum(1 for t in terms if t in hay) / len(terms)


def should_verify(question: str, answer: str, quotes: list[str]) -> bool:
    mode = runtime.current().answer.verify
    if mode == "off":
        return False
    if mode == "always":
        return True
    # auto: verify when the answer is likely to lean on inference. Yes/no questions are the most
    # inference-prone ("is it waterproof?" answered "No" from "water damage isn't covered").
    if not quotes or _YESNO.match(question):
        return True
    if quote_coverage(question, quotes) < 0.6:
        return True
    return bool(_QUALIFIER.search(question)) and quote_coverage(question, quotes) < 0.85


def check(question: str, answer: str, sources: list[str], llm: dict, labels: list[str] | None = None) -> tuple[bool, str]:
    """Return (supported, explanation). ``labels`` name each source's document/section so the
    verifier can tell *whose* terms a passage states (a supplier FAQ is not a vendor contract).
    Verifier failures never block an answer."""
    labels = labels or [""] * len(sources)
    src = "\n\n".join(f"[{i}] ({lab})\n{s}" if lab else f"[{i}] {s}" for i, (s, lab) in enumerate(zip(sources, labels), 1))
    prompt = f"QUESTION:\n{question}\n\nSOURCE:\n{src}\n\nPROPOSED ANSWER:\n{answer}"
    try:
        out = brain_client.generate(
            system=VERIFY_SYSTEM, prompt=prompt, llm=llm, max_tokens=500, temperature=0.0,
            reasoning=settings.verify_reasoning or None,
        )
    except brain_client.BrainError:
        return True, ""
    text = (out.get("text") or "").strip()
    first, _, rest = text.partition("\n")
    verdict = first.strip().upper()
    if verdict.startswith("UNSUPPORTED"):
        return False, re.sub(r"\[\d+\]", "", rest).strip()
    return True, ""
