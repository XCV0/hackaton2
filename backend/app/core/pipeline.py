"""Domain-independent pipeline:
PDF -> registration/dedup -> text layer analysis -> parse/OCR -> segmentation -> node extraction
-> raw reply stored -> normalisation -> source verification -> node comparison (quorum)
-> domain rules -> verified / flagged / needs_review -> DB -> UI/export."""
from __future__ import annotations

import collections
import re
import threading
import time
import traceback

from . import canon, db, llm
from . import domain as D
from . import extract_llm, extract_rules, normalize, rules, segment
from .pdftext import extract_document, find_doi, sha256_file
from .quotes import extend_fragment, now, verify_quote
from ..settings import DOMAINS, SPLITS, list_pdfs, pdf_path

ACTOR = "pipeline"
RANGE_RE = re.compile(r"\d(?:[\d.,]*)\s*(?:-|–|—|to|and|…|\.\.)\s*[-−]?\d", re.I)


# ------------------------------------------------------------------ registration
def register_corpus() -> int:
    c = db.conn()
    n = 0
    for dom in DOMAINS:
        for sp in SPLITS:
            for p in list_pdfs(dom, sp):
                if c.execute("SELECT 1 FROM corpus WHERE domain=? AND split=? AND pub_id=?", (dom, sp, p.stem)).fetchone():
                    continue
                c.execute("INSERT INTO corpus(domain,split,pub_id,sha256,bytes,status,stage) VALUES(?,?,?,?,?,?,?)",
                          (dom, sp, p.stem, sha256_file(p), p.stat().st_size, "registered", "registered"))
                n += 1
    c.commit()
    return n


def _index_pages(domain, split, pid, doc):
    c = db.conn()
    c.execute("DELETE FROM pages_fts WHERE domain=? AND split=? AND pub_id=?", (domain, split, pid))
    for p in doc["pages"]:
        text = p["pymupdf"] if p["has_text_layer"] else (p.get("ocr") or "")
        engine = "pymupdf" if p["has_text_layer"] else "ocr"
        text = text.encode("utf-8", "replace").decode("utf-8")
        c.execute("INSERT INTO pages_fts(domain,split,pub_id,page,engine,text) VALUES(?,?,?,?,?,?)", (domain, split, pid, p["page"], engine, text))


def _safe(s):
    return s.encode("utf-8", "replace").decode("utf-8") if isinstance(s, str) else s


# ------------------------------------------------------------------ quorum
def _label(domain, r, ents):
    if domain == "rag":
        cfgs = {c["config_id"]: c for c in ents.get("configurations", [])}
        lab = (cfgs.get(r.get("config_id")) or {}).get("rag_variant", "")
    else:
        devs = {d["device_id"]: d for d in ents.get("devices", [])}
        lab = (devs.get(r.get("device_id")) or {}).get("device_label", "")
    return set(re.findall(r"[a-z0-9]+", (lab or "").lower()))


def _vkey(r):
    v = normalize.to_float(r.get("normalized_value"))
    return normalize.fmt(v) if v is not None else (r.get("raw_value") or "").strip()


def compare_nodes(domain, a: dict, b: dict) -> dict:
    """Deterministic comparison after normalisation. Returns per-result-index outcomes for node a."""
    out = {}
    bidx = collections.defaultdict(list)
    for j, rb in enumerate(b["results"]):
        bidx[(str(rb.get("source_page")), D.canonical_metric(domain, rb.get("metric_name", ""))[0])].append(j)
    used = set()
    keys = {}
    for i, ra in enumerate(a["results"]):
        key = (str(ra.get("source_page")), D.canonical_metric(domain, ra.get("metric_name", ""))[0])
        keys[i] = key
        same = [j for j in bidx.get(key, []) if j not in used and _vkey(b["results"][j]) == _vkey(ra)]
        if same:
            used.add(same[0])
            rb = b["results"][same[0]]
            out[i] = {"outcome": "agree", "other_value": _vkey(rb), "other_fragment": rb.get("source_fragment", "")}
    for i, ra in enumerate(a["results"]):
        if i in out:
            continue
        la = _label(domain, ra, a["entities"])
        clash = None
        for j in bidx.get(keys[i], []):
            if j in used:
                continue
            rb = b["results"][j]
            lb = _label(domain, rb, b["entities"])
            if la and lb and len(la & lb) / max(1, len(la | lb)) >= 0.5 and str(ra.get("metric_k", "")) == str(rb.get("metric_k", "")):
                clash = j
                break
        if clash is not None:
            used.add(clash)
            rb = b["results"][clash]
            out[i] = {"outcome": "disagree", "other_value": _vkey(rb), "other_fragment": rb.get("source_fragment", "")}
        else:
            out[i] = {"outcome": "single"}
    return out


# ------------------------------------------------------------------ main per-publication processing
def replay_models(domain: str, split: str, pid: str) -> dict:
    """Models that actually extracted this publication (latest successful non-cached runs per node)."""
    out = {}
    for node, key in (("A", "model_a"), ("B", "model_b"), ("C", "model_c")):
        r = db.conn().execute("SELECT model, COUNT(*) n FROM node_runs WHERE domain=? AND split=? AND pub_id=? AND node=? AND error IS NULL "
                              "AND purpose LIKE 'extract page%' AND purpose NOT LIKE '%cached%' GROUP BY model ORDER BY n DESC LIMIT 1",
                              (domain, split, pid, node)).fetchone() if node != "C" else db.conn().execute(
                              "SELECT model FROM node_runs WHERE domain=? AND split=? AND pub_id=? AND node='C' AND error IS NULL ORDER BY id DESC LIMIT 1",
                              (domain, split, pid)).fetchone()
        if r:
            out[key] = r["model"]
    return out


