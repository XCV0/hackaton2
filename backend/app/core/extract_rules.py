"""Node R: deterministic, offline extractor (tables by geometry + textual patterns).

It is independent from the LLM nodes (different method, no model), favours precision, and
only emits values whose number is physically present on the page. Every value carries the
evidence used (table/row/column/cell bbox or text window). Domain specifics are delegated to
small adapters driven by domains/<id>.yaml."""
from __future__ import annotations

import re

from . import domain as D
from . import segment as S
from .pdftext import best_text, norm_rag
from .quotes import find_fragment

NODE = "R-rules"
NODE_VERSION = "rules-1.0"

AGG = [(re.compile(r"\b(champion|best|record|highest|maximum|max\.?)\b", re.I), "champion"),
       (re.compile(r"\b(average|mean|avg\.?)\b", re.I), "mean"),
       (re.compile(r"\bmedian\b", re.I), "median")]
SCAN = [(re.compile(r"\b(reverse|backward|RS|FB[–-]SC)\b"), "reverse"), (re.compile(r"\b(forward|FS|SC[–-]FB)\b"), "forward")]
CITE_RE = re.compile(r"\[(\d+(?:\s*[–,-]\s*\d+)*)\]")
DELTA_RE = re.compile(r"(↑|↓|\(\s*[+−-]\s*\d|\bby\b\s*$|improv|gain|drop|decreas|increas)", re.I)

RAG_DATASETS = ["HotpotQA", "2WikiMultihopQA", "2Wiki", "2WikiMQA", "MuSiQue", "NQ", "Natural Questions", "TriviaQA", "TQA",
                "PopQA", "WebQuestions", "WebQ", "SQuAD", "MS MARCO", "MSMARCO", "BEIR", "FEVER", "ASQA", "ELI5", "StrategyQA",
                "Bamboogle", "MultiHop-RAG", "CRAG", "RGB", "PubMedQA", "BioASQ", "MedQA", "FinQA", "TAT-QA", "NarrativeQA",
                "QASPER", "MMLU", "ARC", "TruthfulQA", "WoW", "KILT", "LongBench", "CoQA", "QuAC", "TREC", "NFCorpus",
                "SciFact", "FiQA", "ArguAna", "Touche", "DBPedia", "Climate-FEVER", "HotPotQA", "IIRC", "Wikipedia"]
RAG_METRIC_TOKENS = ["exact match", "em", "f1", "acc", "acc.", "accuracy", "precision", "recall", "mrr", "ndcg", "hit", "hits",
                     "map", "rouge-l", "rouge-1", "rouge-2", "rougel", "bleu", "bertscore", "faithfulness", "latency", "tokens"]


def _num(raw: str) -> tuple[float | None, str]:
    """Parse a printed number without changing its meaning. Returns (value, note)."""
    t = raw.strip().replace("−", "-").replace("–", "-").strip("*†‡§()[]")
    t = t.rstrip("%")
    note = ""
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+(\.\d+)?", t):
        t = t.replace(",", "")
        note = "comma read as thousands separator"
    elif re.fullmatch(r"-?\d+,\d+", t):
        t = t.replace(",", ".")
        note = "comma read as decimal separator"
    if t.startswith("."):
        t = "0" + t
    if t.startswith("-."):
        t = "-0" + t[1:]
    try:
        return float(t), note
    except ValueError:
        return None, ""


def _fmt(v: float) -> str:
    s = f"{v:.10g}"
    return s


def _agg(text: str) -> str:
    for rx, v in AGG:
        if rx.search(text):
            return v
    return ""


def _scan(text: str) -> str:
    for rx, v in SCAN:
        if rx.search(text):
            return v
    return ""


def _window(text: str, start: int, end: int, before: int = 70, after: int = 40) -> str:
    a = max(0, start - before)
    b = min(len(text), end + after)
    # snap to whitespace so we do not cut words, stay on the raw page text (verbatim)
    while a > 0 and not text[a - 1].isspace():
        a -= 1
    while b < len(text) and not text[b].isspace():
        b += 1
    frag = text[a:b].strip()
    # never end/start on a word split by end-of-line hyphenation (normalisation would join it)
    frag = re.sub(r"\s*\S*-$", "", frag)
    if a > 0 and re.search(r"-\s*\n\s*$", text[:a]):
        frag = re.sub(r"^\S+\s*", "", frag)
    return frag


