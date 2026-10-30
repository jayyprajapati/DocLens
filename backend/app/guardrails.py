"""Guardrails: input screening, untrusted-document neutralisation, output hygiene.

Defence in depth against prompt injection / jailbreaks / prompt exfiltration — no single
layer is trusted on its own:

  1. ``screen_query``     — deterministic pre-LLM screen of the user's message. High-confidence
                            attacks are refused without spending an LLM call.
  2. ``neutralize_source``— retrieved document text is *untrusted data*. Instruction-like
                            sentences ("ignore previous instructions …") are removed before the
                            text reaches the model; ``scan_document`` flags them at upload.
  3. prompt hardening     — see ``prompts.py`` (sources in tagged, escaped blocks; the model is
                            told sources are data, never instructions).
  4. ``sanitize_answer``  — output hygiene: strips HTML, remote images/links the sources never
                            contained (a classic data-exfiltration channel) and blocks replies
                            that echo the system prompt.

Patterns are intentionally specific (an imperative aimed at the assistant) so ordinary questions
*about* prompt injection, or documents that discuss it, are not blocked.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

MAX_QUERY_CHARS = 4000

REFUSAL_REPLY = (
    "I can only help with questions about your uploaded documents, so I can't follow that "
    "request. Ask me something about your files and I'll answer with citations."
)

_I = re.IGNORECASE | re.DOTALL

# (category, pattern). Categories drive the audit trail; all are refused the same way.
_QUERY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("override", re.compile(
        r"\b(ignore|disregard|forget|override|bypass|drop|skip)\b[^.\n]{0,30}\b(all|any|every|the|your|previous|prior|above|earlier|preceding|system|safety)\b"
        r"[^.\n]{0,30}\b(instructions?|prompts?|rules?|guidelines?|directions?|restrictions?|constraints?|guardrails?|documents?|sources?|context)\b", _I)),
    ("override", re.compile(r"\b(new|updated|real|actual)\s+(instructions?|rules?)\s*(are|:)", _I)),
    ("override", re.compile(r"\byou\s+(must|will|shall)\s+now\b[^.\n]{0,40}\b(obey|ignore|only)\b", _I)),
    ("exfil_prompt", re.compile(
        r"\b(repeat|reveal|print|show|display|output|echo|recite|read|leak|dump|tell\s+me|give\s+me|write\s+out|what\s+(is|are|were))\b"
        r"[^.\n]{0,50}\b(system|initial|original|hidden|secret|developer|internal|your)\b[^.\n]{0,15}\b(prompts?|instructions?|rules|guidelines|message|configuration|directives?)\b", _I)),
    ("exfil_prompt", re.compile(r"\b(instructions?|rules|prompt)\b[^.\n]{0,20}\b(you\s+(were|are|have\s+been)\s+(given|told|programmed)|before\s+this\s+conversation|at\s+the\s+(start|beginning))\b", _I)),
    ("exfil_prompt", re.compile(r"\bverbatim\b[^.\n]{0,40}\b(prompt|instructions?|rules)\b", _I)),
    ("jailbreak", re.compile(r"\b(DAN|do\s+anything\s+now|developer\s+mode|jailbreak(ed)?|god\s+mode|unrestricted\s+mode|evil\s+mode)\b", _I)),
    ("jailbreak", re.compile(r"\b(pretend|imagine|act\s+as\s+if|roleplay|role-play|suppose)\b[^.\n]{0,60}\b(no|without|free\s+of|don'?t\s+have|do\s+not\s+have)\b[^.\n]{0,25}\b(restrictions?|rules|limits?|filters?|guardrails?|restraints?)\b", _I)),
    ("jailbreak", re.compile(r"\byou\s+are\s+now\b[^.\n]{0,60}\b(ai|assistant|bot|model|persona|character)\b[^.\n]{0,60}\b(no|without|any)\b[^.\n]{0,20}\b(restrictions?|rules|limits?|filters?)\b", _I)),
    ("jailbreak", re.compile(r"\b(pretend|act)\b[^.\n]{0,20}\byou\s+(are|have)\s+no\b", _I)),
    ("delimiter", re.compile(r"</?\s*(sources?|system|assistant|instructions?|context|documents?)\s*>|<\|\s*(im_start|im_end|system)\s*\|>|\[/?INST\]|^\s*(system|assistant)\s*:", _I | re.MULTILINE)),
    ("secret", re.compile(r"\b(your|yours)\s+(own\s+)?(api[\s_-]?keys?|credentials?|secrets?|passwords?|tokens?|environment\s+variables?|env\s+vars?)", _I)),
    ("secret", re.compile(r"\b(api[\s_-]?keys?|credentials?|secrets?|passwords?|tokens?|environment\s+variables?|env\s+vars?)\b[^.\n]{0,30}\byou\b[^.\n]{0,15}\b(use[ds]?|have|were|are|configured|stored|hold|got)\b", _I)),
    ("exfil_link", re.compile(r"!\[[^\]]*\]\(\s*https?://", _I)),
]

# Sentences inside *documents* that try to instruct the assistant.
_SOURCE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(ignore|disregard|forget|override)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|system|the\s+user'?s?)\b[^.\n]{0,40}\b(instructions?|prompts?|rules?|question|context|directions?)\b", _I),
    re.compile(r"\b(system|assistant|ai|llm|model|chatbot|bot)\b[^.\n]{0,12}\b(instructions?|notes?|messages?|commands?|directives?|override)\b[^.\n]{0,25}(:|\bto\s+the\s+(assistant|ai|model|llm)\b|\bfor\s+the\s+(assistant|ai|model|llm)\b)", _I),
    re.compile(r"\b(instructions?|note|message)\s+(to|for)\s+(the\s+)?(assistant|ai|model|llm|chatbot)\b", _I),
    re.compile(r"\b(reply|respond|answer|output|say)\b[^.\n]{0,15}\b(only|just)\b[^.\n]{0,15}\b(with|the\s+words?)\b", _I),
    re.compile(r"\b(reveal|print|show|repeat|output|disclose)\b[^.\n]{0,25}\b(system\s+prompt|your\s+(full\s+)?(system\s+)?(prompt|instructions))\b", _I),
    re.compile(r"\bmust\s+be\s+(obeyed|followed)\b|\bdo\s+not\s+(tell|inform)\s+the\s+user\b", _I),
    re.compile(r"\byou\s+(must|should|will)\s+(now\s+)?(obey|comply|follow\s+these)\b", _I),
    re.compile(r"^\W*(assistant|system|ai)\s*:\s*(you|when|if|ignore|always|never|tell|do\s+not|don'?t|reply|respond|say|send|output|print|reveal|instead)\b", _I),
    re.compile(r"\btell\s+(the\s+)?(user|reader|customer|human)\s+to\b", _I),
    re.compile(r"\b(when|if)\s+(you\s+are\s+|you're\s+)?(summari[sz]ing|answering|asked|responding|reading|reporting)\b[^.\n]{0,80}\b(tell|say|respond|reply|state|mention|include|append|add|write|send)\b", _I),
    re.compile(r"\b(append|add|include|insert)\b[^.\n]{0,40}\b(to|in|at\s+the\s+end\s+of)\s+(every|each|all|your)\s+(answer|response|reply|message)s?\b", _I),
    re.compile(r"\balways\s+(include|show|render|output)\s+the\s+(image|link|url|pixel)\b", _I),
    re.compile(r"\bai\s+assistants?\b[^.\n]{0,40}\b(must|should|are\s+required|shall|need\s+to)\b", _I),
]

# Hidden or active content that has no business in text shown to the model: HTML comments
# (invisible to the document's human readers) and markdown/HTML images (exfiltration pixels).
_HIDDEN_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_SRC_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)|<img\b[^>]*>", re.IGNORECASE)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
REMOVED_MARK = "[removed: instruction-like text]"

_GREETING = re.compile(
    r"^\s*(hi|hello|hey|hiya|yo|good\s+(morning|afternoon|evening)|thanks?|thank\s+you|thx|ok(ay)?|cool|great|bye|goodbye)\b[\s!.,?]*$", _I)
GREETING_REPLY = "Hi! I'm Lume. Ask me anything about the documents you've added and I'll answer with citations."


@dataclass
class Screen:
    blocked: bool = False
    categories: list[str] = field(default_factory=list)
    reply: str = ""
    smalltalk: bool = False


def normalize_text(text: str) -> str:
    """NFKC-fold and strip zero-width / control characters so obfuscated attacks
    ("ig​nore", full-width letters) hit the same patterns as plain text."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"[​-‏‪-‮⁠﻿]", "", t)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)


