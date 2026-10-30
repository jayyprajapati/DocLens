"""Safe document extraction — the upload attack surface.

Every upload is treated as hostile. Before a single byte reaches a parser we

  1. **sniff the real type from the content**, not the filename: a ``.pdf`` must start with
     ``%PDF-``, a ``.docx`` must be a real OOXML zip, text must be valid UTF-8/16 with no binary;
  2. **inspect DOCX zips without inflating them**: entry count, total uncompressed size and
     compression ratio (zip bombs), and refuse macro-enabled payloads;

then parse in a **sandboxed child process** (``extract_worker.py``): empty environment, CPU /
memory / file-write / process limits, a wall-clock timeout, and a small concurrency cap so a
burst of uploads can't saturate the shared server's CPUs. Page and character caps bound how much
text — and therefore how many embeddings Brain computes — any one document can cost.

Parsing used to happen inside Brain, which other projects share; a single hostile PDF could stall
it for everyone. DocLens now sends Brain only plain, bounded text.
"""
from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import sys
import threading
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from .config import settings

logger = logging.getLogger("doclens.extract")

_WORKER = str(Path(__file__).with_name("extract_worker.py"))
_slots = threading.BoundedSemaphore(max(1, settings.extract_concurrency))

TEXT_EXT = (".md", ".markdown", ".txt")

PASSWORD_MSG = (
    "This file seems to be password-protected, so DocLens can't read it. "
    "Please upload a copy without a password, or another file."
)
LANGUAGE_MSG = (
    "DocLens currently supports documents written in English and other Latin-alphabet languages "
    "(such as Spanish, French, German or Portuguese). This file seems to be mostly in another script, "
    "so it can't be processed. Please upload another file."
)
_OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ENCRYPTED_PACKAGE = "EncryptedPackage".encode("utf-16-le")
ALLOWED_EXT = (".pdf", ".docx") + TEXT_EXT


class ExtractionRejected(Exception):
    """The file was refused. ``code`` is machine-readable, ``message`` is safe to show users."""

    def __init__(self, code: str, message: str, status: int = 415):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class Extracted:
    text: str
    kind: str
    truncated: bool = False
    stats: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# ── type sniffing ────────────────────────────────────────────────────────────


def _docx_preflight(data: bytes) -> None:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ExtractionRejected("bad_docx", "This isn't a valid Word (.docx) file.") from exc
    with zf:
        infos = zf.infolist()
        names = {i.filename for i in infos}
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            raise ExtractionRejected("bad_docx", "This isn't a valid Word (.docx) file.")
        if len(infos) > settings.docx_max_entries:
            raise ExtractionRejected("too_complex", "This Word file has too many internal parts to process safely.")
        total = sum(i.file_size for i in infos)
        if total > settings.docx_max_uncompressed_mb * 1024 * 1024:
            raise ExtractionRejected("too_complex", "This Word file expands to more data than we can process safely.")
        for i in infos:
            # a zip bomb: tiny compressed entry that inflates enormously
            if i.file_size > 2 * 1024 * 1024 and i.compress_size and i.file_size / i.compress_size > 150:
                raise ExtractionRejected("too_complex", "This Word file looks like a compression bomb and was refused.")
            if i.flag_bits & 0x1:
                raise ExtractionRejected("encrypted", PASSWORD_MSG, 422)
        if any(n.lower().endswith("vbaproject.bin") for n in names):
            raise ExtractionRejected("macro", "Macro-enabled Word files aren't accepted. Save it as a normal .docx and try again.")


