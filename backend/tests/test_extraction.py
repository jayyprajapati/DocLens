"""Upload hardening: type sniffing, zip-bomb preflight, the sandboxed parser, and the layout
work that makes PDFs answerable (columns, headings, tables, hidden text)."""
import pytest

from app import extraction
from app.extraction import ExtractionRejected, extract

from . import fixtures as fx

CAPS = dict(max_pages=300, max_chars=1_000_000)


def _x(name, data, **kw):
    return extract(name, data, **{**CAPS, **kw})


def test_two_columns_read_in_order():
    out = _x("depots.pdf", fx.two_column_pdf())
    assert out.stats["multi_column_pages"] == 1
    text = out.text
    # the whole left column comes before the right column, and sentences are not interleaved
    assert text.index("Priya Raman") < text.index("Beta section")
    assert "spoilage rate of 0.8 percent" in " ".join(text.split())
    assert "Regional Depot Report 2025" in text


def test_tables_become_markdown():
    out = _x("plans.pdf", fx.table_pdf())
    assert "| Team | 79 | 600 |" in out.text
    assert out.stats["tables"] == 1


def test_hidden_text_is_removed_but_inverted_heading_kept():
    out = _x("policy.pdf", fx.hidden_text_pdf())
    assert "PWNED" not in out.text and "IGNORE ALL" not in out.text
    assert "hidden_text_removed" in out.warnings
    assert "Warranty Terms" in out.text
    assert "24 month limited warranty" in out.text


def test_pdf_headings_marked():
    out = _x("guide.pdf", fx.headings_pdf())
    assert "## Onboarding Guide" in out.text
    assert "### Laptop Setup" in out.text or "## Laptop Setup" in out.text


def test_scanned_pdf_explains_ocr():
    with pytest.raises(ExtractionRejected) as e:
        _x("scan.pdf", fx.scanned_pdf())
    assert e.value.code == "scanned"


@pytest.mark.parametrize("name,data", [
    ("locked-rc4-40.pdf", fx.encrypted_pdf()),
    ("locked-rc4.pdf", fx.pdf_encrypted_with("pw", "RC4-128")),
    ("locked-aes128.pdf", fx.pdf_encrypted_with("pw", "AES-128")),
    ("locked-aes256.pdf", fx.pdf_encrypted_with("pw", "AES-256")),
    ("locked.docx", fx.encrypted_docx()),
])
def test_password_protected_files_stop_with_clear_message(name, data, monkeypatch):
    with pytest.raises(ExtractionRejected) as e:
        _x(name, data)
    assert e.value.code == "encrypted" and "password-protected" in e.value.message
    assert "another file" in e.value.message


def test_encrypted_docx_never_reaches_parser(monkeypatch):
    called = []
    monkeypatch.setattr(extraction, "_run_worker", lambda *a, **k: called.append(1))
    with pytest.raises(ExtractionRejected):
        _x("locked.docx", fx.encrypted_docx())
    assert not called


@pytest.mark.parametrize("alg", ["RC4-128", "AES-256"])
def test_permissions_only_pdf_is_read(alg):
    # "owner password" PDFs (print/copy restrictions) open without a password: read them normally
    out = _x("restricted.pdf", fx.pdf_encrypted_with("", alg))
    assert "| Team | 79 | 600 |" in out.text


def test_old_doc_renamed_to_docx_explained():
    with pytest.raises(ExtractionRejected) as e:
        _x("old.docx", fx.legacy_doc_renamed())
    assert e.value.code == "type_mismatch" and ".doc" in e.value.message


def test_page_cap_truncates():
    out = _x("audit.pdf", fx.long_pdf(120), max_pages=50)
    assert out.truncated and "truncated" in out.warnings
    assert out.stats["pages"] == 120 and out.stats["pages_read"] == 50
    assert "Page 50." in out.text and "Page 51." not in out.text


def test_char_cap_truncates_text():
    out = _x("big.txt", ("lorem ipsum dolor " * 20000).encode(), max_chars=5000)
    assert len(out.text) <= 5000 and out.truncated