def screen_query(query: str) -> Screen:
    q = normalize_text(query).strip()
    if _GREETING.match(q):
        return Screen(smalltalk=True, reply=GREETING_REPLY)
    cats: list[str] = []
    for cat, pat in _QUERY_PATTERNS:
        if pat.search(q) and cat not in cats:
            cats.append(cat)
    if cats:
        return Screen(blocked=True, categories=cats, reply=REFUSAL_REPLY)
    return Screen()


def is_injection_sentence(sentence: str) -> bool:
    s = normalize_text(sentence)
    return any(p.search(s) for p in _SOURCE_PATTERNS)


def neutralize_source(text: str) -> tuple[str, int]:
    """Remove instruction-like sentences from untrusted document text.
    Returns (clean_text, removed_count). Line structure (tables, lists) is preserved."""
    removed = 0
    text = text or ""
    text, n_hidden = _HIDDEN_RE.subn(" ", text)
    text, n_img = _SRC_IMG_RE.subn("", text)
    removed += n_hidden + n_img
    out_lines = []
    for line in text.split("\n"):
        if not line.strip():
            out_lines.append(line)
            continue
        parts = re.split(r"(?<=[.!?])\s+", line)
        kept = []
        for part in parts:
            if is_injection_sentence(part):
                removed += 1
                kept.append(REMOVED_MARK)
            else:
                kept.append(part)
        out_lines.append(" ".join(kept))
    return "\n".join(out_lines), removed