def process(domain: str, split: str, pid: str, mode: str = "default", log=print, models: dict | None = None) -> dict:
    t_start = time.time()
    c = db.conn()
    path = pdf_path(domain, split, pid)
    cfg = D.load(domain)
    c.execute("UPDATE corpus SET status='running', stage='parse', error=NULL WHERE domain=? AND split=? AND pub_id=?", (domain, split, pid))
    c.commit()
    doc = extract_document(path, domain, f"{split}_{pid}", do_ocr=True)
    _index_pages(domain, split, pid, doc)
    stats = {"pages": doc["page_count"], "text_pages": doc["text_layer_pages"], "is_scan": doc["is_scan"],
             "ocr_pages": sum(1 for p in doc["pages"] if p.get("ocr_done")),
             "ocr_conf_mean": (lambda xs: round(sum(xs) / len(xs), 1) if xs else None)([p["ocr_conf"] for p in doc["pages"] if p.get("ocr_conf")])}
    c.execute("UPDATE corpus SET pages=?, text_pages=?, is_scan=?, doi=?, stage='extract' WHERE domain=? AND split=? AND pub_id=?",
              (doc["page_count"], doc["text_layer_pages"], int(doc["is_scan"]), find_doi(doc), domain, split, pid))
    c.commit()

    # ---- nodes
    nodes = {}
    t0 = time.time()
    nodes["R"] = extract_rules.extract(domain, doc, str(path))
    extract_llm._log(domain, split, pid, "R", "rule-based extraction", extract_rules.NODE_VERSION, {"deterministic": True}, "", "all pages",
                     None, {"results": len(nodes["R"]["results"]), "publication": nodes["R"]["publication"]}, None, t0)
    lc = {**llm.config(), **(models or {})}
    if llm.available() and not (models or {}).get("_rules_only"):
        nodes["A"] = extract_llm.run_node("A", lc["model_a"], domain, split, pid, doc, workers=int(lc.get("page_workers") or 4))
        if mode == "extended" and lc.get("model_b"):
            nodes["B"] = extract_llm.run_node("B", lc["model_b"], domain, split, pid, doc, workers=int(lc.get("page_workers") or 4))
    primary_name = "A" if "A" in nodes and (nodes["A"]["results"] or nodes["A"]["publication"]) else "R"
    primary = nodes[primary_name]
    if primary_name != "R" and primary.get("failed_pages"):
        # fallback: pages the LLM node could not process (gateway error / content-blocked) keep the R node's values
        fp = set(primary["failed_pages"])
        rmap = {}
        for t, rows in nodes["R"]["entities"].items():
            key = cfg["keys"][t]
            for e in rows:
                e2 = dict(e)
                e2[key] = "R" + e[key]
                rmap[(t, e[key])] = e2[key]
                primary["entities"].setdefault(t, []).append(e2)
        for r in nodes["R"]["results"]:
            if r.get("source_page") in fp:
                r2 = dict(r)
                for field, tbl in cfg["result_links"].items():
                    if r2.get(field):
                        r2[field] = rmap.get((tbl, r2[field]), "")
                r2["note"] = (r2.get("note", "") + "; " if r2.get("note") else "") + f"fallback to node R: node {primary_name} failed on this page"
                r2.setdefault("_evidence", {})["fallback"] = "R"
                primary["results"].append(r2)
        stats["fallback_pages"] = sorted(fp)
    if primary_name != "R" and primary.get("truncated_pages"):
        # complement: on pages where the LLM reply was cut by the output limit, add R values A did not return
        tp = set(primary["truncated_pages"])
        have = {(r.get("source_page"), D.canonical_metric(domain, r.get("metric_name", ""))[0], _vkey(normalize.normalize_result(domain, dict(r))))
                for r in primary["results"] if r.get("source_page") in tp}
        rmap2 = {}
        for t, rows in nodes["R"]["entities"].items():
            key = cfg["keys"][t]
            for e in rows:
                if not any(x.get(key) == "R" + e[key] for x in primary["entities"].get(t, [])):
                    e2 = dict(e)
                    e2[key] = "R" + e[key]
                    primary["entities"].setdefault(t, []).append(e2)
                rmap2[(t, e[key])] = "R" + e[key]
        added = 0
        for r in nodes["R"]["results"]:
            if r.get("source_page") not in tp:
                continue
            k = (r.get("source_page"), D.canonical_metric(domain, r.get("metric_name", ""))[0], _vkey(normalize.normalize_result(domain, dict(r))))
            if k in have:
                continue
            r2 = dict(r)
            for field, tbl in cfg["result_links"].items():
                if r2.get(field):
                    r2[field] = rmap2.get((tbl, r2[field]), "")
            r2["note"] = (r2.get("note", "") + "; " if r2.get("note") else "") + f"complement from node R: node {primary_name} reply truncated on this page"
            r2.setdefault("_evidence", {})["fallback"] = "R"
            primary["results"].append(r2)
            added += 1
        stats["truncated_pages"] = sorted(tp)
        stats["complement_from_R"] = added
    second_name = "B" if "B" in nodes else ("R" if primary_name != "R" else None)
    stats["nodes"] = {k: len(v["results"]) for k, v in nodes.items()}
    stats["primary_node"] = primary_name

    # ---- publication row
    pub = dict(primary["publication"] or {})
    if primary_name != "R" and not pub.get("title"):
        pub = {**nodes["R"]["publication"], **{k: v for k, v in pub.items() if v}}
    pubrow = {col: _safe(str(pub.get(col, "") or "")) for col in cfg["tables"]["publications"]}
    pubrow["publication_id"] = pid
    pubrow["in_scope"] = "false" if str(pub.get("in_scope", "true")).lower() == "false" else "true"
    pubrow["exclusion_reason"] = pubrow["exclusion_reason"] if pubrow["in_scope"] == "false" else ""
    if pubrow["in_scope"] == "false" and not pubrow["exclusion_reason"]:
        pubrow["exclusion_reason"] = "excluded by extraction node without stated reason (needs review)"
    if pubrow.get("year") and not re.fullmatch(r"\d{4}", pubrow["year"]):
        m = re.search(r"\d{4}", pubrow["year"])
        pubrow["year"] = m.group(0) if m else ""

    # keep human decisions across re-runs
    reviewed = {}
    for r in c.execute("SELECT * FROM records WHERE domain=? AND split=? AND pub_id=? AND review_status IN ('confirmed','corrected','rejected')",
                       (domain, split, pid)).fetchall():
        rr = db.row_to_record(r)
        reviewed[_sig(rr["tbl"], rr["data"])] = rr
    c.execute("DELETE FROM records WHERE domain=? AND split=? AND pub_id=?", (domain, split, pid))
    ts = now()

    def put(tbl, rec_id, data, node, ext="", ver="", checks=None, quorum=None, evidence=None):
        rv = reviewed.get(_sig(tbl, data))
        review = rv["review_status"] if rv else ("pending" if ver in ("needs_review", "flagged") else "none")
        if rv and rv["review_status"] == "corrected":
            data = rv["data"]
        c.execute("INSERT INTO records(domain,split,pub_id,tbl,rec_id,data,node,extraction_status,verification_status,review_status,checks,quorum,evidence,created,updated)"
                  " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (domain, split, pid, tbl, rec_id, db.j({k: _safe(v) for k, v in data.items()}), node, ext, ver, review,
                   db.j(checks or []), db.j(quorum or {}), db.j(evidence or {}), ts, ts))

    put("publications", pid, pubrow, primary_name, ver="n/a", evidence={"scope_basis": pub.get("_basis", ""), "node": primary_name})
    if pubrow["in_scope"] == "false":
        c.execute("UPDATE corpus SET status='done', stage='excluded', title=?, processed_at=?, stats=? WHERE domain=? AND split=? AND pub_id=?",
                  (pubrow.get("title", ""), now(), db.j(stats), domain, split, pid))
        db.audit(ACTOR, "process", domain, split, pid, reason=f"excluded: {pubrow['exclusion_reason']}")
        c.commit()
        return stats

    # ---- entities (ids validated, columns forced to the official template)
    ents = {}
    for t in cfg["entity_tables"]:
        key = cfg["keys"][t]
        seen = set()
        rows = []
        for e in primary["entities"].get(t, []):
            row = {col: str(e.get(col, "") or "") for col in cfg["tables"][t]}
            row["publication_id"] = pid
            rid = re.sub(r"[^A-Za-z0-9_-]", "", row[key]) or f"{t[:2].upper()}{len(rows) + 1}"
            while rid in seen:
                rid += "x"
            row[key] = rid
            seen.add(rid)
            rows.append(row)
        ents[t] = rows
    internal_issues = []
    # numeric hygiene: printed text that is not a plain number (~1.9, ranges, "2 × 2") is kept verbatim in note
    num_re = re.compile(r"-?\d+(\.\d+)?([eE][-+]?\d+)?")
    int_fields = set(cfg.get("integer_fields") or [])
    for qual in cfg.get("numeric_fields") or []:
        t, col = qual.split(".")
        if t not in ents:
            continue
        for row in ents[t]:
            v = (row.get(col) or "").strip()
            if v and not (num_re.fullmatch(v) and (qual not in int_fields or "." not in v)):
                if "note" in row:
                    row["note"] = (row["note"] + "; " if row["note"] else "") + f"{col} as printed: {v}"
                row[col] = ""
    # links between entity tables
    for qual, target in (cfg.get("entity_links") or {}).items():
        t, col = qual.split(".")
        valid = {e[cfg["keys"][target]] for e in ents.get(target, [])}
        for row in ents.get(t, []):
            vals = [x.strip() for x in (row.get(col) or "").split(";") if x.strip()]
            bad = [x for x in vals if x not in valid]
            if bad:
                row[col] = ";".join(x for x in vals if x in valid)
                if "note" in row:
                    row["note"] = (row["note"] + "; " if row["note"] else "") + f"dangling {col}={','.join(bad)} removed"
    # enum hygiene: values outside closed vocabularies are moved to note (never silently kept)
    for t, rows in ents.items():
        for row in rows:
            for col in list(row):
                allowed = cfg["closed_enums"].get(f"{t}.{col}")
                if allowed and row[col] and row[col] not in allowed:
                    if "note" in row:
                        row["note"] = (row["note"] + "; " if row["note"] else "") + f"{col} as printed: {row[col]}"
                    row[col] = ""

    if domain == "solar":
        stats["unit_conversions"] = _solar_entity_units(ents)

    # ---- results: normalise, verify
    results = []
    for i, r in enumerate(primary["results"]):
        r = dict(r)
        for col in cfg["tables"]["results"]:  # nodes omit empty fields: empty means "not stated"
            if r.get(col) is None:
                r[col] = ""
        r["result_id"] = f"R{i + 1:03d}"
        if RANGE_RE.search(str(r.get("raw_value") or "")):
            # a printed range is kept verbatim in raw_value; no single number is substituted (not the first, not the mean)
            r["value"] = None
            r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"printed range «{r.get('raw_value')}»: no single normalized value"
        r["_node_index"] = i
        if isinstance(r.get("source_fragment"), str):
            r["source_fragment"] = r["source_fragment"].strip()
        normalize.normalize_result(domain, r)
        results.append(r)
    # ---- publication-level canonicalisation: OCR-misread metric names, then one entity per real-world entity
    for r in results:
        fx = canon.ocr_metric_fix(domain, r, doc)
        if fx:
            r["_evidence"] = {**(r.get("_evidence") or {}), "ocr_metric_fix": fx}
            r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"metric_name OCR-read as «{fx['from']}», set to {fx['to']} ({fx['detail']})"
            r["metric_name"] = fx["to"]
    stats["canonicalization"] = canon.canonicalize(domain, ents, results, doc)
    ids = {t: {e[cfg["keys"][t]] for e in ents[t]} for t in ents}
    for r in results:
        for field, tbl in cfg["result_links"].items():
            v = r.get(field, "")
            if v and v not in ids.get(tbl, set()):
                r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"dangling {field}={v} removed"
                r[field] = ""
        for qual in cfg.get("numeric_fields") or []:
            t, col = qual.split(".")
            if t == "results" and r.get(col) not in (None, ""):
                v = str(r[col]).strip()
                if not (num_re.fullmatch(v) and (qual not in int_fields or "." not in v)):
                    r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"{col} as printed: {v}"
                    r[col] = ""
        mv = (r.get("metric_variant") or "").strip()
        ds_names = {(d.get("dataset_name") or "").strip().lower() for d in ents.get("datasets", [])} - {""}
        if mv and domain == "rag" and mv.lower() in ds_names:
            r["metric_variant"] = ""  # the dataset name is not a metric variant (the dataset is linked via dataset_id)
            r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"metric_variant as printed: {mv}"
            mv = ""
        if mv and domain == "rag":
            cn, _ = D.canonical_metric(domain, r.get("metric_name", ""))
            cv, _ = D.canonical_metric(domain, mv)
            if cv.lower() == cn.lower() or mv.lower() == (r.get("metric_name") or "").lower():
                r["metric_variant"] = ""  # only restates the metric name
                r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"metric_variant as printed: {mv}"
        md = (r.get("metric_direction") or "").strip()
        if md:
            low = md.lower().replace("-", " ").replace("_", " ")
            cdir = ("higher_is_better" if low in ("higher", "higher is better", "higher better", "↑", "up", "max", "maximize")
                     else "lower_is_better" if low in ("lower", "lower is better", "lower better", "↓", "down", "min", "minimize")
                     else "target" if low in ("target",) else md if md in ("higher_is_better", "lower_is_better", "target") else "")
            if cdir != md:
                if not cdir:
                    r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"metric_direction as printed: {md}"
                r["metric_direction"] = cdir
        if r.get("result_origin") not in ("primary", "cited"):
            r["result_origin"] = "cited" if r.get("cited_publication_id") else "primary"
        if r["result_origin"] == "cited" and not (r.get("cited_publication_id") or "").strip():
            ref = _citation_marker(doc, r)
            if ref:
                r["cited_publication_id"] = ref
                r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"cited_publication_id taken from the citation marker «{ref}» in the same sentence"
            else:
                r["_cited_without_ref"] = True
        if r["result_origin"] == "primary":
            r["cited_publication_id"] = ""
        if r.get("extraction_status") not in ("extracted", "present_not_extractable", "absent"):
            r["extraction_status"] = "extracted"
        if domain == "solar" and r.get("aggregation") not in ("", "champion", "mean", "median"):
            r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"aggregation as printed: {r['aggregation']}"
            r["aggregation"] = ""
        if domain == "solar" and r["result_origin"] == "cited":
            r["device_id"] = r["measurement_id"] = ""

    if domain == "rag":
        _rag_result_conventions(cfg, results, ents, doc, stats)

    for r in results:
        checks = []
        pg = r.get("source_page")
        try:
            pg = int(pg) if pg != "" else None
        except (TypeError, ValueError):
            pg = None
        q = verify_quote(doc, pg, r.get("source_fragment", ""), r.get("raw_value", ""))
        if q["outcome"] == "wrong_page" and q["other_pages"] and primary_name != "R":
            # our own extraction error (LLM page pointer): correct the extraction, keep a trace
            newp = q["other_pages"][0]
            checks.append({**q, "action": f"extraction page corrected {pg} -> {newp}"})
            r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + f"page pointer corrected by verifier from {pg} to {newp}"
            r["source_page"] = newp
            q = verify_quote(doc, newp, r.get("source_fragment", ""), r.get("raw_value", ""))
        if q.get("outcome") == "matched" and q.get("value_in_fragment") is False and pg:
            ext = extend_fragment(doc, pg, r.get("source_fragment", ""), r.get("raw_value", ""))
            if ext:
                checks.append({**q, "check": "quote_initial", "action": "quote widened to include the value"})
                checks.append({"check": "quote_extension", "ts": now(), "outcome": "extended", "engine": ext["engine"],
                               "from": r.get("source_fragment"), "to": ext["fragment"],
                               "detail": "the number is printed after the quoted text in the same sentence; quote widened on the same page and engine and re-verified"})
                r["source_fragment"] = ext["fragment"]
                q = ext["check"]
        if q["outcome"] in ("not_found", "no_text_layer", "bad_page") and r.get("source_fragment"):
            r["_quote_failed_fragment"] = r["source_fragment"]
        checks.append(q)
        ev = r.get("_evidence") or {}
        if ev.get("kind") == "table" and ev.get("cell_bbox"):
            checks.append({"check": "table_cell", "ts": now(), "outcome": "value_at_cell", "table": ev.get("table"),
                           "row": ev.get("row_label"), "column": ev.get("col_label"), "bbox": ev.get("cell_bbox"),
                           "detail": "printed cell text equals raw_value (geometric table parse)"})
        elif q.get("outcome") in ("matched", "matched_ocr_only") and q.get("value_in_fragment") is False and pg:
            row = _row_check(doc, str(path), pg, r.get("source_fragment", ""), r.get("raw_value", ""))
            if row:
                checks.append(row)
                if row["outcome"] == "value_in_row":
                    ev["row_bbox"] = row["bbox"]
                    r["_evidence"] = ev
        r["_checks"] = checks

    # ---- domain rules
    from .pdftext import best_text
    rule_issues, per = rules.run(domain, results, ents, page_text=lambda pg: best_text(doc, pg)[0] if 1 <= pg <= doc["page_count"] else "")
    dup_errs = rules.duplicate_graph_errors(results)
    for e in dup_errs:
        internal_issues.append({"check_name": "duplicate_of", "record_ids": "", "description": e, "source_page": "", "source_fragment": ""})

    # ---- quorum
    qmap = {}
    if second_name and second_name in nodes and second_name != primary_name:
        sec = nodes[second_name]
        for rr in sec["results"]:
            normalize.normalize_result(domain, rr)
        qmap = compare_nodes(domain, {"results": results, "entities": ents}, sec)
    c_budget = 12
    for i, r in enumerate(results):
        qr = qmap.get(i)
        if (r.get("_evidence") or {}).get("fallback"):
            r["_quorum"] = {"mode": mode, "nodes": ["R"], "outcome": "single_node",
                            "limitation": "fallback value from node R; comparison with R itself would not be independent"}
            continue
        if not qr:
            r["_quorum"] = {"mode": mode, "nodes": [primary_name], "outcome": "single_node",
                            "limitation": "only one extraction node ran" if not second_name else ""}
            continue
        r["_quorum"] = {"mode": mode, "nodes": [primary_name, second_name], **qr}
        if qr["outcome"] == "disagree" and mode == "extended" and llm.available() and c_budget > 0 and lc.get("model_c"):
            c_budget -= 1
            ans = extract_llm.reread(lc["model_c"], domain, split, pid, doc, int(r["source_page"] or 1),
                                     f"Metric {r.get('metric_name')} on page {r['source_page']}: node {primary_name} read {r.get('raw_value')}, "
                                     f"node {second_name} read {qr.get('other_value')}. What value is printed?")
            if ans:
                av = (ans.get("value") or "").strip()
                r["_quorum"]["C"] = ans
                r["_quorum"]["outcome"] = "resolved_by_C" if av and av in (r.get("raw_value"), qr.get("other_value")) and ans.get("confident") else "unresolved"
    same_model = lc.get("model_a") and lc.get("model_a") == lc.get("model_b")

    # ---- statuses + issues
    issues = []
    for iss in rule_issues:
        issues.append(iss)
    rid_to = {r["result_id"]: r for r in results}
    fail_rules = collections.defaultdict(list)
    for rid, lst in per.items():
        for x in lst:
            if x.get("outcome") == "fail":
                fail_rules[rid].append(x["check"])
    for r in results:
        q = next((x for x in r["_checks"] if x["check"] == "quote"), {})
        cell = any(x["check"] == "table_cell" or (x["check"] == "table_row" and x.get("outcome") == "value_in_row") for x in r["_checks"])
        ev = r.get("_evidence") or {}
        reasons = []
        if r.get("extraction_status") != "extracted":
            ver = "not_applicable"
        else:
            ver = "verified"
            if q.get("outcome") == "matched_ocr_only":
                ver = "needs_review"
                reasons.append("ocr_uncertainty")
            elif q.get("outcome") != "matched":
                ver = "needs_review"
                reasons.append("citation_not_found")
            elif not q.get("value_in_fragment") and not cell:
                ver = "needs_review"
                reasons.append("value_not_in_fragment")
            if ev.get("kind") == "figure" or r.get("source_figure") and not r.get("source_table") and not q.get("value_in_fragment"):
                ver = "needs_review"
                reasons.append("source_figure_review")
            if ev.get("ocr"):
                reasons.append("ocr_page")
                if ver == "verified":
                    ver = "needs_review"
            if r.get("_cited_without_ref"):
                ver = "needs_review"
                reasons.append("cited_without_reference")
            qo = (r.get("_quorum") or {}).get("outcome")
            if qo in ("disagree", "unresolved"):
                ver = "needs_review"
                reasons.append("node_disagreement")
            if fail_rules.get(r["result_id"]) and ver == "verified":
                ver = "flagged"
                reasons.append("rule_violation:" + ",".join(fail_rules[r["result_id"]]))
            elif fail_rules.get(r["result_id"]):
                reasons.append("rule_violation:" + ",".join(fail_rules[r["result_id"]]))
        r["_ver"], r["_reasons"] = ver, reasons
        loc_frag = r.get("source_fragment") if q.get("outcome") == "matched" else ""
        if "citation_not_found" in reasons:
            issues.append({"check_name": "citation_not_found", "record_ids": r["result_id"],
                           "description": f"Цитата не найдена на с. {r.get('source_page')} ({q.get('outcome')}): «{(r.get('source_fragment') or '')[:120]}»",
                           "source_page": "", "source_fragment": "", "_kind": "citation_not_found"})
        if "source_figure_review" in reasons:
            issues.append({"check_name": "source_figure_review", "record_ids": r["result_id"],
                           "description": f"Значение с рисунка {r.get('source_figure')}: текстовый поиск не подтверждает визуальное считывание; нужна визуальная проверка",
                           "source_page": str(r.get("source_page") or ""), "source_fragment": loc_frag, "_kind": "source_figure_review"})
        if "ocr_uncertainty" in reasons or ("ocr_page" in reasons and ver == "needs_review" and "citation_not_found" not in reasons):
            fx = ev.get("ocr_metric_fix")
            issues.append({"check_name": "ocr_uncertainty", "record_ids": r["result_id"],
                           "description": "Источник — скан: цитата подтверждена только OCR-текстом; цифры/знаки требуют сверки с изображением страницы"
                                          + (f"; название метрики OCR прочитал как «{fx['from']}», принято {fx['to']} по тексту статьи (с. {', '.join(map(str, fx['pages']))})" if fx else ""),
                           "source_page": str(r.get("source_page") or ""), "source_fragment": "", "_kind": "ocr_uncertainty"})
        if "node_disagreement" in reasons:
            qq = r["_quorum"]
            issues.append({"check_name": "node_disagreement", "record_ids": r["result_id"],
                           "description": f"Ноды разошлись: {qq['nodes'][0]}={r.get('raw_value')} vs {qq['nodes'][1]}={qq.get('other_value')}"
                                          + (f"; C: {qq.get('C', {}).get('value')}" if qq.get("C") else "") + "; возможна ошибка чтения",
                           "source_page": str(r.get("source_page") or ""), "source_fragment": loc_frag, "_kind": "node_disagreement"})
        if r.get("_norm", {}).get("rule", "").startswith(("unit unknown", "unit ")) and r.get("extraction_status") == "extracted" and domain == "solar":
            issues.append({"check_name": "normalization", "record_ids": r["result_id"],
                           "description": f"Нормализация невозможна: {r['_norm']['rule']} (raw {r.get('raw_value')} {r.get('raw_unit')})",
                           "source_page": str(r.get("source_page") or ""), "source_fragment": loc_frag, "_kind": "normalization"})
    for r in results:
        if r.get("duplicate_of") and r["duplicate_of"] not in rid_to:
            r["duplicate_of"] = ""
    issues += internal_issues

    # ---- persist
    for t in cfg["entity_tables"]:
        for e in ents[t]:
            put(t, e[cfg["keys"][t]], e, primary_name, ver="n/a")
    for r in results:
        data = {col: _safe(str(r.get(col, "") if r.get(col) is not None else "")) for col in cfg["tables"]["results"]}
        data["publication_id"] = pid
        evidence = {**(r.get("_evidence") or {}), "norm": r.get("_norm"), "reasons": r.get("_reasons"),
                    "failed_fragment": r.get("_quote_failed_fragment")}
        put("results", r["result_id"], data, primary_name, r.get("extraction_status", ""), r["_ver"],
            checks=r["_checks"] + per.get(r["result_id"], []), quorum={**(r.get("_quorum") or {}), "same_model_limitation": bool(same_model)},
            evidence=evidence)
    for k, iss in enumerate(issues, 1):
        data = {col: _safe(str(iss.get(col, "") or "")) for col in cfg["tables"]["issues"]}
        data.update(publication_id=pid, issue_id=f"I{k}")
        put("issues", f"I{k}", data, "verifier", ver="open",
            evidence={"kind": iss.get("_kind", iss["check_name"]), "formula": iss.get("_formula"), "inputs": iss.get("_inputs")})
    stats.update(results=len(results), issues=len(issues), seconds=round(time.time() - t_start, 1),
                 verified=sum(r["_ver"] == "verified" for r in results), flagged=sum(r["_ver"] == "flagged" for r in results),
                 needs_review=sum(r["_ver"] == "needs_review" for r in results))
    tok = c.execute("SELECT COALESCE(SUM(tokens_in),0) ti, COALESCE(SUM(tokens_out),0) tt, COALESCE(SUM(cost_usd),0) cost FROM node_runs WHERE domain=? AND split=? AND pub_id=?",
                    (domain, split, pid)).fetchone()
    stats.update(tokens_in=tok["ti"], tokens_out=tok["tt"], cost_usd=round(tok["cost"], 4))
    c.execute("UPDATE corpus SET status='done', stage='done', title=?, processed_at=?, stats=? WHERE domain=? AND split=? AND pub_id=?",
              (pubrow.get("title", ""), now(), db.j(stats), domain, split, pid))
    db.audit(ACTOR, "process", domain, split, pid, after={"results": len(results), "issues": len(issues), "primary": primary_name, "mode": mode},
             reason="automatic pipeline run")
    c.commit()
    log(f"{domain}/{split}/{pid}: {len(results)} results, {len(issues)} issues, primary={primary_name}, {stats['seconds']}s")
    return stats