# ---------------------------------------------------------------- bibliography / scope
def bibliography(doc: dict, pdf_path: str) -> dict:
    meta = doc.get("metadata") or {}
    first, _ = best_text(doc, 1)
    title = (meta.get("title") or "").strip()
    if len(title) < 12 or re.search(r"\.(docx?|pdf|tex)$|^untitled|^microsoft word", title, re.I):
        title = ""
    if not title:
        try:
            import pymupdf
            with pymupdf.open(pdf_path) as d:
                blocks = d[0].get_text("dict")["blocks"]
            spans = [(s["size"], s["text"].strip()) for b in blocks for l in b.get("lines", []) for s in l["spans"] if s["text"].strip()]
            if spans:
                mx = max(s for s, _ in spans)
                title = " ".join(t for s, t in spans if s >= mx - 0.5)[:300]
        except Exception:
            title = ""
    doi = None
    m = re.search(r"\b(10\.\d{4,9}/[^\s\"<>]+)", first)
    if m:
        doi = m.group(1).rstrip(".,;)]")
    year = ""
    for src in (meta.get("creationDate") or "", first):
        ym = re.search(r"\b(19[89]\d|20[0-3]\d)\b", src)
        if ym:
            year = ym.group(1)
            break
    authors = (meta.get("author") or "").replace(",", ";").replace(" and ", ";")
    return {"title": title.strip(), "year": year, "DOI": doi or "", "authors": ";".join(a.strip() for a in authors.split(";") if a.strip())}


def scope(domain: str, doc: dict) -> tuple[str, str, str]:
    """Heuristic scope decision -> (in_scope, exclusion_reason, basis). Always marked for review."""
    full = " ".join((p.get("pymupdf") or p.get("ocr") or "") for p in doc["pages"]).lower()
    if domain == "rag":
        ret = len(re.findall(r"retriev", full))
        gen = len(re.findall(r"generat|llm|language model", full))
        if ret >= 5 and gen >= 5:
            return "true", "", f"retrieval mentions={ret}, generation mentions={gen}"
        return "false", "No retrieval-augmented generation system with evaluation found (rule-based scope check)", f"retrieval={ret}, generation={gen}"
    exp = len(re.findall(r"fabricat|spin-coat|deposited|annealed|evaporat|sputter|measured under|j[–-]v curve", full))
    sim = len(re.findall(r"scaps|simulat|numerical model|dft|first-principles|ab initio", full))
    tandem = len(re.findall(r"tandem", full))
    if exp < 3 and sim >= 3:
        return "false", "Только расчёт/моделирование без изготовленных образцов (rule-based)", f"exp={exp}, sim={sim}"
    if tandem > 15:
        return "false", "Тандемный прибор (вне границ области: только однопереходные) (rule-based)", f"tandem={tandem}"
    return "true", "", f"exp={exp}, sim={sim}, tandem={tandem}"


# ---------------------------------------------------------------- metric/column interpretation
def _rag_header(col_text: str, span: str, caption: str) -> dict | None:
    text = f"{span} {col_text}".strip()
    low = " " + re.sub(r"[()]", " ", text.lower()) + " "
    metric, k = None, None
    for tok in sorted(RAG_METRIC_TOKENS, key=len, reverse=True):
        m = re.search(r"(?<![a-z])" + re.escape(tok) + r"(\s*@\s*(\d+))?(?![a-z])", low)
        if m:
            metric = text[m.start() - 1:m.end() - 1].strip() if False else tok
            if m.group(2):
                k = int(m.group(2))
            break
    if not metric:
        cl = caption.lower()
        for tok in ["exact match", "em", "f1", "accuracy", "recall", "ndcg", "mrr"]:
            if re.search(r"(?<![a-z])" + re.escape(tok) + r"(?![a-z])", cl):
                metric = tok
                break
    if not metric:
        return None
    mk = re.search(r"(@\s*\d+)", text)
    raw_name = {"em": "EM", "f1": "F1", "acc": "Acc", "acc.": "Acc", "accuracy": "Accuracy", "exact match": "Exact Match",
                "mrr": "MRR", "ndcg": "nDCG", "map": "MAP", "hit": "Hit", "hits": "Hits", "bleu": "BLEU"}.get(metric, metric.title() if metric.islower() else metric)
    if mk:
        raw_name += mk.group(1).replace(" ", "")
    ds = ""
    for d in sorted(RAG_DATASETS, key=len, reverse=True):
        if re.search(r"(?<![A-Za-z0-9])" + re.escape(d) + r"(?![A-Za-z0-9])", text, re.I):
            ds = d
            break
    unit = "%" if "%" in text else ""
    gen = ""
    gm = GEN_RE.search(text)
    if gm:
        gen = gm.group(0).strip()
    return {"metric": raw_name, "k": k, "dataset": ds, "unit": unit, "header": text, "generator": gen}


