from app.grounding import (
    ensure_markers,
    parse_model_output,
    renumber,
    repair_citations,
    unsupported_numbers,
    verify_evidence,
)

SOURCES = [
    "Rate limits are enforced per API key, per minute. | Free | 60 | 10 | | Pro | 600 | 100 | | Enterprise | 6000 | 1500 |",
    "Keys expire after 90 days and must be rotated from the Developer Console.",
    "Vantora closed Q3 2026 with total revenue of $48.2 million, a 14% increase over Q3 2025 ($42.3 million).",
]


def test_parse_structured():
    p = parse_model_output('<evidence>\n[2] "Keys expire after 90 days"\n</evidence>\n<answer>\nKeys expire after 90 days. [2]\n</answer>')
    assert p.structured and p.answer == "Keys expire after 90 days. [2]" and p.evidence == [(2, "Keys expire after 90 days")]
    assert not p.not_found


def test_parse_not_found_and_clarify_and_untagged():
    assert parse_model_output("<evidence></evidence><answer>NOT_FOUND: the docs never mention a CEO.</answer>").not_found
    c = parse_model_output("<answer>CLARIFY: which plan do you mean?</answer>")
    assert c.clarify and c.answer.startswith("which plan")
    u = parse_model_output("Keys expire after 90 days [1].")
    assert not u.structured and u.answer.startswith("Keys expire")


def test_parse_truncated_answer_tag():
    assert parse_model_output("<evidence></evidence><answer>The limit is 600").answer == "The limit is 600"


def test_verify_evidence_exact_fuzzy_and_fabricated():
    ok = verify_evidence([(2, "Keys expire after 90 days")], SOURCES)
    assert ok and ok[0][0] == 2
    # wrong source number is re-attributed
    assert verify_evidence([(1, "Keys expire after 90 days")], SOURCES)[0][0] == 2
    # table row with markdown noise
    assert verify_evidence([(1, "| Pro | 600 | 100 |")], SOURCES)
    assert not verify_evidence([(1, "Enterprise customers get a dedicated 99.99% uptime SLA")], SOURCES)


def test_unsupported_numbers():
    assert unsupported_numbers("The Pro plan allows 600 requests per minute.", SOURCES) == []
    assert unsupported_numbers("Revenue grew by $5.9 million.", SOURCES) == []           # 48.2 - 42.3
    assert unsupported_numbers("That is about 14% growth.", SOURCES) == []
    assert unsupported_numbers("Aurora guarantees 99.9% uptime.", SOURCES) == ["99.9%"]
    assert unsupported_numbers("Keys expire after 120 days.", SOURCES) == ["120"]
    assert unsupported_numbers("There are 3 plans.", SOURCES) == []                       # tiny ints ignored


def test_repair_citations_repoints_wrong_marker():
    ans = "Keys expire after 90 days and must be rotated from the Developer Console. [1]"
    assert repair_citations(ans, SOURCES).endswith("[2]")
    good = "The Pro plan allows 600 requests per minute. [1]"
    assert repair_citations(good, SOURCES) == good


def test_repair_citations_drops_out_of_range():
    assert "[9]" not in repair_citations("Keys expire after 90 days. [9]", SOURCES)


def test_ensure_markers_and_renumber():
    assert ensure_markers("Keys expire after 90 days.", [2]).endswith("[2]")
    assert ensure_markers("Already cited [1].", [2]) == "Already cited [1]."
    out, mapping = renumber("A [3] and B [1][3].", [3, 1])
    assert out == "A [1] and B [2][1]." and mapping == {3: 1, 1: 2}


def test_repair_never_overrides_verified_evidence():
    srcs = [
        "All Orion devices carry a 2-year limited warranty from the date of purchase. The warranty covers manufacturing defects.",
        "Orion Hardware is the consumer devices brand of Vantora Systems. This document describes the returns and warranty policy.",
    ]
    ans = "The standard Orion device warranty is 2 years from the date of purchase. [1]"
    assert repair_citations(ans, srcs, trusted={1}) == ans
    assert repair_citations(ans, srcs) == ans  # hyphen/plural tolerant support keeps the right marker


def test_percentage_arithmetic_is_allowed():
    src = ["Base rent is $8,450 per month. Base rent increases by 3.5% at the start of each lease year."]
    assert unsupported_numbers("In year two the rent is $8,745.75 per month.", src) == []
    assert unsupported_numbers("In year two the rent is $9,999 per month.", src) == ["$9,999"]