CITE_RE = re.compile(r"\[\s*\d+(?:\s*[-–,]\s*\d+)*\s*\]|\b[A-Z][A-Za-z'-]+(?: and [A-Z][A-Za-z'-]+| et al\.?)?,?\s*\(?(?:19|20)\d\d[a-z]?\)?")


def _citation_marker(doc, r):
    """A cited value needs a reference; look for «[12]» / «Smith et al., 2020» in the sentence of the quote on the same page."""
    frag = (r.get("source_fragment") or "").strip()
    try:
        pg = int(r.get("source_page") or 0)
    except (TypeError, ValueError):
        return ""
    if not frag or not 1 <= pg <= doc["page_count"]:
        return ""
    m = CITE_RE.search(frag)
    if m:
        return m.group(0).strip()
    p = doc["pages"][pg - 1]
    for t in (p.get("pymupdf"), p.get("pypdf"), p.get("ocr")):
        flat = re.sub(r"\s+", " ", t or "")
        i = flat.find(re.sub(r"\s+", " ", frag))
        if i < 0:
            continue
        s0 = max(flat.rfind(". ", 0, i) + 2, 0)
        e = flat.find(". ", i + len(frag))
        m = CITE_RE.search(flat[s0:(e if e > 0 else len(flat))])
        if m:
            return m.group(0).strip()
    return ""