GEN_RE = re.compile(r"(?i)\b(llama[\w.\-]*(\s*[\d.]+[bm])?(-instruct|-chat)?|gpt-?[\w.\-]+(\s*mini)?|qwen[\w.\-]*(\s*plus)?|mistral[\w.\-]*|mixtral[\w.\-]*|claude[\w.\-]*|gemini[\w.\-]*|flan-t5[\w.\-]*|vicuna[\w.\-]*|phi-?[\w.\-]*|deepseek[\w.\-]*)")


SOLAR_HEAD = [("Voc", r"\bv\s*_?oc\b|open[- ]circuit"), ("Jsc", r"\bj\s*_?sc\b|short[- ]circuit"), ("FF", r"\bff\b|fill factor"),
              ("PCE", r"\bpce\b|η|\befficiency\b"), ("Rsh", r"\br\s*_?sh\b|shunt"), ("Rs", r"\br\s*_?s\b|series resist"),
              ("HI", r"\bhi\b|hysteresis index")]


def _solar_header(col_text: str, span: str) -> dict | None:
    low = col_text.lower()
    for name, rx in SOLAR_HEAD:
        if re.search(rx, low):
            unit = ""
            m = re.search(r"\(([^)]+)\)|\[([^\]]+)\]", col_text)
            u = (m.group(1) or m.group(2)) if m else ""
            u = u.replace("−", "-").replace(" ", "")
            if name == "Voc":
                unit = "mV" if "mv" in u.lower() else ("V" if u else "")
            elif name in ("Jsc",):
                unit = "mA/cm2" if "ma" in u.lower() else ("A/m2" if "a/m" in u.lower() else "")
            elif name in ("PCE", "FF", "HI"):
                unit = "%" if "%" in u else ""
            elif name in ("Rs", "Rsh"):
                unit = "Ohm*cm2" if ("cm" in u.lower() and "k" not in u.lower()) else ("kOhm*cm2" if "k" in u.lower() else "")
            return {"metric": name, "unit": unit, "header": col_text}
    return None


# ---------------------------------------------------------------- extraction
def extract(domain: str, doc: dict, pdf_path: str) -> dict:
    cfg = D.load(domain)
    secs = S.sections(doc, pdf_path)
    out = {"node": NODE, "version": NODE_VERSION, "publication": {}, "entities": {t: [] for t in cfg["entity_tables"]},
           "results": [], "issues": [], "notes": []}
    bib = bibliography(doc, pdf_path)
    ins, reason, basis = scope(domain, doc)
    out["publication"] = {**bib, "in_scope": ins, "exclusion_reason": reason, "_basis": basis}
    if ins == "false":
        return out
    seen_regions = set()
    tables = []
    for p in doc["pages"]:
        pg = p["page"]
        try:
            lines = S.group_lines(S.page_words(doc, pdf_path, pg))
        except Exception as exc:
            out["notes"].append(f"page {pg}: words unavailable: {exc}")
            continue
        for cap in S.captions(doc, pdf_path, pg, lines):
            if cap["kind"] != "table":
                continue
            grid = S.parse_table_grid(lines, cap, p["height"])
            if not grid:
                continue
            key = (pg, tuple(round(r["y"]) for r in grid["rows"][:3]))
            if key in seen_regions:
                continue
            seen_regions.add(key)
            tables.append((pg, grid))
    if domain == "rag":
        _rag_from_tables(out, doc, tables, secs)
        _rag_from_text(out, doc, secs)
    else:
        _solar_from_tables(out, doc, tables, secs)
        _solar_from_text(out, doc, secs)
    return out


