"""Source verification: literal same-page quote check across independent engines,
value anchoring, paraphrase detection. A matched quote proves only that the text exists
on that page — it does not prove the semantic correctness of the record."""
from __future__ import annotations

import datetime as dt
import re

from .pdftext import norm_rag, norm_solar

PARAPHRASE_RE = re.compile(r"^(table|tab\.|figure|fig\.|таблица|рисунок|рис\.)\s*\w+[,;:]?\s*(row|line|строка|столбец|column|col)\b", re.I)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def numeric_tokens(raw: str) -> list[str]:
    return re.findall(r"\d+(?:[.,]\d+)?", raw or "")


def verify_quote(doc: dict, page: int | None, fragment: str, raw_value: str = "") -> dict:
    """Return a structured, timestamped check record."""
    rec = {"check": "quote", "ts": now(), "page": page, "fragment": fragment}
    if not fragment:
        rec.update(outcome="no_fragment", detail="no verbatim fragment; table/figure locator requires visual review")
        return rec
    if not page or not doc or not 1 <= page <= doc["page_count"]:
        rec.update(outcome="bad_page", detail=f"source_page {page} outside PDF (1..{doc and doc['page_count']})")
        return rec
    p = doc["pages"][page - 1]
    needle = norm_rag(fragment)
    engines = {"pymupdf": p.get("pymupdf") or "", "pypdf": p.get("pypdf") or ""}
    if p.get("ocr"):
        engines["ocr"] = p["ocr"]
    matched = [e for e, t in engines.items() if needle and needle in norm_rag(t)]
    solar_compat = bool(needle) and norm_solar(fragment) in norm_solar(p.get("pypdf") or "")
    other_pages = []
    if not matched:
        for q in doc["pages"]:
            if q["page"] == page:
                continue
            for t in (q.get("pymupdf"), q.get("pypdf"), q.get("ocr")):
                if t and needle in norm_rag(t):
                    other_pages.append(q["page"])
                    break
    paraphrase = bool(PARAPHRASE_RE.match(fragment.strip()))
    if matched:
        outcome = "matched_ocr_only" if matched == ["ocr"] else "matched"
    elif other_pages:
        outcome = "wrong_page"
    elif not p.get("has_text_layer") and not p.get("ocr"):
        outcome = "no_text_layer"
    else:
        outcome = "not_found"
    rec.update(outcome=outcome, engines=matched, other_pages=other_pages[:10], paraphrase_suspect=paraphrase,
               solar_checker_compatible=solar_compat, ocr_page=not p.get("has_text_layer"))
    # value anchoring: does the fragment itself contain the number? (necessary, not sufficient)
    toks = numeric_tokens(raw_value)
    if toks:
        frag_n = norm_rag(fragment).replace(",", ".")
        rec["value_in_fragment"] = all(t.replace(",", ".").lstrip("0") in frag_n for t in toks)
    return rec


def find_fragment(doc: dict, page: int, candidates: list[str]) -> str | None:
    """Pick the first candidate that is literally present on the page (used by extractors to
    snap an LLM-proposed quote to the actual page text without inventing text)."""
    p = doc["pages"][page - 1]
    texts = [norm_rag(t) for t in (p.get("pymupdf"), p.get("pypdf"), p.get("ocr")) if t]
    for c in candidates:
        n = norm_rag(c or "")
        if n and any(n in t for t in texts):
            return c
    return None


def extend_fragment(doc: dict, page: int, fragment: str, raw_value: str, max_len: int = 400) -> dict | None:
    """A quote that is found on the page but stops before the number ("... obtains Recall@10 =" with the value on the next
    line) is widened to the sentence(s) of the same page and the same text engine that contain both the quote and the
    number. Pages and engines are never mixed; the result is accepted only if it passes verify_quote again."""
    toks = numeric_tokens(raw_value)
    if not fragment or not toks or not doc or not page or not 1 <= page <= doc["page_count"]:
        return None
    p = doc["pages"][page - 1]
    frag_flat = re.sub(r"\s+", " ", fragment).strip()
    for engine in ("pymupdf", "pypdf"):
        text = p.get(engine) or ""
        flat = re.sub(r"\s+", " ", text)
        pos = flat.find(frag_flat)
        if pos < 0:
            low = flat.lower().find(frag_flat.lower())
            if low < 0:
                continue
            pos = low
        end = pos + len(frag_flat)
        starts = [m.end() for m in re.finditer(r"[.!?]\s+(?=[A-Z(\[])", flat[:pos])]
        s0 = starts[-1] if starts else max(0, pos - 200)
        m = re.search(r"[.!?](?=\s|$)", flat[end:])
        while m and end + m.start() + 1 < len(flat) and flat[end + m.start() + 1:end + m.start() + 2].isdigit():
            m = re.search(r"[.!?](?=\s|$)", flat[end + m.end():])
        e0 = end + m.end() if m else min(len(flat), end + 200)
        cand = flat[s0:e0].strip()
        if len(cand) > max_len:
            continue
        num = norm_rag(cand).replace(",", ".")
        if not all(t.replace(",", ".").lstrip("0") in num for t in toks):
            continue
        rec = verify_quote(doc, page, cand, raw_value)
        if rec.get("outcome") == "matched" and rec.get("value_in_fragment"):
            return {"fragment": cand, "engine": engine, "check": rec}
    return None