UNIT_TO_CM2 = {"cm2": 1, "cm^2": 1, "cm²": 1, "cm 2": 1, "mm2": 0.01, "mm^2": 0.01, "mm²": 0.01, "m2": 1e4, "m^2": 1e4, "m²": 1e4}
UNIT_TO_NM = {"nm": 1, "µm": 1000, "μm": 1000, "um": 1000, "micron": 1000, "microns": 1000, "mm": 1e6, "å": 0.1, "a": 0.1, "angstrom": 0.1, "pm": 0.001}
UNIT_TO_EV = {"ev": 1, "mev": 0.001}


def _convert(row, vcol, ucol, table, target, label):
    """Bring an entity value to the template unit when the printed unit is explicit; otherwise keep the print in note."""
    u = (row.get(ucol) or "").strip()
    if not u or u == target:
        return None
    f = table.get(u.lower(), table.get(u.lower().replace(" ", "")))
    v = (row.get(vcol) or "").strip()
    if f is None:
        if "note" in row:
            row["note"] = (row["note"] + "; " if row.get("note") else "") + f"{label} as printed: {v} {u} (unit is not a {target} quantity)"
        row[vcol], row[ucol] = "", ""
        return f"{label}: «{v} {u}» moved to note"
    try:
        x = float(v)
    except ValueError:
        row[ucol] = target if not v else u
        return None
    nv = normalize.fmt(x * f)
    if "note" in row and f != 1:
        row["note"] = (row["note"] + "; " if row.get("note") else "") + f"{label} as printed: {v} {u}"
    row[vcol], row[ucol] = nv, target
    return f"{label}: {v} {u} -> {nv} {target}"