def _fragment_for_cell(doc, pg, row_label, value, caption_text, solar=False):
    cands = []
    if row_label:
        cands.append(f"{row_label} {value}")
    cands.append(caption_text[:90])
    cap_short = re.match(r"^((Table|TABLE|Tab\.)\s*[0-9IVXL]+[.:|]?)", caption_text)
    if cap_short:
        cands.append(cap_short.group(1))
    if solar:
        from .pdftext import norm_solar
        pp = norm_solar(doc["pages"][pg - 1].get("pypdf") or "")
        ok = [c for c in cands if c and norm_solar(c) and norm_solar(c) in pp]
        hit = find_fragment(doc, pg, ok)
        if hit:
            return hit
    return find_fragment(doc, pg, cands) or ""


def _rag_from_tables(out, doc, tables, secs):
    ents = out["entities"]
    exp_n = 0
    cfg_by_label, ds_by_name = {}, {}
    task = {"task_id": "T1", "task_type": "", "note": "task type not determined by rule-based node; requires LLM/human"}
    ents["tasks"].append(task)
    for pg, grid in tables:
        cap = grid["caption"]
        cols = [(_rag_header(c["header"], c["span"], cap["text"]), c) for c in grid["columns"]]
        if not any(h for h, _ in cols):
            continue
        exp_n += 1
        eid = f"E{exp_n}"
        ents["experiments"].append({"experiment_id": eid, "evaluation_protocol": cap["text"][:300], "baseline_name": "",
                                    "hardware": "", "latency_ms": "", "tokens_per_query": "", "sample_size": "",
                                    "note": f"{cap['label']}, page {pg} (rule-based: protocol = caption text)"})
        for row in grid["rows"]:
            label = row["label"].strip()
            if not label or len(label) > 80 or not re.search(r"[A-Za-z]", label):
                continue
            for cell in row["cells"]:
                if cell.get("role", "main") != "main":
                    continue  # ± spreads and parenthesised deltas are not separate scores
                h, col = cols[cell["col"]] if cell["col"] < len(cols) else (None, None)
                if not h:
                    continue
                ckey = (label, h.get("generator", ""))
                cid = cfg_by_label.get(ckey)
                if not cid:
                    cid = f"C{len(cfg_by_label) + 1}"
                    cfg_by_label[ckey] = cid
                    ents["configurations"].append({"config_id": cid, "rag_variant": label, "generator_model": h.get("generator", ""),
                                                   "note": f"row label of {cap['label']} p.{pg}" + (f"; generator from column group header" if h.get("generator") else "") + " (rule-based)"})
                val, nnote = _num(cell["value"])
                if val is None:
                    continue
                ds = h["dataset"] or "unspecified"
                if ds not in ds_by_name:
                    ds_by_name[ds] = f"DS{len(ds_by_name) + 1}"
                    ents["datasets"].append({"dataset_id": ds_by_name[ds], "dataset_name": "" if ds == "unspecified" else ds,
                                             "note": "dataset not identifiable from table header" if ds == "unspecified" else "from table header"})
                cited = CITE_RE.search(label)
                frag = _fragment_for_cell(doc, pg, label, cell["value"], cap["text"])
                unit = "%" if (h["unit"] == "%" or cell["value"].endswith("%")) else ""
                out["results"].append({
                    "experiment_id": eid, "config_id": cid, "dataset_id": ds_by_name[ds], "task_id": "T1",
                    "metric_group": "", "metric_name": h["metric"], "metric_variant": "", "metric_direction": "",
                    "metric_k": str(h["k"]) if h["k"] is not None else "", "raw_value": cell["value"], "raw_unit": unit,
                    "value": val, "unit": unit, "aggregation": "", "sample_size": "",
                    "result_origin": "cited" if cited else "primary", "cited_publication_id": f"[{cited.group(1)}]" if cited else "",
                    "source_page": pg, "source_section": S.section_for(secs, pg, row["y"]), "source_table": cap["label"],
                    "source_figure": "", "source_fragment": frag, "extraction_status": "extracted",
                    "note": f"row='{label}'; column='{h['header']}'" + (f"; {nnote}" if nnote else ""),
                    "_evidence": {"kind": "table", "page": pg, "table": cap["label"], "row_label": label,
                                  "col_label": h["header"], "cell_bbox": cell["bbox"], "row_bbox": row["bbox"],
                                  "ocr": not doc["pages"][pg - 1]["has_text_layer"]},
                })