def scan_document(text: str) -> list[str]:
    """Upload-time scan: short excerpts of instruction-like text found in a document."""
    hits = []
    text = normalize_text(text)
    for m in _HIDDEN_RE.finditer(text):  # hidden comments are judged on their content
        if is_injection_sentence(m.group(0).strip("<!->").strip()):
            hits.append("hidden: " + m.group(0)[:150].strip())
            break
    for sent in _SENT_SPLIT.split(text):
        if sent.strip() and is_injection_sentence(sent):
            hits.append(sent.strip()[:160])
            if len(hits) >= 5:
                break
    return hits


def escape_delimiters(text: str) -> str:
    """Neutralise anything that could close or forge our prompt delimiters."""
    return re.sub(r"<\s*(/?)\s*(source|sources|question|history|system)\b", r"<​\1\2", text or "", flags=re.IGNORECASE)


# ── output hygiene ──────────────────────────────────────────────────────────

_IMG_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)[^)]*\)")
_RAW_URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
_WORD_RE = re.compile(r"[a-z0-9']+")


def _shingles(text: str, n: int = 7) -> set[tuple[str, ...]]:
    w = _WORD_RE.findall(text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def leaks_system_prompt(answer: str, system_prompt: str, n: int = 7, max_hits: int = 1) -> bool:
    """True if the answer reproduces a verbatim run of the system prompt."""
    if not answer or not system_prompt:
        return False
    return len(_shingles(answer, n) & _shingles(system_prompt, n)) >= max_hits


def sanitize_answer(answer: str, source_text: str) -> tuple[str, list[str]]:
    """Strip exfiltration channels from the model output. URLs are allowed only if they
    literally occur in the retrieved sources. Returns (clean_answer, flags)."""
    flags: list[str] = []
    allowed = set(_RAW_URL_RE.findall(source_text or ""))
    if _IMG_RE.search(answer):
        answer = _IMG_RE.sub("", answer)
        flags.append("image_removed")

    def _link(m: re.Match) -> str:
        if m.group(2) in allowed:
            return m.group(0)
        flags.append("link_removed")
        return m.group(1)

    answer = _LINK_RE.sub(_link, answer)

    def _raw(m: re.Match) -> str:
        url = m.group(0).rstrip(".,;")
        return m.group(0) if url in allowed else "[link removed]"

    answer = _RAW_URL_RE.sub(_raw, answer)
    if "[link removed]" in answer:
        flags.append("link_removed")
    return answer.strip(), sorted(set(flags))