def _solar_entity_units(ents):
    """Template units (solar README): area_unit cm2, thickness_unit nm («толщины в мкм переводятся в нм»), bandgap_unit eV."""
    log = []
    for row in ents.get("devices", []):
        x = _convert(row, "active_area", "area_unit", UNIT_TO_CM2, "cm2", "active_area")
        if x:
            log.append(f"{row.get('device_id')}: {x}")
    for row in ents.get("layers", []):
        x = _convert(row, "layer_thickness", "thickness_unit", UNIT_TO_NM, "nm", "layer_thickness")
        if x:
            log.append(f"{row.get('layer_id')}: {x}")
    for row in ents.get("materials", []):
        x = _convert(row, "bandgap_value", "bandgap_unit", UNIT_TO_EV, "eV", "bandgap")
        if x:
            log.append(f"{row.get('material_id')}: {x}")
    return log


def _addnote(r, text):
    r["note"] = (r.get("note", "") + "; " if r.get("note") else "") + text


def _rag_result_conventions(cfg, results, ents, doc, stats):
    """One documented convention per field across the publication:
    deltas are differences (named «<metric> delta», linked to the baseline configuration), never scores;
    a bounded metric with no printed unit gets unit «fraction» only when the paper states the 0-1 scale;
    metric_direction follows the metric definition; one spelling per metric within a publication."""
    scale = canon.stated_scale(doc)
    configs = ents.get("configurations") or []
    for r in results:
        cm, _ = D.canonical_metric("rag", r.get("metric_name", ""))
        spec = (cfg.get("metrics") or {}).get(cm) or {}
        if canon.is_delta(r) and not re.search(r"\bdelta\b", r.get("metric_name", ""), re.I):
            bid, label = canon.delta_baseline(r, configs)
            _addnote(r, f"metric_name as printed: {r.get('metric_name')}; the value is a difference, not an absolute {cm or 'score'}"
                        + (f"; baseline configuration {bid} («{label}»)" if bid else (f"; baseline «{label}» not resolved to one configuration" if label else "")))
            r["metric_name"] = f"{cm or r.get('metric_name')} delta"
            r["metric_variant"] = f"difference vs {label}" if label else (r.get("metric_variant") or "difference")
            r["metric_direction"] = ""
            r["_delta"] = {"metric": cm, "baseline_config_id": bid, "baseline_label": label}
            continue
        u = normalize.canon_unit(r.get("raw_unit") or "")
        if u != (r.get("raw_unit") or "") and u in ("fraction", "%"):
            r["unit"] = u
            normalize.normalize_result("rag", r)
        if (spec.get("scale") == "bounded" and not (r.get("metric_unit") or r.get("raw_unit")) and scale
                and r.get("value") is not None and 0 <= float(r["value"]) <= 1):
            r["unit"] = "fraction"
            normalize.normalize_result("rag", r)
            r["_norm"]["rule"] = f"unit fraction: the paper states «{scale[0]}» (p. {scale[1]}); value not rescaled"
        if not r.get("metric_direction") and spec.get("direction"):
            r["metric_direction"] = spec["direction"]
    # one spelling per metric (needed for duplicate_of, which the official checker compares literally)
    groups = collections.defaultdict(list)
    for r in results:
        nm = (r.get("metric_name") or "").strip()
        cm, _ = D.canonical_metric("rag", nm)
        if nm and "@" not in nm and cm in (cfg.get("metrics") or {}) and not r.get("_delta"):
            groups[cm].append(r)
    for cm, rs in groups.items():
        spellings = collections.Counter(r["metric_name"].strip() for r in rs)
        if len(spellings) < 2:
            continue
        best = max(spellings, key=lambda s_: (spellings[s_], len(s_)))
        for r in rs:
            if r["metric_name"].strip() != best:
                _addnote(r, f"metric_name as printed: {r['metric_name']} (same metric as «{best}»)")
                r["metric_name"] = best
        stats.setdefault("canonicalization", []).append(f"metric spellings unified: {dict(spellings)} -> {best}")