RAG_TEXT_RE = re.compile(
    r"(?P<metric>exact match|EM|F1|accuracy|Recall@\d+|nDCG@\d+|MRR|Hit@\d+|ROUGE-L|BLEU)\s*(?:score)?\s*(?:of|=|:|reaches|reaching|achieves)\s*(?P<val>\d+(?:\.\d+)?)\s*(?P<pct>%?)"
    r"|(?P<val2>\d+(?:\.\d+)?)\s*(?P<pct2>%?)\s*(?P<metric2>EM|F1|accuracy|exact match)\b", re.I)


def _rag_from_text(out, doc, secs):
    ents = out["entities"]
    for p in doc["pages"]:
        text, engine = best_text(doc, p["page"])
        if not text or re.search(r"^\s*references\s*$", text[:200], re.I | re.M) and p["page"] > 3:
            pass
        for m in RAG_TEXT_RE.finditer(text):
            val_s = m.group("val") or m.group("val2")
            metric = m.group("metric") or m.group("metric2")
            pct = m.group("pct") or m.group("pct2") or ""
            frag = _window(text, m.start(), m.end())
            ctx = text[max(0, m.start() - 60):m.end() + 10]
            if CITE_RE.search(ctx):
                origin, cite = "cited", CITE_RE.search(ctx).group(0)
            else:
                origin, cite = "primary", ""
            delta = bool(DELTA_RE.search(text[max(0, m.start() - 25):m.start()]))
            ds = next((d for d in RAG_DATASETS if re.search(r"(?<![A-Za-z0-9])" + re.escape(d) + r"(?![A-Za-z0-9])", frag)), "")
            if not ds:
                continue  # without a dataset the statement cannot be linked: precision first
            if ds not in [d["dataset_name"] for d in ents["datasets"]]:
                ents["datasets"].append({"dataset_id": f"DS{len(ents['datasets']) + 1}", "dataset_name": ds, "note": "from text"})
            dsid = next(d["dataset_id"] for d in ents["datasets"] if d["dataset_name"] == ds)
            if not any(e["experiment_id"] == "ET" for e in ents["experiments"]):
                ents["experiments"].append({"experiment_id": "ET", "evaluation_protocol": "values stated in running text",
                                            "note": "rule-based: textual statements"})
            if not any(c["config_id"] == "CT" for c in ents["configurations"]):
                ents["configurations"].append({"config_id": "CT", "rag_variant": "", "note": "configuration not resolvable from sentence (rule-based)"})
            if not ents["tasks"]:
                ents["tasks"].append({"task_id": "T1", "task_type": "", "note": "rule-based"})
            val, _ = _num(val_s)
            mk = re.search(r"@(\d+)", metric)
            out["results"].append({
                "experiment_id": "ET", "config_id": "CT", "dataset_id": dsid, "task_id": ents["tasks"][0]["task_id"],
                "metric_group": "", "metric_name": metric, "metric_variant": "difference (improvement/drop)" if delta else "",
                "metric_direction": "", "metric_k": mk.group(1) if mk else "", "raw_value": val_s + pct, "raw_unit": "%" if pct else "",
                "value": val, "unit": "%" if pct else "", "aggregation": "", "sample_size": "", "result_origin": origin,
                "cited_publication_id": cite, "source_page": p["page"], "source_section": S.section_for(secs, p["page"]),
                "source_table": "", "source_figure": "", "source_fragment": frag, "extraction_status": "extracted",
                "note": "rule-based text pattern" + ("; value is a difference, not an absolute score" if delta else ""),
                "_evidence": {"kind": "text", "page": p["page"], "engine": engine, "ocr": engine == "ocr"},
            })


def _solar_material(doc) -> dict:
    full = " ".join((p.get("pymupdf") or p.get("ocr") or "") for p in doc["pages"][:4])
    classes = [("perovskite", r"perovskite"), ("CIGS", r"\bCIGS\b|Cu\(In,\s*Ga\)Se"), ("CdTe", r"\bCdTe\b"),
               ("kesterite", r"kesterite|\bCZTS"), ("Sb2Se3", r"Sb2\s*Se3|Sb2\(S,\s*Se\)3|Sb2Se3"), ("thin-film Si", r"a-Si|amorphous silicon|thin-film silicon")]
    counts = {c: len(re.findall(rx, full)) for c, rx in classes}
    cls = max(counts, key=counts.get) if max(counts.values()) else "other"
    return {"material_id": "M1", "material_name_raw": cls, "formula_normalized": "", "material_class": cls,
            "note": f"absorber class by keyword frequency on pages 1-4 (rule-based): {counts}"}


