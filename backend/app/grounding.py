"""Post-generation grounding checks — the deterministic half of "answer only if found".

The model replies with ``<evidence>`` (verbatim quotes) and an ``<answer>``. Here we

  * parse that reply tolerantly (small models don't always follow formats),
  * verify every quote really occurs in the source it names (exact, then fuzzy token match),
  * repair citation markers that point at the wrong source,
  * flag numbers in the answer that appear in no source and aren't simple arithmetic on
    source numbers (a cheap, high-precision hallucination detector).

Nothing here calls an LLM, so it adds ~milliseconds.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

_EVID_RE = re.compile(r"<evidence>(.*?)</evidence>", re.DOTALL | re.IGNORECASE)
_ANS_RE = re.compile(r"<answer>(.*?)(?:</answer>|$)", re.DOTALL | re.IGNORECASE)
_EVID_LINE_RE = re.compile(r"""^\s*[-*]?\s*\[(\d+)\]\s*[:\-–]?\s*["“'‘`]?(.+?)["”'’`]?\s*$""")
_CITE_RE = re.compile(r"\[(\d+)\]")
_NOT_FOUND_RE = re.compile(r"^\W*NOT[_ ]FOUND\b[\s:.\-–—]*", re.IGNORECASE)
_CLARIFY_RE = re.compile(r"^\W*CLARIFY\b[\s:.\-–—]*", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9.'_@/%-]*", re.IGNORECASE)
_NUM_RE = re.compile(r"(?<![\w.])\$?\d[\d,]*(?:\.\d+)?%?")

_STOP = frozenset(
    "a an the and or of to in on for with by from at as is are was were be been it its this that these those "
    "there their they them he she his her you your we our i me my not no yes do does did can could should would "
    "will may might has have had than then so if but also about which who whom what when where how why per each "
    "any all some more most other such only into over under between within across up down out off".split()
)


@dataclass
class Parsed:
    answer: str
    evidence: list[tuple[int, str]] = field(default_factory=list)  # (source number, quote)
    not_found: bool = False
    clarify: bool = False
    structured: bool = False  # the model followed the tagged format


def parse_model_output(raw: str) -> Parsed:
    raw = (raw or "").strip()
    am = _ANS_RE.search(raw)
    em = _EVID_RE.search(raw)
    structured = bool(am)
    if am:
        answer = am.group(1).strip()
    else:
        # Untagged reply (small model): drop any stray evidence block, keep the prose.
        answer = _EVID_RE.sub("", raw).replace("<evidence>", "").strip()
    evidence: list[tuple[int, str]] = []
    if em:
        for line in em.group(1).splitlines():
            m = _EVID_LINE_RE.match(line)
            if m and m.group(2).strip():
                evidence.append((int(m.group(1)), m.group(2).strip()))
    not_found = bool(_NOT_FOUND_RE.match(answer))
    clarify = bool(_CLARIFY_RE.match(answer))
    if not_found:
        answer = _NOT_FOUND_RE.sub("", answer).strip()
    elif clarify:
        answer = _CLARIFY_RE.sub("", answer).strip()
    return Parsed(answer=answer, evidence=evidence, not_found=not_found, clarify=clarify, structured=structured)


# ── text normalisation / token support ──────────────────────────────────────


def _norm(text: str) -> str:
    t = (text or "").lower()
    t = re.sub(r"[|*_`#>\[\]()“”‘’\"']", " ", t)
    t = re.sub(r"(?<=\d),(?=\d{3})", "", t)
    t = re.sub(r"[‐-―−]", "-", t)
    return re.sub(r"\s+", " ", t).strip()


def _tokens(text: str) -> list[str]:
    toks = [w.strip(".'_-/") for w in _WORD_RE.findall(_norm(text).replace("-", " "))]
    return [w for w in toks if w and w not in _STOP]


def quote_support(quote: str, source: str) -> float:
    """1.0 for a verbatim (normalised) quote; otherwise the fraction of the quote's content
    tokens found in the source. Handles ellipses ("…") by scoring each fragment."""
    ns = _norm(source)
    frags = [f for f in re.split(r"\.\.\.|…", quote) if f.strip()] or [quote]
    scores = []
    src_tokens = set(_tokens(source))
    for f in frags:
        nf = _norm(f)
        if not nf:
            continue
        if nf in ns:
            scores.append(1.0)
            continue
        toks = _tokens(f)
        if not toks:
            continue
        scores.append(sum(1 for t in toks if t in src_tokens) / len(toks))
    return min(scores) if scores else 0.0


def verify_evidence(evidence: list[tuple[int, str]], sources: list[str], threshold: float = 0.8) -> list[tuple[int, str, float]]:
    """Return (source_no, quote, support) for evidence lines that are really in the sources.
    A quote attributed to the wrong source is re-attributed to the best-matching one."""
    verified = []
    for n, quote in evidence:
        best_n, best = 0, 0.0
        order = ([n - 1] if 1 <= n <= len(sources) else []) + [i for i in range(len(sources)) if i != n - 1]
        for i in order:
            s = quote_support(quote, sources[i])
            if s > best + 1e-9:
                best_n, best = i + 1, s
            if best >= 0.999:
                break
        if best >= threshold:
            verified.append((best_n, quote, best))
    return verified


# ── citations ────────────────────────────────────────────────────────────────


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?:])\s+|\n+", text) if s.strip()]