def _row_check(doc, pdf_path, page, fragment, raw_value):
    """Row-label quote without the number: is the printed number on the same visual row as the label?
    Works on text-layer words and on OCR word boxes. Necessary evidence, not proof of the column."""
    toks = re.findall(r"\d+(?:[.,]\d+)?", raw_value or "")
    if not toks or not fragment.strip():
        return None
    try:
        words = segment.page_words(doc, pdf_path, page)
    except Exception:
        return None
    lab = [t.lower() for t in re.findall(r"\S+", fragment)][:4]
    lines = segment.group_lines(words, ytol=3.5)
    for ln in lines:
        lw = [w.t.lower() for w in ln.words]
        if not lab or lab[0] not in lw:
            continue
        i = lw.index(lab[0])
        if lw[i:i + len(lab)] != lab:
            continue
        y0, y1 = ln.bbox[1] - 2, ln.bbox[3] + 2
        same_row = [w for w in words if (w.y0 + w.y1) / 2 >= y0 and (w.y0 + w.y1) / 2 <= y1]
        texts = [w.t.replace(",", ".").strip("%()±*") for w in same_row]
        want = toks[0].replace(",", ".")
        hit = next((w for w, t in zip(same_row, texts) if t == want or t.lstrip("0") == want.lstrip("0")), None)
        if hit:
            return {"check": "table_row", "ts": now(), "outcome": "value_in_row", "bbox": [hit.x0, hit.y0, hit.x1, hit.y1],
                    "detail": f"«{fragment.strip()[:40]}» и число {raw_value} стоят в одной строке на с. {page} (столбец не доказан)"}
        return {"check": "table_row", "ts": now(), "outcome": "value_not_in_row",
                "detail": f"строка «{fragment.strip()[:40]}» найдена, но числа {raw_value} в ней нет"}
    return None