def _solar_from_tables(out, doc, tables, secs):
    ents = out["entities"]
    ents["materials"].append(_solar_material(doc))
    full = " ".join((p.get("pymupdf") or p.get("ocr") or "") for p in doc["pages"])
    am = "AM1.5G" if re.search(r"AM\s*1\.5\s*G?", full) else ""
    inten = "100" if re.search(r"100\s*mW\s*/?\s*cm", full) else ""
    ms = {}

    def meas(direction):
        key = direction or "unspecified"
        if key not in ms:
            mid = f"MS{len(ms) + 1}"
            ms[key] = mid
            ents["measurements"].append({"measurement_id": mid, "device_id": "", "measurement_type": "J-V", "spectrum": am,
                                         "light_intensity": inten, "intensity_unit": "mW/cm2" if inten else "",
                                         "scan_direction": direction, "note": "rule-based; conditions found in paper text" if am else "rule-based"})
        return ms[key]

    dev_by_label = {}
    for pg, grid in tables:
        cap = grid["caption"]
        cols = [_solar_header(c["header"], c["span"]) for c in grid["columns"]]
        if sum(1 for c in cols if c) < 2:
            continue
        cap_agg = _agg(cap["text"])
        cap_scan = _scan(cap["text"])
        for row in grid["rows"]:
            label = row["label"].strip() or (row["cells"][0]["value"] if row["cells"] and not cols[row["cells"][0]["col"]] else "")
            if not label:
                continue
            did = dev_by_label.get(label)
            if not did:
                did = f"DV{len(dev_by_label) + 1}"
                dev_by_label[label] = did
                ents["devices"].append({"device_id": did, "absorber_material_id": "M1", "device_label": label, "device_type": "cell",
                                        "note": f"row label of {cap['label']} p.{pg} (rule-based)"})
            scan = _scan(label) or cap_scan
            mid = meas(scan)
            for m in ents["measurements"]:
                if m["measurement_id"] == mid and did not in m["device_id"].split(";"):
                    m["device_id"] = ";".join(x for x in [m["device_id"], did] if x)
            agg = _agg(label) or cap_agg
            spreads = {c["col"]: c["value"] for c in row["cells"] if c.get("role") == "spread"}
            has_paren = {c["col"] for c in row["cells"] if c.get("role") == "paren"}
            for cell in row["cells"]:
                if cell.get("role") in ("spread", "extra"):
                    continue
                h = cols[cell["col"]] if cell["col"] < len(cols) else None
                if not h:
                    continue
                val, nnote = _num(cell["value"])
                if val is None:
                    continue
                spread = spreads.get(cell["col"], "") if cell.get("role") == "main" else ""
                if cell.get("role") == "paren":
                    nnote = (nnote + "; " if nnote else "") + "value printed in parentheses (often the best device); aggregation not stated"
                unit = h["unit"]
                if h["metric"] in ("FF", "PCE") and not unit:
                    unit = "fraction" if val <= 1 else "%"
                    nnote = (nnote + "; " if nnote else "") + f"unit inferred from magnitude ({unit})"
                if h["metric"] == "Voc" and not unit:
                    unit = "mV" if val > 10 else "V"
                    nnote = (nnote + "; " if nnote else "") + f"unit inferred from magnitude ({unit})"
                cited = CITE_RE.search(label)
                frag = _fragment_for_cell(doc, pg, label, cell["value"], cap["text"], solar=True)
                out["results"].append({
                    "device_id": "" if cited else did, "measurement_id": "" if cited else mid, "material_id": "M1",
                    "metric_name": h["metric"], "raw_value": cell["value"], "raw_unit": unit, "value": val, "unit": unit,
                    "aggregation": agg if cell.get("role") == "main" else "", "spread_value": spread, "n_devices": "", "time_point": "", "time_unit": "",
                    "result_origin": "cited" if cited else "primary", "cited_publication_id": f"[{cited.group(1)}]" if cited else "",
                    "source_page": pg, "source_section": S.section_for(secs, pg, row["y"]), "source_table": cap["label"],
                    "source_figure": "", "source_fragment": frag, "extraction_status": "extracted",
                    "note": f"row='{label}'; column='{h['header']}'" + (f"; {nnote}" if nnote else ""),
                    "_evidence": {"kind": "table", "page": pg, "table": cap["label"], "row_label": label, "col_label": h["header"],
                                  "cell_bbox": cell["bbox"], "row_bbox": row["bbox"], "ocr": not doc["pages"][pg - 1]["has_text_layer"]},
                })