def test_mostly_latin_document_with_some_chinese_is_accepted():
    out = _x("politica.pdf", fx.multilingual_pdf())
    assert "devoluciones" in out.text and "30 días" in out.text


def test_english_with_foreign_names_is_accepted():
    out = _x("suppliers.pdf", fx.english_with_foreign_names_pdf())
    assert "18 months" in out.text


def test_latin_alphabet_languages_are_accepted():
    out = _x("policies.txt", fx.latin_languages_text())
    assert "dreißig" in out.text and "trente" in out.text


@pytest.mark.parametrize("name,data", [
    ("notice.pdf", fx.chinese_pdf()),
    ("suchna.txt", fx.hindi_text()),
])
def test_unsupported_scripts_are_refused(name, data):
    with pytest.raises(ExtractionRejected) as e:
        _x(name, data)
    assert e.value.code == "unsupported_language" and "Latin-alphabet" in e.value.message


def test_pdf_javascript_is_inert_text_still_read():
    out = _x("report.pdf", fx.pdf_with_javascript())
    assert "4.2 million" in out.text
    assert "app.alert" not in out.text


@pytest.mark.parametrize("name,data,code", [
    ("invoice.pdf", fx.fake_pdf(), "type_mismatch"),
    ("notes.docx", b"%PDF-1.4 not a zip", "type_mismatch"),
    ("notes.txt", b"MZ\x90\x00\x03\x00\x00\x00binary", "type_mismatch"),
    ("payload.exe", b"MZ", "unsupported_type"),
    ("legacy.doc", b"\xd0\xcf\x11\xe0", "unsupported_type"),
    ("empty.pdf", b"", "empty_file"),
])
def test_sniffing_rejects_mismatches(name, data, code):
    with pytest.raises(ExtractionRejected) as e:
        _x(name, data)
    assert e.value.code == code


def test_docx_zip_bomb_refused_before_parsing(monkeypatch):
    called = []
    monkeypatch.setattr(extraction, "_run_worker", lambda *a, **k: called.append(1))
    with pytest.raises(ExtractionRejected) as e:
        _x("bomb.docx", fx.docx_zip_bomb())
    assert e.value.code == "too_complex" and not called


def test_docx_macro_refused():
    with pytest.raises(ExtractionRejected) as e:
        _x("macro.docx", fx.docx_with_macro())
    assert e.value.code == "macro"


def test_docx_keeps_body_order_and_headings():
    out = _x("travel.docx", fx.ordered_docx())
    t = out.text
    assert t.index("## Travel Policy") < t.index("### Per Diem Rates") < t.index("| London | GBP 85 |") < t.index("Receipts are required")


def test_docx_hidden_runs_removed():
    out = _x("travel.docx", fx.ordered_docx(hidden=True))
    assert "PWNED" not in out.text and "unlimited" not in out.text
    assert "hidden_text_removed" in out.warnings


def test_worker_timeout_is_a_clean_rejection(monkeypatch):
    # a budget no parse can meet: the worker is killed (CPU rlimit or wall clock), never hangs
    monkeypatch.setattr(extraction.settings, "extract_timeout_s", 0.05)
    with pytest.raises(ExtractionRejected) as e:
        _x("audit.pdf", fx.long_pdf(40))
    assert e.value.code == "too_complex"


def test_worker_gets_no_secrets(monkeypatch):
    """The parser child must not inherit the API process's environment (Mongo URI, keys)."""
    import subprocess

    seen = {}
    real = subprocess.run

    def spy(cmd, **kw):
        seen.update(kw.get("env") or {})
        return real(cmd, **kw)

    monkeypatch.setenv("MONGO_URI", "mongodb://secret")
    monkeypatch.setattr(extraction.subprocess, "run", spy)
    _x("a.txt", b"plain words are here")
    assert "MONGO_URI" not in seen and set(seen) <= {"PATH", "PYTHONDONTWRITEBYTECODE", "PYTHONHASHSEED"}


def test_table_stays_under_its_heading_in_two_column_paper():
    from evals.stress_eval import research_paper

    t = _x("paper.pdf", research_paper()).text
    assert t.index("## 2. Results") < t.index("| Clay | 16 | 2.8 | 0.7 |") < t.index("## 3. Cost")