def _sig(tbl, data):
    if tbl == "results":
        return (tbl, str(data.get("source_page")), data.get("metric_name"), data.get("raw_value"), data.get("source_table"),
                data.get("config_id", data.get("device_id")), (data.get("source_fragment") or "")[:60])
    return (tbl, data.get(next(iter(data)), ""), str(sorted(data.items()))[:200])


# ------------------------------------------------------------------ jobs
_job_lock = threading.Lock()


def create_job(kind: str, params: dict) -> int:
    c = db.conn()
    cur = c.execute("INSERT INTO jobs(kind,params,status,progress,total,done,log,created) VALUES(?,?,?,?,?,?,?,?)",
                    (kind, db.j(params), "queued", 0, 0, 0, "", now()))
    c.commit()
    jid = cur.lastrowid
    threading.Thread(target=_run_job, args=(jid,), daemon=True).start()
    return jid


def _run_job(jid: int):
    with _job_lock:
        c = db.conn()
        job = c.execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
        params = db.lj(job["params"], {})
        targets = []
        for dom in params.get("domains") or list(DOMAINS):
            for sp in params.get("splits") or ["dev"]:
                for p in list_pdfs(dom, sp):
                    if params.get("pub_ids") and p.stem not in params["pub_ids"]:
                        continue
                    targets.append((dom, sp, p.stem))
        c.execute("UPDATE jobs SET status='running', started=?, total=? WHERE id=?", (now(), len(targets), jid))
        c.commit()
        logs = []

        def log(msg):
            logs.append(f"[{now()}] {msg}")
            c.execute("UPDATE jobs SET log=? WHERE id=?", ("\n".join(logs[-400:]), jid))
            c.commit()

        register_corpus()
        failed = 0
        for k, (dom, sp, pid) in enumerate(targets, 1):
            try:
                process(dom, sp, pid, params.get("mode", "default"), log=log)
            except Exception as exc:
                failed += 1
                log(f"ERROR {dom}/{sp}/{pid}: {exc}")
                c.execute("UPDATE corpus SET status='error', error=? WHERE domain=? AND split=? AND pub_id=?",
                          (traceback.format_exc()[-2000:], dom, sp, pid))
            c.execute("UPDATE jobs SET done=?, progress=? WHERE id=?", (k, k / max(1, len(targets)), jid))
            c.commit()
        c.execute("UPDATE jobs SET status=?, finished=? WHERE id=?", ("done" if not failed else "done_with_errors", now(), jid))
        c.commit()