def _stem(w: str) -> str:
    for suf in ("ing", "ies", "es", "ed", "ly", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def _support(sentence: str, source: str) -> float:
    toks = {_stem(t) for t in _tokens(re.sub(r"\[\d+\]", " ", sentence))}
    if not toks:
        return 0.0
    src = {_stem(t) for t in _tokens(source)}
    nums = {t for t in toks if any(c.isdigit() for c in t)}
    base = sum(1 for t in toks if t in src) / len(toks)
    if nums:  # numbers are the strongest signal of which chunk states a fact
        base = 0.5 * base + 0.5 * (sum(1 for t in nums if t in src) / len(nums))
    return base


def repair_citations(answer: str, sources: list[str], trusted: set[int] | None = None) -> str:
    """Fix markers that point at the wrong source; drop markers outside the source list.

    ``trusted`` = source numbers whose evidence quotes were verified verbatim: a marker that
    points at one of those is never touched. Any other marker is re-pointed only when the
    sentence is clearly better supported by a different source (preferring trusted ones)."""
    trusted = trusted or set()
    if not sources:
        return _CITE_RE.sub("", answer)
    out_lines = []
    for line in answer.split("\n"):
        # never split off a trailing marker ("… Console. [1]") from the sentence it belongs to
        pieces = re.split(r"(?<=[.!?:])\s+(?!\[\d+\])", line) if line.strip() else [line]
        fixed = []
        for sent in pieces:
            if _CITE_RE.search(sent):
                scores = [_support(sent, s) for s in sources]
                bonus = [0.15 if (i + 1) in trusted else 0.0 for i in range(len(sources))]
                best = max(range(len(sources)), key=lambda i: scores[i] + bonus[i])

                def sub(m: re.Match) -> str:
                    n = int(m.group(1))
                    if not 1 <= n <= len(sources):
                        return best_marker(best) if scores[best] >= 0.5 else ""
                    if n in trusted:
                        return m.group(0)
                    if scores[n - 1] < 0.45 and scores[best] >= 0.5 and scores[best] > scores[n - 1] + 0.2:
                        return best_marker(best)
                    return m.group(0)

                sent = _CITE_RE.sub(sub, sent)
                sent = re.sub(r"(\[\d+\])(?:\s*\1)+", r"\1", sent)  # "[2][2]" -> "[2]"
            fixed.append(sent)
        out_lines.append(" ".join(fixed))
    return "\n".join(out_lines)


def best_marker(i: int) -> str:
    return f"[{i + 1}]"


def cited_numbers(answer: str) -> list[int]:
    seen: list[int] = []
    for m in _CITE_RE.finditer(answer):
        n = int(m.group(1))
        if n not in seen:
            seen.append(n)
    return seen


def best_sources(answer: str, sources: list[str], k: int = 2, floor: float = 0.3) -> list[int]:
    """1-based numbers of the sources that best support the answer text (lexically)."""
    plain = _CITE_RE.sub("", answer)
    scored = sorted(((_support(plain, s), i + 1) for i, s in enumerate(sources)), reverse=True)
    return [n for sc, n in scored[:k] if sc >= floor]


def ensure_markers(answer: str, source_numbers: list[int]) -> str:
    """If the model cited nothing but its evidence is verified, attach the supporting
    sources to the end of the first paragraph so the answer is traceable."""
    if _CITE_RE.search(answer) or not source_numbers:
        return answer
    marks = "".join(f"[{n}]" for n in source_numbers[:2])
    first, sep, rest = answer.partition("\n")
    return f"{first.rstrip()} {marks}{sep}{rest}"


def renumber(answer: str, used: list[int]) -> tuple[str, dict[int, int]]:
    """Compact the cited source numbers to 1..k in order of first use."""
    mapping = {old: new for new, old in enumerate(used, start=1)}
    return _CITE_RE.sub(lambda m: f"[{mapping[int(m.group(1))]}]" if int(m.group(1)) in mapping else "", answer), mapping


# ── numeric hallucination check ──────────────────────────────────────────────


def _to_float(tok: str) -> float | None:
    try:
        return float(tok.replace("$", "").replace(",", "").replace("%", ""))
    except ValueError:
        return None


def _numbers(text: str) -> list[float]:
    out = []
    for m in _NUM_RE.findall(re.sub(r"\[\d+\]", " ", text)):
        v = _to_float(m)
        if v is not None:
            out.append(v)
    return out


def unsupported_numbers(answer: str, sources: list[str], question: str = "") -> list[str]:
    """Numbers in the answer that appear in no source/question and aren't a sum, difference,
    product, ratio or percentage of two source numbers. Small bare integers (list counts,
    ordinals) are ignored."""
    src_nums = set(_numbers(" ".join(sources) + " " + question))
    pct_nums = {float(m.replace(",", "")) for m in re.findall(r"(\d[\d,]*(?:\.\d+)?)\s*%", " ".join(sources) + " " + question)}
    # numbers spelled out in the sources ("twenty-five", "five") are rare in our domain; skip.
    derived = set(src_nums)
    # years/ids make poor operands (2025/2026 ≈ 99.95%) — arithmetic only over quantities
    pool = sorted(n for n in src_nums if not (n == int(n) and 1900 <= n <= 2100))[:120]
    for a, b in itertools.combinations(pool, 2):
        derived.update((a + b, abs(a - b), a * b))
        # percentage arithmetic only with numbers the sources actually write as percentages:
        # "8,450 up 3.5%" -> 8,745.75; "20% of 300" -> 60
        for base, pct in ((a, b), (b, a)):
            if pct in pct_nums:
                derived.update((base * pct / 100, base * (1 + pct / 100), base * (1 - pct / 100)))
        if b:
            derived.update((a / b, 100 * a / b))
        if a:
            derived.update((b / a, 100 * b / a))
    bad = []
    for m in _NUM_RE.findall(re.sub(r"\[\d+\]", " ", answer)):
        v = _to_float(m)
        if v is None:
            continue
        if v < 10 and "." not in m and "$" not in m and "%" not in m:
            continue
        # rounding slack = half a unit in the last digit the answer states ("34.9%" vs 34.906)
        dec = len(m.split(".")[1].rstrip("%")) if "." in m else 0
        tol = 0.5 * 10 ** (-dec) + 1e-6
        if any(abs(v - d) <= tol for d in derived):
            continue
        bad.append(m)
    return bad
