"""Page X-ray: where every extracted value sits on a PDF page, and which printed numbers nobody extracted.
Boxes are in PDF points (72 dpi page space); for scans they come from OCR word boxes."""
from __future__ import annotations

import re

import pymupdf

from . import segment as S
from .pdftext import norm_rag

NUM = re.compile(r"^[(\[]?[-−–+±]?\d*[.,]?\d+(?:[eE][-−+]?\d+)?[)\]]?[%*†‡§,;:]*$")


def _num_key(t: str) -> str:
    t = t.replace("−", "-").replace("–", "-").strip("()[]*†‡§,;:%±+")
    t = t.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", t) else t.replace(",", ".")
    if t.startswith("."):
        t = "0" + t
    try:
        return f"{float(t):.10g}"
    except ValueError:
        return ""


def _inside(b, r, pad=2.0):
    cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
    return r[0] - pad <= cx <= r[2] + pad and r[1] - pad <= cy <= r[3] + pad


def page_words(doc, pdf_path, page):
    return [w for w in S.page_words(doc, str(pdf_path), page) if w.t.strip()]


def number_words(words):
    """Printed numbers on the page (single tokens), with their visual line text."""
    lines = S.group_lines(words, ytol=3.0)
    out = []
    for ln in lines:
        lt = ln.text
        for w in ln.words:
            if NUM.match(w.t) and re.search(r"\d", w.t) and _num_key(w.t):
                out.append({"text": w.t, "key": _num_key(w.t), "box": [w.x0, w.y0, w.x1, w.y1], "line": lt})
    return out


def locate(rec_data: dict, evidence: dict, nums: list, frag_rects: list) -> tuple[list | None, str]:
    """Best box for one extracted value: table cell/row geometry, then the number inside the quoted fragment,
    then the same number elsewhere on the page (approximate)."""
    if evidence.get("cell_bbox"):
        return list(evidence["cell_bbox"]), "cell"
    key = _num_key(re.findall(r"[-−]?\d[\d.,]*|\.\d+", rec_data.get("raw_value") or "")[0]) if re.search(r"\d", rec_data.get("raw_value") or "") else ""
    if evidence.get("row_bbox"):
        return list(evidence["row_bbox"]), "row"
    if not key:
        return None, ""
    same = [n for n in nums if n["key"] == key]
    for r in frag_rects:
        hit = [n for n in same if _inside(n["box"], r, pad=4)]
        if hit:
            return hit[0]["box"], "quote"
    if len(same) == 1:
        return same[0]["box"], "value"
    if same:
        return same[0]["box"], "value-ambiguous"
    return None, ""


def fragment_rects(pdf_path, page, fragment, has_text_layer):
    if not fragment or not has_text_layer:
        return []
    with pymupdf.open(str(pdf_path)) as d:
        pg = d[page - 1]
        for cand in (fragment, fragment[:60], fragment[-50:]):
            cand = norm_rag(cand)
            if len(cand) >= 3:
                found = pg.search_for(cand)
                if found:
                    return [[q.x0, q.y0, q.x1, q.y1] for q in found[:6]]
    return []
