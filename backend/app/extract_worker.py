"""Sandboxed document → text worker. Runs as a short-lived child process (see extraction.py).

Uploaded files are hostile input: a PDF can be a decompression bomb, a 10,000-page monster, a
parser-hang, or carry text a human never sees (white-on-white, 0.5 pt, off-page) aimed at the
assistant. Parsing therefore never happens inside the API process or inside Brain (which other
projects share). This script

  * caps its own CPU time, address space, file writes, open files and child processes before it
    touches the bytes, and is started with an empty environment (no secrets to read);
  * reads the file from stdin and writes one JSON object to stdout;
  * stops at ``max_pages`` / ``max_chars`` and reports what it skipped.

Deliberately standalone (stdlib + pdfplumber + python-docx): it must not import the app, so a
parser bug can't reach application state.

Usage: python -I extract_worker.py <kind> <max_pages> <max_chars> <cpu_seconds> <mem_mb> < file
"""
from __future__ import annotations

import io
import json
import re
import statistics
import sys

# ── sandbox ──────────────────────────────────────────────────────────────────


def _limit(cpu_s: int, mem_mb: int) -> None:
    try:
        import resource
    except ImportError:  # non-POSIX: rely on the parent's wall-clock timeout
        return
    for name, value in (
        ("RLIMIT_CPU", (cpu_s, cpu_s + 1)),
        ("RLIMIT_AS", (mem_mb * 1024 * 1024,) * 2),  # not enforced on macOS; enforced on Linux
        ("RLIMIT_FSIZE", (0, 0)),  # never write files
        ("RLIMIT_NPROC", (0, 0)),  # never spawn processes
        ("RLIMIT_CORE", (0, 0)),
    ):
        lim = getattr(resource, name, None)
        if lim is None:
            continue
        try:
            resource.setrlimit(lim, value)
        except (ValueError, OSError):
            pass


# ── shared helpers ───────────────────────────────────────────────────────────

_WS = re.compile(r"[ \t]+")
# glyphs with no Unicode mapping come out of pdfminer as "(cid:127)"; at a line start they are
# almost always list bullets
_CID_BULLET = re.compile(r"^\s*\(cid:\d+\)\s*")
_CID = re.compile(r"\(cid:\d+\)")


