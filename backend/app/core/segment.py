"""Page segmentation: lines with geometry, section headings, table/figure captions, table grids.
Works on the native text layer (PyMuPDF words) and on OCR word boxes for scanned pages."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

NUM_RE = re.compile(r"^[(\[]?[-−–+]?\d*[.,]?\d+(?:[eE][-−+]?\d+)?[)\]]?[%*†‡§]*$")
CAPTION_RE = re.compile(r"^\s*(Table|TABLE|Tab\.|Figure|FIGURE|Fig\.|FIG\.)\s*([0-9]+|[IVXL]+)\b[.:|]?", re.U)
SECTION_WORDS = ["abstract", "introduction", "related work", "background", "method", "methods", "methodology",
                 "experimental", "experimental section", "experiments", "experiment", "results", "results and discussion",
                 "discussion", "evaluation", "conclusion", "conclusions", "references", "acknowledgements",
                 "acknowledgments", "materials and methods", "appendix", "limitations", "analysis", "experimental setup"]
HEAD_RE = re.compile(r"^((\d+(\.\d+){0,3}\.?)|([IVX]+\.)|([A-H]\.))\s+[A-Z][A-Za-z][^.]{1,80}$")


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    t: str


@dataclass
class Line:
    words: list = field(default_factory=list)

    @property
    def text(self):
        return " ".join(w.t for w in self.words)

    @property
    def bbox(self):
        return (min(w.x0 for w in self.words), min(w.y0 for w in self.words),
                max(w.x1 for w in self.words), max(w.y1 for w in self.words))

    @property
    def yc(self):
        b = self.bbox
        return (b[1] + b[3]) / 2


def is_num(t: str) -> bool:
    t = t.replace("−", "-").replace("–", "-").strip("*†‡§")
    return bool(NUM_RE.match(t))


def page_words(doc: dict, pdf_path: str, page_no: int) -> list[Word]:
    p = doc["pages"][page_no - 1]
    if p["has_text_layer"]:
        with pymupdf.open(pdf_path) as d:
            ws = d[page_no - 1].get_text("words")
        return [Word(w[0], w[1], w[2], w[3], w[4]) for w in ws]
    scale = 72.0 / 300.0
    return [Word(w["b"][0] * scale, w["b"][1] * scale, w["b"][2] * scale, w["b"][3] * scale, w["t"])
            for w in (p.get("ocr_words") or []) if w["c"] >= 0 and w["t"].strip()]


def group_lines(words: list[Word], ytol: float = 3.0) -> list[Line]:
    """Group words into visual lines (column-aware: a big horizontal gap splits a line)."""
    words = sorted(words, key=lambda w: ((w.y0 + w.y1) / 2, w.x0))
    rows: list[list[Word]] = []
    for w in words:
        yc = (w.y0 + w.y1) / 2
        if rows and abs(((rows[-1][0].y0 + rows[-1][0].y1) / 2) - yc) <= ytol:
            rows[-1].append(w)
        else:
            rows.append([w])
    lines = []
    for r in rows:
        r.sort(key=lambda w: w.x0)
        cur = [r[0]]
        for w in r[1:]:
            if w.x0 - cur[-1].x1 > 40:  # column gutter
                lines.append(Line(cur))
                cur = [w]
            else:
                cur.append(w)
        lines.append(Line(cur))
    return lines


def sections(doc: dict, pdf_path: str) -> dict[int, list[tuple[float, str]]]:
    """page -> [(y, heading)] in reading order."""
    out = {}
    for p in doc["pages"]:
        heads = []
        try:
            lines = group_lines(page_words(doc, pdf_path, p["page"]))
        except Exception:
            lines = []
        for ln in lines:
            t = ln.text.strip()
            low = re.sub(r"^((\d+(\.\d+)*\.?)|([IVX]+\.))\s*", "", t).strip(" .:").lower()
            if len(t) < 90 and (HEAD_RE.match(t) and not re.search(r"\d{3,}|=|%", t) or low in SECTION_WORDS):
                heads.append((ln.bbox[1], t))
        out[p["page"]] = heads
    return out


def section_for(secs: dict, page: int, y: float | None = None) -> str:
    cand = ""
    for pg in sorted(secs):
        for (yy, h) in secs[pg]:
            if pg < page or (pg == page and (y is None or yy <= y)):
                cand = h
    return cand


def captions(doc: dict, pdf_path: str, page_no: int, lines: list[Line] | None = None) -> list[dict]:
    lines = lines if lines is not None else group_lines(page_words(doc, pdf_path, page_no))
    out = []
    for ln in lines:
        m = CAPTION_RE.match(ln.text)
        if m:
            kind = "table" if m.group(1).lower().startswith("tab") else "figure"
            out.append({"kind": kind, "label": f"{'Table' if kind == 'table' else 'Figure'} {m.group(2)}",
                        "text": ln.text, "bbox": ln.bbox, "page": page_no})
    return out


def parse_table_grid(lines: list[Line], caption: dict, page_height: float) -> dict | None:
    """Heuristic geometric table parser near a caption. Returns rows of cells with bboxes.
    It is deliberately conservative: anything ambiguous is dropped (precision over recall)."""
    cx0, cy0, cx1, cy1 = caption["bbox"]
    width_lo, width_hi = cx0 - 20, max(cx1, cx0 + 200) + 260

    def numeric_share(ln):
        toks = [w.t for w in ln.words]
        return sum(is_num(t.rstrip("%")) for t in toks) / max(1, len(toks))

    def collect(direction):
        cand = sorted([ln for ln in lines if ln.bbox[0] >= width_lo - 5 and ln.bbox[0] <= width_hi
                       and ((ln.bbox[3] <= cy0 + 1) if direction < 0 else (ln.bbox[1] >= cy1 - 1))],
                      key=lambda l: l.yc, reverse=direction < 0)
        region, last_y, nums = [], cy0 if direction < 0 else cy1, 0
        for ln in cand:
            gap = abs(ln.yc - last_y)
            if gap > 38:
                break
            share = numeric_share(ln)
            if len(ln.text) > 140 and share < 0.15:
                break  # prose
            region.append(ln)
            nums += share > 0.3
            last_y = ln.yc
        return region, nums

    up, nu = collect(-1)
    down, nd = collect(+1)
    region = up if nu >= nd else down
    if max(nu, nd) < 2:
        return None
    region = sorted(region, key=lambda l: l.yc)
    # merge lines on the same y (multi-column split lines)
    rows: list[list[Word]] = []
    for ln in region:
        if rows and abs(((rows[-1][0].y0 + rows[-1][0].y1) / 2) - ln.yc) < 3:
            rows[-1].extend(ln.words)
        else:
            rows.append(list(ln.words))
    for r in rows:
        r.sort(key=lambda w: w.x0)
    data_rows = [r for r in rows if sum(is_num(w.t.rstrip("%")) for w in r) >= 1 and
                 sum(is_num(w.t.rstrip("%")) for w in r) / len(r) >= 0.3]
    if len(data_rows) < 2:
        return None
    first_data_y = min((r[0].y0 for r in data_rows))
    header_rows = [r for r in rows if r[0].y0 < first_data_y - 1]
    # column anchors from numeric cells
    xs = sorted(((w.x0 + w.x1) / 2) for r in data_rows for w in r if is_num(w.t.rstrip("%")))
    cols: list[list[float]] = []
    for x in xs:
        if cols and x - cols[-1][-1] < 14:
            cols[-1].append(x)
        else:
            cols.append([x])
    centers = [sum(c) / len(c) for c in cols if len(c) >= max(2, len(data_rows) // 3)]
    if not centers:
        return None

    def col_of(w):
        xc = (w.x0 + w.x1) / 2
        best = min(range(len(centers)), key=lambda i: abs(centers[i] - xc))
        return best if abs(centers[best] - xc) < 22 else None

    header_labels = ["" for _ in centers]
    spans = ["" for _ in centers]
    for hr in header_rows:
        for w in hr:
            xc = (w.x0 + w.x1) / 2
            near = min(range(len(centers)), key=lambda i: abs(centers[i] - xc))
            if abs(centers[near] - xc) < 25:
                header_labels[near] = (header_labels[near] + " " + w.t).strip()
            else:
                # spanning header word: attach to all columns to its right until next span word
                for i, c in enumerate(centers):
                    if c >= w.x0 - 5:
                        spans[i] = (spans[i] + " " + w.t).strip() if c - w.x0 < 220 else spans[i]
    out_rows = []
    for r in data_rows:
        label_words = [w for w in r if not is_num(w.t.rstrip("%")) and (w.x1 < centers[0] - 8)]
        cells = []
        for w in r:
            if not is_num(w.t.rstrip("%")):
                continue
            ci = col_of(w)
            if ci is None:
                continue
            cells.append({"col": ci, "value": w.t, "bbox": (w.x0, w.y0, w.x1, w.y1)})
        out_rows.append({"label": " ".join(w.t for w in label_words).strip(), "cells": cells,
                         "y": r[0].y0, "bbox": (min(w.x0 for w in r), min(w.y0 for w in r), max(w.x1 for w in r), max(w.y1 for w in r))})
    return {"caption": caption, "columns": [{"header": header_labels[i], "span": spans[i]} for i in range(len(centers))],
            "rows": out_rows, "header_text": " | ".join(" ".join(w.t for w in hr) for hr in header_rows)}
