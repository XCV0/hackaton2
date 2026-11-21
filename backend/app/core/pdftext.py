"""PDF text layer access: independent pypdf / PyMuPDF extraction, OCR for image-only pages.

PDF content is treated strictly as data. Source PDFs are opened read-only and never modified.
Text from different engines or different pages is never concatenated into a quote.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata

import pymupdf
from pypdf import PdfReader

from ..settings import CACHE_DIR

OCR_DPI = 300
OCR_LANG = "eng"
TEXT_LAYER_MIN_CHARS = 40  # page with fewer printable chars is treated as image-only


def norm_rag(text: str) -> str:
    """Identical to the official RAG checker: Unicode NFKC, soft hyphen, end-of-line hyphenation, whitespace."""
    text = unicodedata.normalize("NFKC", text).replace("­", "")
    text = re.sub(r"(?<=\w)-\s*\r?\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def norm_solar(text: str) -> str:
    """Identical to the official domain-1 checker normalisation (used only for its compatibility check)."""
    s = text.replace("ﬁ", "fi").replace("ﬂ", "fl").replace("ﬀ", "ff").replace("−", "-").replace("–", "-")
    return re.sub(r"[^a-z0-9.%]+", "", s.lower())


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def tesseract_path() -> str | None:
    for cand in [shutil.which("tesseract"), "/opt/homebrew/bin/tesseract", "/usr/local/bin/tesseract"]:
        if cand and pathlib.Path(cand).exists():
            return cand
    return None


def tesseract_version() -> str | None:
    exe = tesseract_path()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20)
        return (out.stdout or out.stderr).splitlines()[0]
    except Exception:
        return None


def cache_dir(domain: str, pid: str) -> pathlib.Path:
    d = CACHE_DIR / domain / pid
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ocr_png(png: pathlib.Path) -> tuple[str, list[dict], float | None]:
    """Run Tesseract twice on the same image: plain text exactly as the official checker
    (psm 3, stdout) and TSV for word boxes/confidences (used only for highlighting/diagnostics)."""
    exe = tesseract_path()
    if not exe:
        raise RuntimeError("Tesseract is not installed")
    txt = subprocess.run([exe, str(png), "stdout", "-l", OCR_LANG, "--psm", "3"],
                         capture_output=True, encoding="utf-8", errors="replace", check=True, timeout=180).stdout or ""
    tsv = subprocess.run([exe, str(png), "stdout", "-l", OCR_LANG, "--psm", "3", "tsv"],
                         capture_output=True, encoding="utf-8", errors="replace", check=True, timeout=180).stdout or ""
    words, confs = [], []
    for line in tsv.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12 or not parts[11].strip():
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        x, y, w, h = map(int, parts[6:10])
        words.append({"t": parts[11], "c": conf, "b": [x, y, x + w, y + h], "line": f"{parts[2]}.{parts[3]}.{parts[4]}"})
        if conf >= 0:
            confs.append(conf)
    return txt, words, (sum(confs) / len(confs) if confs else None)


def extract_document(pdf_path: pathlib.Path, domain: str, pid: str, *, do_ocr: bool = True, force: bool = False) -> dict:
    """Return cached per-page text variants and diagnostics for one PDF."""
    out = cache_dir(domain, pid) / "pages.json"
    if out.exists() and not force:
        doc = json.loads(out.read_text())
        if not do_ocr or all(p.get("ocr_done") or p["has_text_layer"] for p in doc["pages"]):
            return doc
    t0 = time.time()
    try:
        pypdf_pages = [p.extract_text() or "" for p in PdfReader(str(pdf_path)).pages]
        pypdf_error = None
    except Exception as exc:  # recorded, not hidden
        pypdf_pages, pypdf_error = None, str(exc)
    pages = []
    with pymupdf.open(str(pdf_path)) as document:
        meta = document.metadata or {}
        for i, page in enumerate(document):
            mu = page.get_text() or ""
            pp = pypdf_pages[i] if pypdf_pages and i < len(pypdf_pages) else ""
            printable = len(re.sub(r"\s", "", norm_rag(mu))) + 0
            has_text = printable >= TEXT_LAYER_MIN_CHARS or len(re.sub(r"\s", "", norm_rag(pp))) >= TEXT_LAYER_MIN_CHARS
            pages.append({
                "page": i + 1,
                "width": page.rect.width,
                "height": page.rect.height,
                "pymupdf": mu,
                "pypdf": pp,
                "chars": printable,
                "images": len(page.get_images()),
                "has_text_layer": has_text,
                "ocr": None, "ocr_words": None, "ocr_conf": None, "ocr_engine": None, "ocr_done": False,
            })
        page_count = len(document)
    if pypdf_pages is not None and len(pypdf_pages) != page_count:
        pypdf_error = f"page count disagreement pypdf={len(pypdf_pages)} pymupdf={page_count}"
    doc = {"pid": pid, "domain": domain, "path": str(pdf_path), "page_count": page_count,
           "pypdf_error": pypdf_error, "metadata": meta, "parse_seconds": round(time.time() - t0, 2), "pages": pages}
    if do_ocr:
        run_ocr(doc, pdf_path)
    doc["text_layer_pages"] = sum(1 for p in pages if p["has_text_layer"])
    doc["is_scan"] = doc["text_layer_pages"] == 0
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc))  # ascii escapes keep lone surrogates from pypdf faithfully
    tmp.replace(out)
    return doc


def run_ocr(doc: dict, pdf_path: pathlib.Path) -> None:
    """OCR only pages without a usable text layer. The PDF is rendered, never modified."""
    exe = tesseract_path()
    todo = [p for p in doc["pages"] if not p["has_text_layer"] and not p.get("ocr_done")]
    if not todo:
        return
    if not exe:
        for p in todo:
            p["ocr_error"] = "Tesseract not installed: page left unverified"
        return
    version = tesseract_version()
    with pymupdf.open(str(pdf_path)) as document, tempfile.TemporaryDirectory(prefix="viniti_ocr_") as tmp:
        for p in todo:
            t0 = time.time()
            png = pathlib.Path(tmp) / f"p{p['page']}.png"
            document[p["page"] - 1].get_pixmap(dpi=OCR_DPI, colorspace=pymupdf.csRGB, alpha=False).save(png)
            try:
                txt, words, conf = _ocr_png(png)
                p.update(ocr=txt, ocr_words=words, ocr_conf=conf, ocr_done=True,
                         ocr_engine=f"{version}; lang={OCR_LANG}; psm=3; dpi={OCR_DPI}",
                         ocr_seconds=round(time.time() - t0, 1))
            except Exception as exc:
                p.update(ocr_error=str(exc))


def page_variants(doc: dict, page_no: int) -> dict[str, str]:
    """Independent same-page text variants (never merged)."""
    if not 1 <= page_no <= doc["page_count"]:
        return {}
    p = doc["pages"][page_no - 1]
    v = {"pymupdf": p["pymupdf"], "pypdf": p["pypdf"]}
    if p.get("ocr"):
        v["ocr"] = p["ocr"]
    return v


def best_text(doc: dict, page_no: int) -> tuple[str, str]:
    p = doc["pages"][page_no - 1]
    if p["has_text_layer"]:
        return p["pymupdf"] or p["pypdf"], "pymupdf"
    if p.get("ocr"):
        return p["ocr"], "ocr"
    return "", "none"


def render_page_png(pdf_path: pathlib.Path, domain: str, pid: str, page_no: int, dpi: int = 110) -> pathlib.Path:
    out = cache_dir(domain, pid) / f"page_{page_no}_{dpi}.png"
    if not out.exists():
        with pymupdf.open(str(pdf_path)) as document:
            document[page_no - 1].get_pixmap(dpi=dpi, alpha=False).save(out)
    return out


DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)


def find_doi(doc: dict) -> str | None:
    for p in doc["pages"][:2]:
        txt = p["pymupdf"] or p.get("ocr") or ""
        m = DOI_RE.search(txt)
        if m:
            return m.group(1).rstrip(".,;)]")
    return None