SOLAR_TEXT = [
    ("PCE", re.compile(r"(?:PCE|power conversion efficiency|efficiency|η)\s*(?:\([^)]{0,20}\))?\s*(?:of|=|:|reached|reaching|up to|as high as|was|is)\s*(?:~|≈)?\s*(\d{1,2}(?:\.\d+)?)\s*%", re.I)),
    ("Voc", re.compile(r"(?:V\s*OC|Voc|open[- ]circuit voltage)\s*(?:\([^)]{0,20}\))?\s*(?:of|=|:|was|is)\s*(\d+(?:\.\d+)?)\s*(m?V)\b", re.I)),
    ("Jsc", re.compile(r"(?:J\s*SC|Jsc|short[- ]circuit current(?: density)?)\s*(?:\([^)]{0,20}\))?\s*(?:of|=|:|was|is)\s*(\d+(?:\.\d+)?)\s*(mA\s*/?\s*cm\s*[-−–]?\s*2|mA\s*cm\s*[-−–]\s*2)", re.I)),
    ("FF", re.compile(r"(?:FF|fill factor)\s*(?:\([^)]{0,20}\))?\s*(?:of|=|:|was|is)\s*(\d+(?:\.\d+)?)\s*(%?)", re.I)),
]


def _solar_from_text(out, doc, secs):
    ents = out["entities"]
    if not ents["materials"]:
        ents["materials"].append(_solar_material(doc))
    for p in doc["pages"]:
        # domain-1 official checker reads pypdf text: build verbatim windows from it when available
        if p["has_text_layer"] and p.get("pypdf"):
            text, engine = p["pypdf"], "pypdf"
        else:
            text, engine = best_text(doc, p["page"])
        low = text.lower()
        ref_at = low.find("\nreferences")
        for metric, rx in SOLAR_TEXT:
            for m in rx.finditer(text):
                if ref_at >= 0 and m.start() > ref_at:
                    continue
                raw = m.group(1)
                unit = m.group(2) if m.lastindex and m.lastindex >= 2 else "%"
                if metric == "PCE":
                    unit = "%"
                if metric == "Jsc":
                    unit = "mA/cm2"
                if metric == "FF":
                    unit = "%" if (m.group(2) or "") == "%" else ("fraction" if float(raw) <= 1 else "")
                if not unit:
                    continue
                val, _ = _num(raw)
                ctx = text[max(0, m.start() - 120):m.end() + 40]
                frag = _window(text, m.start(), m.end())
                cited = CITE_RE.search(text[m.start():m.end() + 25]) or CITE_RE.search(text[max(0, m.start() - 40):m.start()])
                agg = _agg(ctx)
                if not cited and not any(d["device_id"] == "DV-text" for d in ents["devices"]):
                    ents["devices"].append({"device_id": "DV-text", "absorber_material_id": ents["materials"][0]["material_id"],
                                            "device_label": "device described in text", "device_type": "cell",
                                            "note": "rule-based placeholder: the sentence does not let the rules resolve which device; requires review"})
                out["results"].append({
                    "device_id": "" if cited else "DV-text", "measurement_id": "", "material_id": ents["materials"][0]["material_id"],
                    "metric_name": metric, "raw_value": raw, "raw_unit": unit, "value": val, "unit": unit, "aggregation": agg,
                    "spread_value": "", "n_devices": "", "time_point": "", "time_unit": "",
                    "result_origin": "cited" if cited else "primary", "cited_publication_id": cited.group(0) if cited else "",
                    "source_page": p["page"], "source_section": S.section_for(secs, p["page"]), "source_table": "", "source_figure": "",
                    "source_fragment": frag, "extraction_status": "extracted", "note": "rule-based text pattern",
                    "_evidence": {"kind": "text", "page": p["page"], "engine": engine, "ocr": engine == "ocr"},
                })