def sniff(filename: str, data: bytes) -> str:
    """Return the verified kind ('pdf' | 'docx' | 'text') or raise ExtractionRejected."""
    name = (filename or "").lower().strip()
    if not data:
        raise ExtractionRejected("empty_file", "The uploaded file is empty.", 400)
    if not name.endswith(ALLOWED_EXT):
        raise ExtractionRejected("unsupported_type", "Supported types: PDF, Word (.docx), Markdown (.md) or plain text (.txt).")
    head = data[:1024]
    if name.endswith(".pdf"):
        if b"%PDF-" not in head:
            raise ExtractionRejected("type_mismatch", "This file is named .pdf but isn't a PDF.")
        return "pdf"
    if name.endswith(".docx"):
        if data.startswith(_OLE_MAGIC):
            # Office saves password-protected .docx files as an OLE container holding an
            # "EncryptedPackage" stream; any other OLE file is an old binary .doc renamed .docx
            if _ENCRYPTED_PACKAGE in data:
                raise ExtractionRejected("encrypted", PASSWORD_MSG, 422)
            raise ExtractionRejected(
                "type_mismatch", "This looks like an old Word (.doc) file renamed to .docx. Open it in Word, save it as .docx, and upload it again."
            )
        if not data.startswith(b"PK\x03\x04"):
            raise ExtractionRejected("type_mismatch", "This file is named .docx but isn't a Word document.")
        _docx_preflight(data)
        return "docx"
    # text / markdown: must really be text
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            data.decode("utf-16")
        except UnicodeDecodeError as exc:
            raise ExtractionRejected("type_mismatch", "This text file isn't valid UTF-16.") from exc
        return "text"
    if b"\x00" in data[:65536]:
        raise ExtractionRejected("type_mismatch", "This file contains binary data, not text.")
    try:
        data[: 1024 * 1024].decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        # tolerate a multibyte char cut at the 1 MB probe boundary
        if exc.start < 1024 * 1024 - 4:
            raise ExtractionRejected("type_mismatch", "Text files must be UTF-8 encoded.") from exc
    return "text"


# ── sandboxed parse ──────────────────────────────────────────────────────────


def _run_worker(kind: str, data: bytes, max_pages: int, max_chars: int) -> dict:
    timeout = settings.extract_timeout_s
    env = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONHASHSEED": "0"}
    cmd = [
        sys.executable, "-I", _WORKER, kind, str(max_pages), str(max_chars),
        str(int(timeout)), str(settings.extract_mem_mb),
    ]
    acquired = _slots.acquire(timeout=timeout)
    if not acquired:
        raise ExtractionRejected("busy", "The server is busy processing other documents. Please try again in a minute.", 503)
    try:
        proc = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout, env=env, cwd="/", check=False)
    except subprocess.TimeoutExpired as exc:
        raise ExtractionRejected("too_complex", "This file took too long to process and was stopped. Try a smaller or simpler file.", 422) from exc
    finally:
        _slots.release()
    if proc.returncode != 0 or not proc.stdout:
        # killed by a resource limit (CPU/memory) or crashed inside a parser
        logger.warning("extract worker exited rc=%s stderr=%s", proc.returncode, proc.stderr[-300:])
        raise ExtractionRejected("too_complex", "This file is too large or complex to process safely.", 422)
    try:
        return json.loads(proc.stdout)
    except ValueError as exc:
        raise ExtractionRejected("unreadable", "This file could not be read.", 422) from exc


def extract(filename: str, data: bytes, *, max_pages: int, max_chars: int) -> Extracted:
    kind = sniff(filename, data)
    res = _run_worker(kind, data, max_pages, max_chars)
    if res.get("error") == "encrypted":
        raise ExtractionRejected("encrypted", PASSWORD_MSG, 422)
    if res.get("error"):
        raise ExtractionRejected(res["error"], res.get("message") or "This file could not be read.", 422)
    text = (res.get("text") or "").strip()
    stats = res.get("stats") or {}
    if len(text.split()) < 3:
        raise ExtractionRejected("no_text", "No readable text was found in this file.", 422)
    if not latin_script(text):
        raise ExtractionRejected("unsupported_language", LANGUAGE_MSG, 422)
    warnings: list[str] = []
    if res.get("truncated"):
        warnings.append("truncated")
    if stats.get("hidden_chars", 0) >= 20 or stats.get("hidden_runs", 0) >= 1:
        warnings.append("hidden_text_removed")
    if stats.get("image_only_pages"):
        warnings.append("image_pages_skipped")
    elif stats.get("images"):
        warnings.append("images_not_read")
    return Extracted(text=text, kind=kind, truncated=bool(res.get("truncated")), stats=stats, warnings=warnings)


def latin_script(text: str, sample: int = 200_000) -> bool:
    """True unless the text is mostly in a non-Latin script (CJK, Devanagari, Arabic, Cyrillic, …).
    Retrieval uses an English embedding model, so only Latin-alphabet languages are supported; a
    document that merely contains some foreign names or quotes still passes."""
    letters = [c for c in text[:sample] if c.isalpha()]
    if len(letters) < 40:
        return True
    latin = sum(1 for c in letters if ord(c) < 0x250 or 0x1E00 <= ord(c) <= 0x1EFF)
    return latin / len(letters) >= 0.6


def worker_available() -> bool:
    return os.path.exists(_WORKER)