def _table_md(rows) -> str:
    cleaned = []
    for row in rows or []:
        cells = [(str(c) if c is not None else "").replace("\n", " ").replace("|", "/").strip() for c in row]
        if any(cells):
            cleaned.append(cells)
    if len(cleaned) < 2:
        return ""
    width = max(len(r) for r in cleaned)
    norm = [r + [""] * (width - len(r)) for r in cleaned]
    out = ["| " + " | ".join(norm[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    out += ["| " + " | ".join(r) + " |" for r in norm[1:]]
    return "\n".join(out)


# ── PDF ──────────────────────────────────────────────────────────────────────


def _is_white(color) -> bool:
    if color is None:
        return False
    if isinstance(color, (int, float)):
        color = (color,)
    try:
        vals = [float(v) for v in color]
    except (TypeError, ValueError):
        return False
    if len(vals) == 1:
        return vals[0] >= 0.97
    if len(vals) == 3:
        return all(v >= 0.97 for v in vals)
    if len(vals) == 4:  # CMYK: no ink
        return all(v <= 0.03 for v in vals)
    return False


class _Visibility:
    """Decides whether a glyph is something a human reader of the page can actually see."""

    def __init__(self, page):
        x0, top, x1, bottom = page.bbox
        self.box = (x0 - 2, top - 2, x1 + 2, bottom + 2)
        # dark filled shapes: white text on them is a real (inverted) heading, not hidden text
        self.dark = []
        for r in (page.rects or [])[:400]:
            if r.get("fill") and not _is_white(r.get("non_stroking_color")):
                self.dark.append((r["x0"], r["top"], r["x1"], r["bottom"]))
        self.hidden = 0

    def __call__(self, obj) -> bool:
        if obj.get("object_type") != "char":
            return True
        x0, top, x1, bottom = self.box
        cx = (obj.get("x0", 0) + obj.get("x1", 0)) / 2
        cy = (obj.get("top", 0) + obj.get("bottom", 0)) / 2
        visible = True
        if not (x0 <= cx <= x1 and top <= cy <= bottom):
            visible = False  # off-page
        elif (obj.get("size") or 0) < 2.0:
            visible = False  # microscopic
        elif _is_white(obj.get("non_stroking_color")):
            visible = any(a <= cx <= c and b <= cy <= d for a, b, c, d in self.dark)
        if not visible and (obj.get("text") or "").strip():
            self.hidden += 1
        return visible


def _gutter(words, width: float) -> float | None:
    """x of a vertical gutter splitting the page into two text columns, or None."""
    if len(words) < 40:
        return None
    best, best_cross = None, None
    lo, hi = int(width * 0.3), int(width * 0.7)
    for x in range(lo, hi + 1, 2):
        cross = sum(1 for w in words if w["x0"] < x < w["x1"])
        if best_cross is None or cross < best_cross:
            best, best_cross = x, cross
    if best is None:
        return None
    left = [w for w in words if w["x1"] <= best]
    right = [w for w in words if w["x0"] >= best]
    if best_cross > 0.08 * len(words) or len(left) < 0.2 * len(words) or len(right) < 0.2 * len(words):
        return None
    # real columns: the two sides run side by side (lines at the same height on both)
    lt = {round(w["top"] / 4) for w in left}
    rt = {round(w["top"] / 4) for w in right}
    if len(lt & rt) < 0.3 * min(len(lt), len(rt)):
        return None
    return float(best)


def _lines_to_text(lines, body_size: float) -> str:
    """Join text lines, marking headings (larger or bold short lines) as Markdown and keeping
    paragraph breaks, so the chunker gets real structure from a PDF."""
    out: list[str] = []
    prev_bottom = None
    heights = [ln["bottom"] - ln["top"] for ln in lines if not ln.get("table") and ln.get("bottom", 0) > ln.get("top", 0)]
    typical = statistics.median(heights) if heights else 10.0
    for ln in lines:
        if ln.get("table"):
            # attach the table to the paragraph that introduces it ("Table 1 reports …") with no
            # blank line, so the chunker keeps caption + table together: a bare Markdown table is
            # hard for the reranker to match to a question
            last = next((x for x in reversed(out) if x), "")
            if out and out[-1] and not last.startswith("#"):
                out += [ln["table"], ""]
            else:
                out += ["", ln["table"], ""]
            prev_bottom = ln["bottom"]
            continue
        text = _WS.sub(" ", ln.get("text") or "").strip()
        if _CID_BULLET.match(text):
            text = "- " + _CID_BULLET.sub("", text)
        text = _CID.sub("", text).strip()
        if not text:
            continue
        chars = [c for c in ln.get("chars", []) if (c.get("text") or "").strip()]
        size = statistics.mean(c.get("size") or body_size for c in chars) if chars else body_size
        bold = bool(chars) and sum(1 for c in chars if "bold" in (c.get("fontname") or "").lower()) >= 0.8 * len(chars)
        short = len(text) <= 90 and not text.endswith((".", ",", ";")) and len(text.split()) <= 14
        has_letters = any(ch.isalpha() for ch in text)
        gap = ln["top"] - prev_bottom if prev_bottom is not None else None
        level = ""
        if short and has_letters and size >= body_size * 1.35:
            level = "##"
        elif short and has_letters and (size >= body_size * 1.12 or (bold and len(text) <= 70)):
            level = "###"
        # a heading that wraps onto a second line continues the same heading
        last = next((x for x in reversed(out) if x), "")
        if level and last.startswith(level + " ") and gap is not None and gap < 0.9 * typical:
            idx = len(out) - 1 - [x for x in reversed(out)].index(last)
            out[idx] = f"{last} {text}"
            prev_bottom = ln["bottom"]
            continue
        if gap is not None and gap > 0.9 * typical:
            out.append("")
        if level:
            out += ["", f"{level} {text}", ""]
        else:
            out.append(text)
        prev_bottom = ln["bottom"]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def _page_text(page, body_size: float, stats: dict) -> str:
    vis = _Visibility(page)
    page = page.filter(vis)
    try:
        tables = page.find_tables() or []
    except Exception:  # noqa: BLE001
        tables = []
    boxes = []
    for t in tables:
        try:
            boxes.append(t.bbox)
        except Exception:  # noqa: BLE001
            continue

    def outside(obj, _b=boxes):
        if obj.get("object_type") != "char":
            return True
        cx = (obj.get("x0", 0) + obj.get("x1", 0)) / 2
        cy = (obj.get("top", 0) + obj.get("bottom", 0)) / 2
        return not any(x0 <= cx <= x1 and t <= cy <= b for x0, t, x1, b in _b)

    prose = page.filter(outside) if boxes else page
    words = prose.extract_words(x_tolerance=1.5) or []
    gut = _gutter(words, page.width)
    parts: list[str] = []

    # Tables are placed where they sit on the page (under their heading, in their column) as
    # pseudo-lines, so a table lands in the same chunk as the text that introduces it.
    table_items: list[dict] = []
    for t in tables:
        try:
            md = _table_md(t.extract())
            tx0, ttop, tx1, tbottom = t.bbox
        except Exception:  # noqa: BLE001
            continue
        if md:
            table_items.append({"table": md, "x0": tx0, "x1": tx1, "top": ttop, "bottom": tbottom, "text": ""})
            stats["tables"] += 1

    def lines_in(bbox) -> list[dict]:
        try:
            region = prose.crop(bbox, strict=False) if bbox else prose
            lines = region.extract_text_lines(x_tolerance=1.5, return_chars=True)
        except Exception:  # noqa: BLE001
            lines = []
        for it in table_items:
            cx, cy = (it["x0"] + it["x1"]) / 2, (it["top"] + it["bottom"]) / 2
            if not it.get("used") and (bbox is None or (bbox[0] <= cx <= bbox[2] and bbox[1] <= cy <= bbox[3])):
                it["used"] = True
                lines.append(it)
        return sorted(lines, key=lambda ln: ln["top"])

    if gut is None:
        parts.append(_lines_to_text(lines_in(None), body_size))
    else:
        stats["multi_column_pages"] += 1
        # Split the page into horizontal bands: bands where some word crosses the gutter (titles,
        # full-width figures/footers) are read across; the bands between them are read as left
        # column then right column.
        x0, top0, x1, bottom0 = page.bbox
        spans = [(w["top"] - 1, w["bottom"] + 1) for w in words if w["x0"] < gut < w["x1"]]
        # a table is full-width only if it really covers both columns (one that merely overhangs
        # the gutter belongs to the column holding its centre)
        spans += [(it["top"] - 1, it["bottom"] + 1) for it in table_items
                  if min(gut - it["x0"], it["x1"] - gut) > 0.3 * min(gut - x0, x1 - gut)]
        # a row whose words continue across the gutter at normal word spacing (a title that
        # happens to break there) is full-width too; real columns are separated by a wide gap
        rows: dict[int, list[dict]] = {}
        for w in words:
            rows.setdefault(round(w["top"] / 3), []).append(w)
        for row in rows.values():
            lefts = [w for w in row if w["x1"] <= gut]
            rights = [w for w in row if w["x0"] >= gut]
            if lefts and rights:
                a = max(lefts, key=lambda w: w["x1"])
                b = min(rights, key=lambda w: w["x0"])
                if b["x0"] - a["x1"] < 0.6 * max(a["bottom"] - a["top"], 1):
                    spans.append((min(w["top"] for w in row) - 1, max(w["bottom"] for w in row) + 1))
        spans.sort()
        merged: list[list[float]] = []
        for a, b in spans:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        cursor = top0
        for a, b in merged + [[bottom0, bottom0]]:
            a, b = max(a, top0), min(b, bottom0)
            if a > cursor + 1:
                parts.append(_lines_to_text(lines_in((x0, cursor, gut, a)), body_size))
                parts.append(_lines_to_text(lines_in((gut, cursor, x1, a)), body_size))
            if b > a:
                parts.append(_lines_to_text(lines_in((x0, a, x1, b)), body_size))
            cursor = max(cursor, b)
    parts += [it["table"] for it in table_items if not it.get("used")]  # safety net: never drop a table
    text = "\n\n".join(p for p in parts if p.strip())
    stats["hidden_chars"] += vis.hidden
    try:
        imgs = page.images or []
    except Exception:  # noqa: BLE001
        imgs = []
    if imgs:
        stats["images"] += len(imgs)
        area = page.width * page.height or 1
        covered = sum(max(0, (i["x1"] - i["x0"])) * max(0, (i["bottom"] - i["top"])) for i in imgs)
        if len(text.strip()) < 40 and covered > 0.3 * area:
            stats["image_only_pages"] += 1
    return text


def extract_pdf(data: bytes, max_pages: int, max_chars: int) -> dict:
    import pdfplumber

    stats = {"pages": 0, "pages_read": 0, "multi_column_pages": 0, "tables": 0, "images": 0,
             "image_only_pages": 0, "hidden_chars": 0, "empty_pages": 0}
    out: list[str] = []
    total = 0
    truncated = False
    try:
        pdf = pdfplumber.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        msg = repr(exc).lower()
        if "password" in msg or "encrypt" in msg:
            return {"error": "encrypted", "message": "This PDF is password-protected. Remove the password and upload it again."}
        return {"error": "unreadable", "message": "This PDF could not be read (it may be damaged)."}
    with pdf:
        pages = pdf.pages
        stats["pages"] = len(pages)
        # body font size = most common glyph size over the first pages (headings are larger)
        sizes: dict[float, int] = {}
        for p in pages[: min(5, len(pages))]:
            for c in p.chars[:6000]:
                s = round(c.get("size") or 0, 1)
                if s >= 2:
                    sizes[s] = sizes.get(s, 0) + 1
        body = max(sizes, key=sizes.get) if sizes else 10.0
        for i, page in enumerate(pages):
            if i >= max_pages or total >= max_chars:
                truncated = True
                break
            try:
                text = _page_text(page, body, stats)
            except Exception:  # noqa: BLE001 — one bad page never sinks the document
                text = ""
            stats["pages_read"] += 1
            if not text.strip():
                stats["empty_pages"] += 1
                continue
            out.append(text)
            total += len(text)
            if hasattr(page, "close"):
                page.close()  # free the page's parsed objects; long PDFs otherwise grow memory
    text = "\n\n".join(out)
    if len(text) > max_chars:
        text, truncated = text[:max_chars], True
    if not text.strip() and stats["image_only_pages"]:
        return {"error": "scanned", "message": "This PDF is scanned images with no text layer, so there is nothing to read. Run it through OCR first (e.g. \"Save as searchable PDF\") and upload that."}
    return {"text": text, "truncated": truncated, "stats": stats}


# ── DOCX ─────────────────────────────────────────────────────────────────────


def extract_docx(data: bytes, max_chars: int) -> dict:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception:  # noqa: BLE001
        return {"error": "unreadable", "message": "This Word file could not be read (it may be damaged or not a real .docx)."}
    stats = {"paragraphs": 0, "tables": 0, "images": 0, "hidden_runs": 0}
    out: list[str] = []
    total = 0
    truncated = False
    body = document.element.body
    for child in body.iterchildren():
        if total >= max_chars:
            truncated = True
            break
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, document)
            runs = []
            for r in p.runs:
                f = r.font
                hidden = bool(f.hidden) or (f.size is not None and f.size.pt < 2)
                try:
                    rgb = f.color.rgb if f.color is not None and f.color.type is not None else None
                except Exception:  # noqa: BLE001
                    rgb = None
                if rgb is not None and str(rgb).upper() == "FFFFFF":
                    hidden = True
                if hidden:
                    stats["hidden_runs"] += 1
                    continue
                runs.append(r.text)
            stats["images"] += len(child.findall(".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"))
            text = "".join(runs).strip() if p.runs else p.text.strip()
            if not text:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            m = re.match(r"(?i)heading\s*(\d)", style)
            if m:
                text = "#" * min(int(m.group(1)) + 1, 6) + " " + text
            elif style.lower() == "title":
                text = "# " + text
            elif "list" in style.lower():
                text = "- " + text
            out.append(text)
            stats["paragraphs"] += 1
        elif tag == "tbl":
            t = Table(child, document)
            try:
                rows = [[c.text.strip() for c in row.cells] for row in t.rows]
            except Exception:  # noqa: BLE001
                continue
            md = _table_md(rows)
            if md:
                # keep the table in the same block as the paragraph introducing it (see PDF path)
                if out and not out[-1].startswith(("#", "|")):
                    out[-1] = out[-1] + "\n" + md
                else:
                    out.append(md)
                stats["tables"] += 1
        else:
            continue
        total += len(out[-1]) if out else 0
    text = "\n\n".join(out)
    if len(text) > max_chars:
        text, truncated = text[:max_chars], True
    return {"text": text, "truncated": truncated, "stats": stats}


# ── text / markdown ──────────────────────────────────────────────────────────


def extract_text(data: bytes, max_chars: int) -> dict:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = data.decode("utf-16", errors="replace")
    else:
        text = data.decode("utf-8-sig", errors="replace")
    truncated = len(text) > max_chars
    return {"text": text[:max_chars], "truncated": truncated, "stats": {}}


def main() -> None:
    kind, max_pages, max_chars, cpu_s, mem_mb = sys.argv[1], *map(int, sys.argv[2:6])
    _limit(cpu_s, mem_mb)
    data = sys.stdin.buffer.read()
    try:
        if kind == "pdf":
            res = extract_pdf(data, max_pages, max_chars)
        elif kind == "docx":
            res = extract_docx(data, max_chars)
        else:
            res = extract_text(data, max_chars)
    except MemoryError:
        res = {"error": "too_complex", "message": "This file is too complex to process safely."}
    except Exception:  # noqa: BLE001 — never leak a traceback to the caller
        res = {"error": "unreadable", "message": "This file could not be read."}
    sys.stdout.write(json.dumps(res))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
