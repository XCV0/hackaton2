"""HTTP API for the user UI and the admin UI."""
from __future__ import annotations

import collections
import csv
import io
import json
import logging
import pathlib
import re
import warnings

import pymupdf
import yaml
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .core import db, evaluate, export, llm, pipeline
from .core import domain as D
from .core.pdftext import extract_document, norm_rag, render_page_png
from .core.quotes import now, verify_quote
from .settings import CONFIG_DIR, DOMAINS, REPORTS_DIR, ROOT, list_pdfs, pdf_path, split_dir

warnings.filterwarnings("ignore")
logging.getLogger("pypdf").setLevel(logging.ERROR)

app = FastAPI(title="VINITI Evidence Extraction", version="1.0")
app.add_middleware(GZipMiddleware, minimum_size=2000)


def _clean(o):
    if isinstance(o, str):
        return o.encode("utf-8", "replace").decode("utf-8")
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    return o


def J(o):
    return JSONResponse(_clean(o))


def _dom(domain):
    if domain not in DOMAINS:
        raise HTTPException(404, f"unknown domain {domain}")
    return domain


def _doc(domain, split, pid):
    p = pdf_path(domain, split, pid)
    if not p.exists():
        raise HTTPException(404, "PDF not found")
    return extract_document(p, domain, f"{split}_{pid}", do_ocr=False), p


@app.on_event("startup")
def _startup():
    pipeline.register_corpus()


# ------------------------------------------------------------------ overview / corpus
@app.get("/api/overview")
def overview():
    c = db.conn()
    out = {}
    for dom, meta in DOMAINS.items():
        d = {"title": meta["title"], "splits": {}}
        for sp in ("dev", "test", "demo"):
            corp = c.execute("SELECT status, is_scan, stats FROM corpus WHERE domain=? AND split=?", (dom, sp)).fetchall()
            ver = dict(c.execute("SELECT verification_status, COUNT(*) FROM records WHERE domain=? AND split=? AND tbl='results' GROUP BY 1", (dom, sp)).fetchall())
            rev = dict(c.execute("SELECT review_status, COUNT(*) FROM records WHERE domain=? AND split=? AND tbl='results' GROUP BY 1", (dom, sp)).fetchall())
            issues = c.execute("SELECT COUNT(*) FROM records WHERE domain=? AND split=? AND tbl='issues' AND verification_status='open'", (dom, sp)).fetchone()[0]
            excluded = c.execute("SELECT COUNT(*) FROM records WHERE domain=? AND split=? AND tbl='publications' AND json_extract(data,'$.in_scope')='false'", (dom, sp)).fetchone()[0]
            problem = c.execute("SELECT COUNT(DISTINCT pub_id) FROM records WHERE domain=? AND split=? AND tbl='results' AND verification_status IN ('flagged','needs_review')", (dom, sp)).fetchone()[0]
            total = sum(ver.values())
            d["splits"][sp] = {
                "pdfs": len(corp), "processed": sum(1 for x in corp if x["status"] == "done"), "errors": sum(1 for x in corp if x["status"] == "error"),
                "scans": sum(1 for x in corp if x["is_scan"]), "excluded": excluded, "problem_publications": problem,
                "results": total, "verification": ver, "review": rev, "open_issues": issues,
                "verified_share": round(ver.get("verified", 0) / total, 4) if total else None,
            }
        out[dom] = d
    lc = llm.public_config()
    out["_llm"] = {"available": llm.available(), "model_a": lc.get("model_a"), "base_url": lc.get("base_url")}
    return J(out)


@app.get("/api/corpus")
def corpus(domain: str | None = None, split: str | None = None):
    q, a = "SELECT * FROM corpus WHERE 1=1", []
    if domain:
        q += " AND domain=?"; a.append(domain)
    if split:
        q += " AND split=?"; a.append(split)
    rows = []
    for r in db.conn().execute(q + " ORDER BY domain, split, pub_id", a).fetchall():
        d = dict(r)
        d["stats"] = db.lj(d["stats"], {})
        rows.append(d)
    return J(rows)


# ------------------------------------------------------------------ catalog
def quote_outcome(checks):
    """Fragment found AND number confirmed (in the fragment or in the table cell/row) — otherwise not a green «matched»."""
    q = next((x for x in checks or [] if x.get("check") == "quote"), None)
    if not q:
        return None
    cell = any(x.get("check") == "table_cell" or (x.get("check") == "table_row" and x.get("outcome") == "value_in_row") for x in checks)
    if q.get("outcome") == "matched" and q.get("value_in_fragment") is False and not cell:
        return "matched_no_value"
    return q.get("outcome")


@app.get("/api/publications")
def publications(domain: str = "rag", split: str = "dev", q: str = "", status: str = "", scope: str = "", scan: str = "",
                 sort: str = "pub_id", metric: str = "", material_class: str = ""):
    _dom(domain)
    c = db.conn()
    pubs = {r["pub_id"]: db.row_to_record(r) for r in c.execute("SELECT * FROM records WHERE domain=? AND split=? AND tbl='publications'", (domain, split))}
    corp = {r["pub_id"]: dict(r) for r in c.execute("SELECT * FROM corpus WHERE domain=? AND split=?", (domain, split))}
    agg = collections.defaultdict(lambda: collections.Counter())
    metrics = collections.defaultdict(set)
    for r in c.execute("SELECT pub_id, verification_status, json_extract(data,'$.metric_name') m FROM records WHERE domain=? AND split=? AND tbl='results'", (domain, split)):
        agg[r["pub_id"]][r["verification_status"]] += 1
        metrics[r["pub_id"]].add(r["m"])
    iss = collections.Counter(r[0] for r in c.execute("SELECT pub_id FROM records WHERE domain=? AND split=? AND tbl='issues'", (domain, split)))
    mats = collections.defaultdict(set)
    if domain == "solar":
        for r in c.execute("SELECT pub_id, json_extract(data,'$.material_class') mc FROM records WHERE domain=? AND split=? AND tbl='materials'", (domain, split)):
            mats[r["pub_id"]].add(r["mc"])
    hits = None
    if q:
        hits = set()
        try:
            for r in c.execute("SELECT DISTINCT pub_id FROM pages_fts WHERE domain=? AND split=? AND pages_fts MATCH ?", (domain, split, _fts(q))):
                hits.add(r[0])
        except Exception:
            pass
        ql = q.lower()
        for pid, p in pubs.items():
            if ql in json.dumps(p["data"], ensure_ascii=False).lower() or ql in pid.lower():
                hits.add(pid)
    rows = []
    for pid, cr in corp.items():
        p = pubs.get(pid)
        data = p["data"] if p else {}
        st = db.lj(cr["stats"], {})
        row = {"pub_id": pid, "title": data.get("title") or cr.get("title") or "", "year": data.get("year", ""), "doi": data.get("DOI") or cr.get("doi") or "",
               "authors": data.get("authors", ""), "in_scope": data.get("in_scope", ""), "exclusion_reason": data.get("exclusion_reason", ""),
               "status": cr["status"], "stage": cr["stage"], "is_scan": bool(cr["is_scan"]), "pages": cr["pages"],
               "results": sum(agg[pid].values()), "verified": agg[pid]["verified"], "flagged": agg[pid]["flagged"],
               "needs_review": agg[pid]["needs_review"], "issues": iss[pid], "primary_node": st.get("primary_node", ""),
               "material_classes": sorted(x for x in mats[pid] if x), "metrics": sorted(x for x in metrics[pid] if x)[:30]}
        if hits is not None and pid not in hits:
            continue
        if status == "problem" and not (row["flagged"] or row["needs_review"] or row["status"] == "error"):
            continue
        if status and status not in ("problem",) and row["status"] != status:
            continue
        if scope and row["in_scope"] != scope:
            continue
        if scan and str(row["is_scan"]).lower() != scan:
            continue
        if metric and metric not in row["metrics"]:
            continue
        if material_class and material_class not in row["material_classes"]:
            continue
        rows.append(row)
    key, rev = sort.lstrip("-"), sort.startswith("-")
    rows.sort(key=lambda r: (r.get(key) is None, r.get(key)), reverse=rev)
    return J(rows)


def _fts(q):
    toks = re.findall(r"[\w.@-]+", q)
    return " ".join('"' + t.replace('"', "") + '"' for t in toks) or '""'


@app.get("/api/publications/{domain}/{split}/{pid}")
def publication(domain: str, split: str, pid: str):
    _dom(domain)
    c = db.conn()
    cfg = D.load(domain)
    recs = [db.row_to_record(r) for r in c.execute("SELECT * FROM records WHERE domain=? AND split=? AND pub_id=? ORDER BY id", (domain, split, pid))]
    corp = c.execute("SELECT * FROM corpus WHERE domain=? AND split=? AND pub_id=?", (domain, split, pid)).fetchone()
    if not corp:
        raise HTTPException(404, "publication not registered")
    by = collections.defaultdict(list)
    for r in recs:
        by[r["tbl"]].append(r)
    runs = [dict(r) for r in c.execute("SELECT id,node,purpose,model,input_ref,error,started,seconds,tokens_in,tokens_out,cost_usd FROM node_runs WHERE domain=? AND split=? AND pub_id=? ORDER BY id", (domain, split, pid))]
    return J({"corpus": {**dict(corp), "stats": db.lj(corp["stats"], {})}, "publication": (by["publications"] or [{}])[0],
              "entities": {t: by[t] for t in cfg["entity_tables"]}, "results": by["results"], "issues": by["issues"],
              "node_runs": runs, "tables": cfg["tables"], "entity_tables": cfg["entity_tables"]})


# ------------------------------------------------------------------ results
@app.get("/api/results")
def results(domain: str = "rag", split: str = "dev", pub: str = "", metric: str = "", verification: str = "", review: str = "",
            origin: str = "", kind: str = "", q: str = "", issue: str = "", scan: str = "", sort: str = "pub_id",
            limit: int = 200, offset: int = 0):
    _dom(domain)
    c = db.conn()
    sql = "SELECT * FROM records WHERE domain=? AND split=? AND tbl='results'"
    a = [domain, split]
    if pub:
        sql += " AND pub_id=?"; a.append(pub)
    if verification:
        sql += " AND verification_status IN (%s)" % ",".join("?" * len(verification.split(","))); a += verification.split(",")
    if review:
        sql += " AND review_status=?"; a.append(review)
    if metric:
        sql += " AND json_extract(data,'$.metric_name')=?"; a.append(metric)
    if origin:
        sql += " AND json_extract(data,'$.result_origin')=?"; a.append(origin)
    if kind:
        sql += " AND json_extract(evidence,'$.kind')=?"; a.append(kind)
    if q:
        sql += " AND (data LIKE ? OR pub_id LIKE ?)"; a += [f"%{q}%", f"%{q}%"]
    if scan:
        sql += " AND pub_id IN (SELECT pub_id FROM corpus WHERE domain=? AND split=? AND is_scan=?)"; a += [domain, split, 1 if scan == "true" else 0]
    rows = [db.row_to_record(r) for r in c.execute(sql, a).fetchall()]
    issues = collections.defaultdict(list)
    for r in c.execute("SELECT pub_id, rec_id, data FROM records WHERE domain=? AND split=? AND tbl='issues'", (domain, split)):
        d = db.lj(r["data"], {})
        for rid in d.get("record_ids", "").split(";"):
            if rid:
                issues[(r["pub_id"], rid)].append(d.get("check_name"))
    if issue:
        rows = [r for r in rows if issue in issues[(r["pub_id"], r["rec_id"])]]
    key, rev = sort.lstrip("-"), sort.startswith("-")
    def sk(r):
        if key in ("pub_id", "rec_id", "verification_status", "review_status"):
            return str(r.get(key))
        v = r["data"].get(key, "")
        try:
            return float(v)
        except (TypeError, ValueError):
            return str(v)
    try:
        rows.sort(key=lambda r: (sk(r), r["pub_id"], r["id"]), reverse=rev)
    except TypeError:
        rows.sort(key=lambda r: str(sk(r)), reverse=rev)
    total = len(rows)
    page = rows[offset: offset + limit]
    for r in page:
        r["issue_types"] = issues[(r["pub_id"], r["rec_id"])]
        r["quote_outcome"] = quote_outcome(r["checks"])
        r.pop("checks", None)
    facets = {"metric": collections.Counter(r["data"].get("metric_name") for r in rows).most_common(40),
              "verification": collections.Counter(r["verification_status"] for r in rows).most_common(),
              "review": collections.Counter(r["review_status"] for r in rows).most_common(),
              "kind": collections.Counter((r["evidence"] or {}).get("kind") for r in rows).most_common()}
    return J({"total": total, "rows": page, "facets": facets})


def _record(rid: int):
    r = db.conn().execute("SELECT * FROM records WHERE id=?", (rid,)).fetchone()
    if not r:
        raise HTTPException(404, "record not found")
    return db.row_to_record(r)


@app.get("/api/records/{rid}")
def record(rid: int):
    r = _record(rid)
    c = db.conn()
    cfg = D.load(r["domain"])
    linked = {}
    for field, tbl in cfg.get("result_links", {}).items():
        v = r["data"].get(field)
        if v:
            e = c.execute("SELECT * FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl=? AND rec_id=?",
                          (r["domain"], r["split"], r["pub_id"], tbl, v)).fetchone()
            linked[field] = db.row_to_record(e) if e else None
    issues = []
    for i in c.execute("SELECT * FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='issues'", (r["domain"], r["split"], r["pub_id"])):
        ii = db.row_to_record(i)
        if r["rec_id"] in ii["data"].get("record_ids", "").split(";"):
            issues.append(ii)
    hist = [dict(x) for x in c.execute("SELECT * FROM audit WHERE domain=? AND split=? AND pub_id=? AND (rec_id=? OR rec_id='') ORDER BY id DESC LIMIT 50",
                                        (r["domain"], r["split"], r["pub_id"], r["rec_id"]))]
    runs = [dict(x) for x in c.execute("SELECT id,node,purpose,model,input_ref,error,started,seconds FROM node_runs WHERE domain=? AND split=? AND pub_id=? ORDER BY id",
                                        (r["domain"], r["split"], r["pub_id"]))]
    pub = c.execute("SELECT * FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='publications'", (r["domain"], r["split"], r["pub_id"])).fetchone()
    corp = c.execute("SELECT is_scan, pages FROM corpus WHERE domain=? AND split=? AND pub_id=?", (r["domain"], r["split"], r["pub_id"])).fetchone()
    dup = None
    if r["data"].get("duplicate_of"):
        x = c.execute("SELECT id FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='results' AND rec_id=?",
                      (r["domain"], r["split"], r["pub_id"], r["data"]["duplicate_of"])).fetchone()
        dup = x["id"] if x else None
    return J({**r, "linked": linked, "issues": issues, "history": hist, "node_runs": runs, "duplicate_record": dup,
              "publication": db.row_to_record(pub)["data"] if pub else {}, "is_scan": bool(corp and corp["is_scan"]),
              "page_count": corp and corp["pages"], "columns": cfg["tables"].get(r["tbl"], [])})


@app.post("/api/records/{rid}/review")
def review(rid: int, body: dict = Body(...)):
    r = _record(rid)
    action = body.get("action")
    comment = (body.get("comment") or "").strip()
    actor = (body.get("actor") or "reviewer").strip()[:60]
    if action not in ("confirm", "correct", "reject", "reopen"):
        raise HTTPException(400, "action must be confirm | correct | reject | reopen")
    if action in ("correct", "reject") and not comment:
        raise HTTPException(400, "a comment is required for correct/reject")
    c = db.conn()
    before = {"data": r["data"], "review_status": r["review_status"], "verification_status": r["verification_status"]}
    data = dict(r["data"])
    checks = list(r["checks"])
    ver = r["verification_status"]
    if action == "correct":
        changes = body.get("data") or {}
        cols = D.load(r["domain"])["tables"][r["tbl"]]
        for k, v in changes.items():
            if k in cols and k not in ("publication_id", D.load(r["domain"])["keys"][r["tbl"]]):
                data[k] = "" if v is None else str(v)
        # keep the original extraction visible: published raw value changes are explicit and audited
        ev = dict(r["evidence"] or {})
        ev.setdefault("original_extraction", r["data"])
        if r["tbl"] == "results":
            doc, _ = _doc(r["domain"], r["split"], r["pub_id"])
            try:
                pg = int(data.get("source_page") or 0)
            except ValueError:
                pg = 0
            qv = verify_quote(doc, pg, data.get("source_fragment", ""), data.get("raw_value", ""))
            qv["by"] = "re-verification after manual correction"
            checks.append(qv)
            ver = "verified" if qv["outcome"] == "matched" and (qv.get("value_in_fragment") or data.get("source_table")) else "needs_review"
        c.execute("UPDATE records SET data=?, evidence=?, checks=?, verification_status=?, review_status='corrected', updated=? WHERE id=?",
                  (db.j(data), db.j(ev), db.j(checks), ver, now(), rid))
    else:
        status = {"confirm": "confirmed", "reject": "rejected", "reopen": "pending"}[action]
        c.execute("UPDATE records SET review_status=?, updated=? WHERE id=?", (status, now(), rid))
    db.audit(actor, f"review:{action}", r["domain"], r["split"], r["pub_id"], r["tbl"], r["rec_id"], before,
             {"data": data, "review_status": action, "verification_status": ver}, comment)
    c.commit()
    return record(rid)


@app.post("/api/issues/{rid}/status")
def issue_status(rid: int, body: dict = Body(...)):
    r = _record(rid)
    st = body.get("status")
    if st not in ("open", "resolved", "wont_fix"):
        raise HTTPException(400, "status must be open | resolved | wont_fix")
    if not (body.get("comment") or "").strip():
        raise HTTPException(400, "comment required")
    db.conn().execute("UPDATE records SET verification_status=?, updated=? WHERE id=?", (st, now(), rid))
    db.audit(body.get("actor") or "reviewer", f"issue:{st}", r["domain"], r["split"], r["pub_id"], "issues", r["rec_id"],
             {"status": r["verification_status"]}, {"status": st}, body["comment"])
    db.conn().commit()
    return {"ok": True}


@app.get("/api/issues")
def issues(domain: str = "rag", split: str = "dev", check: str = "", status: str = "", pub: str = "", limit: int = 500, offset: int = 0):
    _dom(domain)
    rows = [db.row_to_record(r) for r in db.conn().execute("SELECT * FROM records WHERE domain=? AND split=? AND tbl='issues' ORDER BY pub_id, id", (domain, split))]
    if check:
        rows = [r for r in rows if r["data"].get("check_name") == check]
    if status:
        rows = [r for r in rows if r["verification_status"] == status]
    if pub:
        rows = [r for r in rows if r["pub_id"] == pub]
    facets = collections.Counter(r["data"].get("check_name") for r in rows)
    ids = {}
    for r in db.conn().execute("SELECT id, pub_id, rec_id FROM records WHERE domain=? AND split=? AND tbl='results'", (domain, split)):
        ids[(r["pub_id"], r["rec_id"])] = r["id"]
    for r in rows:
        r["record_links"] = [{"rec_id": x, "id": ids.get((r["pub_id"], x))} for x in r["data"].get("record_ids", "").split(";") if x]
    return J({"total": len(rows), "rows": rows[offset:offset + limit], "facets": facets.most_common()})


# ------------------------------------------------------------------ source viewing
@app.get("/api/pdf/{domain}/{split}/{pid}.pdf")
def pdf(domain: str, split: str, pid: str):
    p = pdf_path(_dom(domain), split, pid)
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{pid}.pdf"'})


@app.get("/api/page/{domain}/{split}/{pid}/{page}.png")
def page_png(domain: str, split: str, pid: str, page: int, dpi: int = 110):
    p = pdf_path(_dom(domain), split, pid)
    if not p.exists():
        raise HTTPException(404)
    dpi = max(60, min(220, dpi))
    return FileResponse(render_page_png(p, domain, f"{split}_{pid}", page, dpi), media_type="image/png",
                        headers={"Cache-Control": "max-age=86400"})


@app.get("/api/page/{domain}/{split}/{pid}/{page}/text")
def page_text(domain: str, split: str, pid: str, page: int, fragment: str = "", value: str = "", cell: str = ""):
    doc, path = _doc(_dom(domain), split, pid)
    if not 1 <= page <= doc["page_count"]:
        raise HTTPException(404, "page outside PDF")
    p = doc["pages"][page - 1]
    boxes, how = [], ""
    if fragment or value:
        if p["has_text_layer"]:
            with pymupdf.open(str(path)) as d:
                pg = d[page - 1]
                for cand in [fragment, fragment[:60], fragment[-50:], value]:
                    if cand and len(cand.strip()) >= 2:
                        found = pg.search_for(cand.strip())
                        if found:
                            boxes = [[q.x0, q.y0, q.x1, q.y1] for q in found[:8]]
                            how = "text-layer search" + (" (partial)" if cand not in (fragment,) else "")
                            break
        elif p.get("ocr_words"):
            toks = norm_rag(fragment or value).lower().split()
            words = p["ocr_words"]
            wl = [w["t"].lower() for w in words]
            n = len(toks)
            for i in range(len(words)):
                if n and wl[i: i + min(n, 6)] == toks[:min(n, 6)]:
                    seg = words[i:i + n]
                    s = 72 / 300
                    boxes = [[w["b"][0] * s, w["b"][1] * s, w["b"][2] * s, w["b"][3] * s] for w in seg]
                    how = "OCR word boxes"
                    break
    if cell:
        try:
            boxes.append([float(x) for x in cell.split(",")])
            how = (how + " + " if how else "") + "table cell geometry"
        except ValueError:
            pass
    variants = {"pymupdf": p["pymupdf"], "pypdf": p["pypdf"], "ocr": p.get("ocr") or ""}
    match = {}
    if fragment:
        n = norm_rag(fragment)
        match = {k: (n in norm_rag(v)) if v else None for k, v in variants.items()}
    return J({"page": page, "width": p["width"], "height": p["height"], "has_text_layer": p["has_text_layer"],
              "ocr_engine": p.get("ocr_engine"), "ocr_conf": p.get("ocr_conf"), "variants": variants, "boxes": boxes,
              "highlight_method": how, "fragment_match": match, "page_count": doc["page_count"]})


# ------------------------------------------------------------------ vision (reviewer-driven)
import threading as _th


@app.post("/api/vision/{domain}/{split}/{pid}/{page}")
def vision_start(domain: str, split: str, pid: str, page: int):
    _dom(domain)
    from .core import extract_llm
    if not llm.available():
        raise HTTPException(400, "LLM не настроен (Администрирование → LLM и ноды)")
    model = llm.config().get("model_vision") or llm.config()["model_a"]
    _th.Thread(target=extract_llm.vision_page, args=(model, domain, split, pid, pdf_path(domain, split, pid), page), daemon=True).start()
    db.audit("reviewer", "vision_request", domain, split, pid, reason=f"page {page}, model {model}")
    db.conn().commit()
    return {"started": True, "model": model}


@app.get("/api/vision/{domain}/{split}/{pid}/{page}")
def vision_get(domain: str, split: str, pid: str, page: int):
    r = db.conn().execute("SELECT * FROM node_runs WHERE domain=? AND split=? AND pub_id=? AND node='V' AND input_ref=? ORDER BY id DESC LIMIT 1",
                          (domain, split, pid, f"page {page} image")).fetchone()
    if not r:
        return {"status": "none"}
    d = dict(r)
    return J({"status": "error" if d["error"] else "done", "id": d["id"], "model": d["model"], "seconds": d["seconds"], "started": d["started"],
              "error": d["error"], "answer": db.lj(d["parsed"])})


@app.post("/api/records/add_figure_value")
def add_figure_value(body: dict = Body(...)):
    """Add a value read from a figure (Vision or human). Never auto-verified: goes to the review queue."""
    domain, split, pid = _dom(body["domain"]), body["split"], body["pub_id"]
    cfg = D.load(domain)
    c = db.conn()
    n = c.execute("SELECT COUNT(*) FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='results'", (domain, split, pid)).fetchone()[0]
    rid = f"V{n + 1:03d}"
    data = {col: "" for col in cfg["tables"]["results"]}
    raw = str(body.get("raw_value", "")).strip()
    m = re.search(r"-?\d*\.?\d+", raw.replace(",", "."))
    data.update(publication_id=pid, result_id=rid, metric_name=body.get("metric_name", ""), raw_value=raw, raw_unit=body.get("raw_unit", ""),
                metric_value=m.group(0) if m else "", normalized_value=m.group(0) if m else "", metric_unit=body.get("raw_unit", ""),
                normalized_unit=body.get("raw_unit", ""), result_origin="primary", source_page=str(body["page"]), source_figure=body.get("figure", ""),
                extraction_status="extracted",
                note=f"read from figure by {body.get('read_by', 'Vision node V')}: printed label «{body.get('label', '')}»; requires visual review")
    if m and m.group(0).startswith("."):
        data["metric_value"] = data["normalized_value"] = "0" + m.group(0)
    ts = now()
    c.execute("INSERT INTO records(domain,split,pub_id,tbl,rec_id,data,node,extraction_status,verification_status,review_status,checks,quorum,evidence,created,updated)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (domain, split, pid, "results", rid, db.j(data), "V", "extracted", "needs_review", "pending",
               db.j([{"check": "quote", "ts": ts, "outcome": "no_fragment", "detail": "figure value: text search cannot confirm visual reading"}]),
               db.j({"outcome": "single_node", "nodes": ["V"]}), db.j({"kind": "figure", "page": body["page"], "reasons": ["source_figure_review"],
                                                                      "vision_run": body.get("vision_run")}), ts, ts))
    new_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    k = c.execute("SELECT COUNT(*) FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='issues'", (domain, split, pid)).fetchone()[0] + 1
    idata = {col: "" for col in cfg["tables"]["issues"]}
    idata.update(publication_id=pid, issue_id=f"I{k}", record_ids=rid, check_name="source_figure_review", source_page=str(body["page"]),
                 description=f"Значение {raw} прочитано с рисунка {body.get('figure', '')} ({body.get('read_by', 'Vision')}); нужна визуальная сверка")
    c.execute("INSERT INTO records(domain,split,pub_id,tbl,rec_id,data,node,verification_status,review_status,checks,quorum,evidence,created,updated)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (domain, split, pid, "issues", f"I{k}", db.j(idata), "verifier", "open", "none", "[]", "{}",
                                                       db.j({"kind": "source_figure_review"}), ts, ts))
    db.audit(body.get("actor") or "reviewer", "add_figure_value", domain, split, pid, "results", rid, after=data, reason=body.get("comment") or "")
    c.commit()
    return {"id": new_id, "rec_id": rid}


# ------------------------------------------------------------------ search
@app.get("/api/search")
def search(q: str, domain: str = "", split: str = "", limit: int = 60):
    c = db.conn()
    hits = []
    try:
        sql = "SELECT domain, split, pub_id, page, engine, snippet(pages_fts, 5, '[[', ']]', '…', 14) snip FROM pages_fts WHERE pages_fts MATCH ?"
        a = [_fts(q)]
        if domain:
            sql += " AND domain=?"; a.append(domain)
        if split:
            sql += " AND split=?"; a.append(split)
        hits = [dict(r) for r in c.execute(sql + " ORDER BY rank LIMIT ?", a + [limit])]
    except Exception as exc:
        return J({"error": f"Не удалось выполнить поиск: {exc}", "pages": [], "results": []})
    sql = "SELECT id, domain, split, pub_id, rec_id, verification_status, data FROM records WHERE tbl='results' AND data LIKE ?"
    a = [f"%{q}%"]
    if domain:
        sql += " AND domain=?"; a.append(domain)
    if split:
        sql += " AND split=?"; a.append(split)
    res = []
    for r in c.execute(sql + " LIMIT ?", a + [limit]):
        d = db.lj(r["data"], {})
        res.append({"id": r["id"], "domain": r["domain"], "split": r["split"], "pub_id": r["pub_id"], "rec_id": r["rec_id"],
                    "verification_status": r["verification_status"], "metric_name": d.get("metric_name"), "raw_value": d.get("raw_value"),
                    "source_page": d.get("source_page"), "fragment": d.get("source_fragment", "")[:160]})
    return J({"pages": hits, "results": res})


# ------------------------------------------------------------------ comparison
@app.get("/api/compare")
def compare(domain: str = "rag", split: str = "dev", metric: str = "", dataset: str = "", material_class: str = ""):
    _dom(domain)
    c = db.conn()
    rows = [db.row_to_record(r) for r in c.execute(
        "SELECT * FROM records WHERE domain=? AND split=? AND tbl='results' AND review_status!='rejected' AND json_extract(data,'$.metric_name')=?",
        (domain, split, metric))]
    ents = collections.defaultdict(dict)
    for r in c.execute("SELECT pub_id, tbl, rec_id, data FROM records WHERE domain=? AND split=? AND tbl NOT IN ('results','issues','publications')", (domain, split)):
        ents[(r["pub_id"], r["tbl"])][r["rec_id"]] = db.lj(r["data"], {})
    groups = collections.defaultdict(list)
    excluded = []
    for r in rows:
        d = r["data"]
        reason = []
        if d.get("extraction_status") != "extracted" or not d.get("metric_value"):
            reason.append("нет числового значения")
        if d.get("duplicate_of"):
            reason.append("повтор (duplicate_of)")
        if domain == "rag":
            ds = ents[(r["pub_id"], "datasets")].get(d.get("dataset_id"), {})
            ex = ents[(r["pub_id"], "experiments")].get(d.get("experiment_id"), {})
            if not ds.get("dataset_name"):
                reason.append("набор данных не указан")
            if dataset and dataset.lower() not in (ds.get("dataset_name") or "").lower():
                continue
            key = {"dataset": ds.get("dataset_name", ""), "dataset_version": ds.get("dataset_version", ""), "split": ds.get("data_split", ""),
                   "metric": d.get("metric_name"), "variant": d.get("metric_variant", ""), "k": d.get("metric_k", ""), "unit": d.get("metric_unit", ""),
                   "origin": d.get("result_origin")}
            label = (ents[(r["pub_id"], "configurations")].get(d.get("config_id"), {}) or {}).get("rag_variant", "")
            protocol = ex.get("evaluation_protocol", "")
        else:
            dev = ents[(r["pub_id"], "devices")].get(d.get("device_id"), {})
            ms = ents[(r["pub_id"], "measurements")].get(d.get("measurement_id"), {})
            mat = ents[(r["pub_id"], "materials")].get(d.get("material_id"), {})
            if material_class and mat.get("material_class") != material_class:
                continue
            if d.get("result_origin") == "cited":
                reason.append("цитируемое значение")
            if ms.get("certified") == "true":
                reason.append("сертифицированное — сравнивается отдельно")
            if ms.get("measurement_type") == "stability":
                reason.append("стабильность — сравнивается отдельно")
            area = None
            try:
                area = float(dev.get("active_area") or "")
            except ValueError:
                pass
            area_bin = "" if area is None else ("<0.1 см²" if area < 0.1 else "0.1–1 см²" if area < 1 else "≥1 см²")
            light_ok = (ms.get("spectrum") in ("AM1.5G", "") and ms.get("light_intensity") in ("100", ""))
            if ms and not light_ok:
                reason.append("не AM1.5G 100 мВт/см²")
            key = {"material_class": mat.get("material_class", ""), "device_type": dev.get("device_type", ""),
                   "spectrum": ms.get("spectrum", ""), "intensity": ms.get("light_intensity", ""), "area": area_bin,
                   "area_definition": dev.get("area_definition", ""), "aggregation": d.get("aggregation", ""),
                   "scan": ms.get("scan_direction", ""), "metric": d.get("metric_name"), "unit": d.get("metric_unit", "")}
            if not key["aggregation"]:
                reason.append("агрегация не указана")
            if not key["scan"]:
                reason.append("направление развёртки не указано")
            label = dev.get("device_label", "")
            protocol = ms.get("note", "")
        item = {"id": r["id"], "pub_id": r["pub_id"], "rec_id": r["rec_id"], "label": label, "raw_value": d.get("raw_value"),
                "value": d.get("metric_value"), "unit": d.get("metric_unit"), "verification": r["verification_status"],
                "page": d.get("source_page"), "protocol": protocol[:200]}
        if reason:
            excluded.append({**item, "reasons": reason})
        else:
            groups[json.dumps(key, ensure_ascii=False, sort_keys=True)].append(item)
    out = []
    for k, items in groups.items():
        try:
            items.sort(key=lambda x: -float(x["value"]))
        except (TypeError, ValueError):
            pass
        out.append({"key": json.loads(k), "items": items, "publications": len({i["pub_id"] for i in items})})
    out.sort(key=lambda g: (-g["publications"], -len(g["items"])))
    reason_counts = collections.Counter(r for it in excluded for r in it["reasons"]).most_common()
    return J({"groups": out, "excluded": excluded[:500], "excluded_total": len(excluded), "reason_counts": reason_counts,
              "total_considered": len(rows),
              "rule": "Записи сравниваются только внутри группы с совпадающими условиями (ключ группы); разные протоколы не объединяются в один рейтинг."})


@app.get("/api/metric_names")
def metric_names(domain: str = "rag", split: str = "dev"):
    rows = db.conn().execute("SELECT json_extract(data,'$.metric_name') m, COUNT(*) n FROM records WHERE domain=? AND split=? AND tbl='results' GROUP BY 1 ORDER BY 2 DESC LIMIT 200", (domain, split)).fetchall()
    return J([{"name": r["m"], "n": r["n"]} for r in rows if r["m"]])


# ------------------------------------------------------------------ export
@app.get("/api/export/{domain}/{split}.zip")
def export_zip(domain: str, split: str, pub: str = "", ids: str = "", actor: str = "ui"):
    _dom(domain)
    pub_ids = [x for x in pub.split(",") if x] or None
    result_ids = None
    label = "full"
    if ids:
        sel = [int(x) for x in ids.split(",") if x.isdigit()]
        result_ids = {(r["pub_id"], r["rec_id"]) for r in db.conn().execute(
            "SELECT pub_id, rec_id FROM records WHERE id IN (%s)" % ",".join("?" * len(sel)), sel)}
        pub_ids = sorted({p for p, _ in result_ids})
        label = "selection"
    elif pub_ids:
        label = "pubs"
    data = export.zip_bytes(domain, split, actor, pub_ids, result_ids, label)
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{domain}_{split}_{label}.zip"'})


@app.get("/api/export/{domain}/{split}/issues_report.csv")
def issues_report(domain: str, split: str):
    _dom(domain)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["publication_id", "issue_id", "check_name", "status", "record_ids", "description", "source_page", "source_fragment", "formula"])
    for r in db.conn().execute("SELECT * FROM records WHERE domain=? AND split=? AND tbl='issues' ORDER BY pub_id, id", (domain, split)):
        rr = db.row_to_record(r)
        d = rr["data"]
        w.writerow([rr["pub_id"], d.get("issue_id"), d.get("check_name"), rr["verification_status"], d.get("record_ids"), d.get("description"),
                    d.get("source_page"), d.get("source_fragment"), (rr["evidence"] or {}).get("formula") or ""])
    db.audit("ui", "export_issues_report", domain, split, "", reason="issues report")
    db.conn().commit()
    return Response(buf.getvalue().encode("utf-8-sig"), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{domain}_{split}_issues_report.csv"'})


# ------------------------------------------------------------------ admin
@app.get("/api/admin/llm")
def get_llm():
    return llm.public_config()


@app.post("/api/admin/llm")
def set_llm(body: dict = Body(...)):
    try:
        out = llm.save_config(body)
    except llm.LLMError as exc:
        raise HTTPException(400, str(exc))
    db.audit(body.get("actor") or "admin", "llm_settings", "", "", "", after={k: v for k, v in out.items() if k not in ("presets", "key_pools")},
             reason="LLM settings changed" + (" (backup key added; key value not logged)" if body.get("add_key") else " (keys not logged)"))
    db.conn().commit()
    return out


@app.post("/api/admin/llm/test")
def test_llm():
    return J(llm.test_connection())


@app.get("/api/admin/llm/models")
def llm_models():
    try:
        return {"models": llm.list_models()}
    except Exception as exc:
        return {"models": [], "error": str(exc)}


@app.get("/api/admin/config/{domain}")
def get_config(domain: str):
    _dom(domain)
    cfg = D.load(domain)
    return J({"yaml": (CONFIG_DIR / f"{domain}.yaml").read_text(encoding="utf-8"), "tables": cfg["tables"],
              "closed_enums": cfg["closed_enums"], "metrics": cfg.get("metrics"), "rules": cfg.get("rules")})


@app.put("/api/admin/config/{domain}")
def put_config(domain: str, body: dict = Body(...)):
    _dom(domain)
    text = body.get("yaml", "")
    try:
        parsed = yaml.safe_load(text)
        assert isinstance(parsed, dict) and parsed.get("id") == domain, "yaml must be a mapping with the same id"
        for k in ("entity_tables", "result_links", "closed_enums", "metrics", "rules"):
            assert k in parsed, f"missing key {k}"
    except Exception as exc:
        raise HTTPException(400, f"Конфигурация не принята: {exc}")
    path = CONFIG_DIR / f"{domain}.yaml"
    before = path.read_text(encoding="utf-8")
    (CONFIG_DIR / f"{domain}.yaml.bak").write_text(before, encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    try:
        D.reload(domain)
    except Exception as exc:
        path.write_text(before, encoding="utf-8")
        D.reload(domain)
        raise HTTPException(400, f"Конфигурация не загрузилась, откат: {exc}")
    db.audit(body.get("actor") or "admin", "config_update", domain, "", "", before={"yaml": before[:20000]}, after={"yaml": text[:20000]},
             reason=body.get("comment") or "")
    db.conn().commit()
    return {"ok": True}


@app.get("/api/jobs")
def jobs():
    rows = [dict(r) for r in db.conn().execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 50")]
    for r in rows:
        r["params"] = db.lj(r["params"], {})
    return J(rows)


MAX_UPLOAD = 60 * 1024 * 1024


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...), domain: str = Form(...), process: str = Form("true"),
                     mode: str = Form("default"), actor: str = Form("user")):
    """Upload a user PDF into the separate 'demo' set (never into the case corpus), validate it and queue processing.
    The PDF is data: it is only parsed, never executed."""
    from .core.pdftext import sha256_file
    from .settings import split_dir
    _dom(domain)
    if mode not in ("default", "extended"):
        raise HTTPException(400, "mode must be default or extended")
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "Файл больше 60 МБ")
    if not data.startswith(b"%PDF"):
        raise HTTPException(400, "Это не PDF: файл должен начинаться с сигнатуры %PDF")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as d:
            if d.is_encrypted:
                raise HTTPException(400, "PDF зашифрован паролем — такой файл обработать нельзя")
            pages = len(d)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"PDF не открывается: {exc}")
    if pages == 0 or pages > 300:
        raise HTTPException(400, f"Недопустимое число страниц: {pages}")
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", pathlib.Path(file.filename or "upload").stem).strip("_-")[:40] or "upload"
    if not re.match(r"[A-Za-z0-9]", stem):
        stem = "U" + stem
    folder = split_dir(domain, "demo")
    folder.mkdir(parents=True, exist_ok=True)
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    for existing in folder.glob("*.pdf"):  # dedup by content
        if sha256_file(existing) == sha:
            pid = existing.stem
            break
    else:
        pid, n = stem, 2
        while (folder / f"{pid}.pdf").exists():
            pid, n = f"{stem}_{n}", n + 1
        (folder / f"{pid}.pdf").write_bytes(data)
    pipeline.register_corpus()
    db.audit(actor[:60] or "user", "upload", domain, "demo", pid, after={"file": file.filename, "pages": pages, "sha256": sha[:16]},
             reason="user PDF upload")
    db.conn().commit()
    job = None
    if process == "true":
        job = pipeline.create_job("process", {"domains": [domain], "splits": ["demo"], "pub_ids": [pid], "mode": mode})
    return {"pub_id": pid, "domain": domain, "split": "demo", "pages": pages, "job_id": job, "sha256": sha[:16]}


@app.get("/api/jobs/{jid}")
def job_status(jid: int):
    r = db.conn().execute("SELECT * FROM jobs WHERE id=?", (jid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    d["params"] = db.lj(d["params"], {})
    return J(d)


@app.post("/api/jobs")
def new_job(body: dict = Body(...)):
    params = {k: body.get(k) for k in ("domains", "splits", "pub_ids", "mode")}
    jid = pipeline.create_job("process", params)
    db.audit(body.get("actor") or "admin", "job_start", "", "", "", after={"job": jid, **params}, reason="manual (re)run")
    db.conn().commit()
    return {"job_id": jid}


@app.get("/api/audit")
def audit(domain: str = "", pub: str = "", action: str = "", limit: int = 300):
    sql, a = "SELECT * FROM audit WHERE 1=1", []
    if domain:
        sql += " AND domain=?"; a.append(domain)
    if pub:
        sql += " AND pub_id=?"; a.append(pub)
    if action:
        sql += " AND action LIKE ?"; a.append(action + "%")
    rows = [dict(r) for r in db.conn().execute(sql + " ORDER BY id DESC LIMIT ?", a + [limit])]
    for r in rows:
        r["before"], r["after"] = db.lj(r["before"]), db.lj(r["after"])
    return J(rows)


@app.get("/api/node_runs/{nid}")
def node_run(nid: int):
    r = db.conn().execute("SELECT * FROM node_runs WHERE id=?", (nid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    d["params"], d["parsed"] = db.lj(d["params"]), db.lj(d["parsed"])
    if d["prompt"] and len(d["prompt"]) > 60000:
        d["prompt"] = d["prompt"][:60000] + "\n…[truncated in view]"
    return J(d)


@app.get("/api/metrics/{domain}/{split}")
def metrics(domain: str, split: str, refresh: bool = False):
    _dom(domain)
    path = REPORTS_DIR / f"metrics_{domain}_{split}.json"
    if refresh or not path.exists():
        res = evaluate.evaluate(domain, split)
        path.write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return J(json.loads(path.read_text()))


@app.get("/api/reports")
def reports():
    out = []
    for p in sorted(REPORTS_DIR.glob("*")):
        if p.is_file():
            out.append({"name": p.name, "bytes": p.stat().st_size})
    return out


@app.get("/api/reports/{name}")
def report(name: str):
    p = REPORTS_DIR / name
    if not p.exists() or p.parent != REPORTS_DIR:
        raise HTTPException(404)
    return FileResponse(p)


@app.post("/api/admin/check")
def admin_check(body: dict = Body(...)):
    domain, split = _dom(body.get("domain", "rag")), body.get("split", "dev")
    res = export.export_csv(domain, split, None, body.get("actor") or "admin", label="checked")
    chk = export.run_official_checker(domain, split, res["folder"], ocr=bool(body.get("ocr")))
    (REPORTS_DIR / f"{'official' if domain == 'solar' else 'kit'}_check_{domain}_{split}{'_ocr' if body.get('ocr') else ''}.json").write_text(json.dumps(chk, ensure_ascii=False, indent=1))
    return J(chk)


@app.post("/api/admin/conformance")
def admin_conformance(body: dict = Body(...)):
    """Fresh export + independent check against the kit's template (headers, enums, keys, links, provenance, units)."""
    from .core import conformance
    domain, split = _dom(body.get("domain", "rag")), body.get("split", "dev")
    res = export.export_csv(domain, split, None, body.get("actor") or "admin", label="conformance")
    rep = conformance.check_folder(domain, res["folder"], split_dir(domain, split))
    rep["withheld"] = [x for x in (pathlib.Path(res["folder"]) / "EXPORT_WITHHELD.txt").read_text(encoding="utf-8").splitlines() if x]
    (REPORTS_DIR / f"conformance_{domain}_{split}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    rep["findings"] = rep["findings"][:300]
    return J(rep)


# ------------------------------------------------------------------ page x-ray, add from page, permalinks, passport
from .core import xray as XR  # noqa: E402
from .core import normalize as NZ  # noqa: E402

STATUS_RANK = {"flagged": 0, "needs_review": 1, "verified": 2, "not_applicable": 3}


@app.get("/api/page/{domain}/{split}/{pid}/{page}/xray")
def page_xray(domain: str, split: str, pid: str, page: int):
    """Every extracted value located on the page + printed numbers nobody extracted."""
    doc, path = _doc(_dom(domain), split, pid)
    if not 1 <= page <= doc["page_count"]:
        raise HTTPException(404, "page outside PDF")
    p = doc["pages"][page - 1]
    words = XR.page_words(doc, path, page)
    nums = XR.number_words(words)
    recs = [db.row_to_record(r) for r in db.conn().execute(
        "SELECT * FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='results' AND review_status!='rejected' "
        "AND json_extract(data,'$.source_page')=?", (domain, split, pid, str(page)))]
    out, used = [], []
    for r in recs:
        d = r["data"]
        rects = XR.fragment_rects(path, page, d.get("source_fragment", ""), p["has_text_layer"])
        box, how = XR.locate(d, r["evidence"] or {}, nums, rects)
        if box:
            used.append(box)
        out.append({"id": r["id"], "rec_id": r["rec_id"], "metric": d.get("metric_name"), "raw_value": d.get("raw_value"),
                    "unit": d.get("raw_unit"), "status": r["verification_status"], "review": r["review_status"],
                    "box": box, "how": how, "kind": (r["evidence"] or {}).get("kind")})
    cands = [n for n in nums if not any(XR._inside(n["box"], u, pad=1.5) for u in used)]
    located = sum(1 for o in out if o["box"])
    return J({"page": page, "width": p["width"], "height": p["height"], "scan": not p["has_text_layer"],
              "records": out, "candidates": cands,
              "stats": {"numbers": len(nums), "extracted": len(out), "located": located, "unextracted": len(cands)}})


@app.post("/api/records/add_from_page")
def add_from_page(body: dict = Body(...)):
    """A reviewer adds a printed number the nodes missed. The quote is the printed line itself and is verified
    like any other value; nothing is auto-accepted beyond what the checks prove."""
    from .core.quotes import verify_quote
    domain, split, pid = _dom(body["domain"]), body["split"], body["pub_id"]
    page = int(body["page"])
    doc, path = _doc(domain, split, pid)
    raw = str(body.get("raw_value", "")).strip()
    metric = str(body.get("metric_name", "")).strip()
    if not raw or not metric:
        raise HTTPException(400, "Нужны значение и название показателя")
    cfg = D.load(domain)
    c = db.conn()
    n = c.execute("SELECT COUNT(*) FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='results' AND rec_id LIKE 'H%'",
                  (domain, split, pid)).fetchone()[0]
    rid = f"H{n + 1:03d}"
    while c.execute("SELECT 1 FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='results' AND rec_id=?",
                    (domain, split, pid, rid)).fetchone():
        n += 1
        rid = f"H{n + 1:03d}"
    quote = str(body.get("quote", "")).strip()
    data = {col: "" for col in cfg["tables"]["results"]}
    data.update(publication_id=pid, result_id=rid, metric_name=metric, raw_value=raw, raw_unit=str(body.get("raw_unit", "")).strip(),
                result_origin=body.get("result_origin") or "primary", cited_publication_id=body.get("cited_publication_id", ""),
                source_page=str(page), source_table=body.get("source_table", ""), source_fragment=quote, extraction_status="extracted",
                note="added by a reviewer from the page X-ray (number clicked on the page)")
    for k in ("config_id", "dataset_id", "task_id", "experiment_id", "device_id", "measurement_id", "material_id", "aggregation", "metric_k"):
        if k in data and body.get(k):
            data[k] = str(body[k])
    if data["result_origin"] == "primary":
        data["cited_publication_id"] = ""
    r = {"metric_name": metric, "raw_value": raw, "raw_unit": data["raw_unit"], "unit": data["raw_unit"]}
    m = re.search(r"[-−]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-−]?\d*[.,]?\d+", raw)
    from .core.extract_rules import _num
    r["value"] = _num(m.group(0))[0] if m else None
    NZ.normalize_result(domain, r)
    for k in ("normalized_value", "normalized_unit", "metric_value", "metric_unit"):
        data[k] = r.get(k, "")
    q = verify_quote(doc, page, quote, raw)
    ver = "verified" if q.get("outcome") == "matched" and q.get("value_in_fragment") else "needs_review"
    ts = now()
    actor = (body.get("actor") or "reviewer")[:60]
    c.execute("INSERT INTO records(domain,split,pub_id,tbl,rec_id,data,node,extraction_status,verification_status,review_status,checks,quorum,evidence,created,updated)"
              " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
              (domain, split, pid, "results", rid, db.j(data), "human", "extracted", ver, "confirmed",
               db.j([q]), db.j({"outcome": "single_node", "nodes": ["human"], "limitation": "added manually from the page"}),
               db.j({"kind": "manual", "page": page, "cell_bbox": body.get("box"), "norm": r.get("_norm"),
                     "reasons": [] if ver == "verified" else ["value_not_in_fragment" if q.get("outcome") == "matched" else "citation_not_found"]}),
               ts, ts))
    new_id = c.execute("SELECT last_insert_rowid()").fetchone()[0]
    db.audit(actor, "add_from_page", domain, split, pid, "results", rid, after=data, reason=body.get("comment") or "added from page X-ray")
    c.commit()
    return {"id": new_id, "rec_id": rid, "verification_status": ver, "quote_outcome": q.get("outcome")}


@app.get("/api/resolve/{domain}/{split}/{pid}/{rec_id}")
def resolve(domain: str, split: str, pid: str, rec_id: str, tbl: str = "results"):
    r = db.conn().execute("SELECT id FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl=? AND rec_id=?",
                          (_dom(domain), split, pid, tbl, rec_id)).fetchone()
    if not r:
        raise HTTPException(404, f"{pid}/{rec_id} не найдена — возможно, статью пересобрали без этой записи")
    return {"id": r["id"]}


def _font_file():
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial Unicode.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if pathlib.Path(f).exists():
            return f
    return None


@app.get("/api/passport/{domain}/{split}/{pid}.pdf")
def passport(domain: str, split: str, pid: str, limit: int = 150):
    """Evidence passport: every value with its quote, checks and a crop of the PDF page with the value highlighted."""
    doc, path = _doc(_dom(domain), split, pid)
    c = db.conn()
    pub = c.execute("SELECT data FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='publications'", (domain, split, pid)).fetchone()
    pubd = db.lj(pub["data"], {}) if pub else {}
    recs = [db.row_to_record(r) for r in c.execute(
        "SELECT * FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='results' AND review_status!='rejected' ORDER BY id",
        (domain, split, pid))]
    recs.sort(key=lambda r: (STATUS_RANK.get(r["verification_status"], 9), int(r["data"].get("source_page") or 0)))
    font = _font_file()
    out = pymupdf.open()
    src = pymupdf.open(str(path))
    W, H, M = 595, 842, 40
    STAT = {"verified": "Подтверждено источником", "flagged": "Противоречие правилу", "needs_review": "Нужна проверка",
            "not_applicable": "Без значения"}

    def newpage():
        pg = out.new_page(width=W, height=H)
        if font:
            pg.insert_font(fontname="F0", fontfile=font)
        pg.insert_text((M, H - 20), f"Паспорт доказательств · {domain}/{split}/{pid} · Evidence Extractor", fontsize=7,
                       fontname="F0" if font else "helv", color=(0.45, 0.5, 0.58))
        return pg

    def text(pg, y, t, size=9, color=(0.08, 0.16, 0.29), width=W - 2 * M):
        rect = pymupdf.Rect(M, y, M + width, y + 400)
        rest = pg.insert_textbox(rect, t, fontsize=size, fontname="F0" if font else "helv", color=color)
        return y + (400 - rest if rest >= 0 else 400) + 4

    pg = newpage()
    y = text(pg, 50, "Паспорт доказательств", 20)
    y = text(pg, y, pubd.get("title") or pid, 12)
    y = text(pg, y, f"{pid} · {pubd.get('year', '')} · DOI {pubd.get('DOI', '') or '—'}", 9, (0.36, 0.42, 0.5))
    counts = {}
    for r in recs:
        counts[r["verification_status"]] = counts.get(r["verification_status"], 0) + 1
    y = text(pg, y + 6, "Значений: " + str(len(recs)) + " · " + " · ".join(f"{STAT.get(k, k)}: {v}" for k, v in counts.items()), 10)
    y = text(pg, y + 4, "Для каждого значения: опубликованное и нормализованное число, страница, дословная цитата, результаты "
                        "машинных проверок и фрагмент страницы PDF с подсветкой. Сначала идут противоречия и значения на проверку.", 9,
             (0.36, 0.42, 0.5))
    nums_cache = {}
    for r in recs[:limit]:
        d = r["data"]
        try:
            page = int(d.get("source_page") or 0)
        except ValueError:
            page = 0
        q = next((x for x in r["checks"] if x.get("check") == "quote"), {})
        rules = [x for x in r["checks"] if x.get("check") not in ("quote", "table_cell", "table_row")]
        block_h = 210 if 1 <= page <= doc["page_count"] else 90
        if y + block_h > H - 40:
            pg = newpage()
            y = 40
        y = text(pg, y + 8, f"{r['rec_id']} · {d.get('metric_name')} = {d.get('raw_value')} {d.get('raw_unit') or ''}"
                            f"  →  {d.get('normalized_value') or '—'} {d.get('normalized_unit') or ''}", 11)
        col = {"verified": (0.14, 0.5, 0.49), "flagged": (0.7, 0.14, 0.09), "needs_review": (0.6, 0.36, 0)}.get(r["verification_status"], (0.4, 0.4, 0.4))
        y = text(pg, y, f"{STAT.get(r['verification_status'], r['verification_status'])} · цитата: {q.get('outcome', '—')} "
                        f"({', '.join(q.get('engines') or []) or '—'}) · стр. {page} {d.get('source_table') or d.get('source_figure') or ''} · "
                        f"{d.get('result_origin')}{' ' + d.get('cited_publication_id') if d.get('cited_publication_id') else ''}", 8.5, col)
        if d.get("source_fragment"):
            y = text(pg, y, "«" + d["source_fragment"].replace("\n", " ")[:300] + "»", 8.5, (0.2, 0.25, 0.32))
        for x in rules[:3]:
            y = text(pg, y, f"{x.get('check')}: {x.get('outcome')} {x.get('formula') or ''} {('расчёт ' + str(x.get('computed'))) if x.get('computed') is not None else ''}",
                     8, (0.36, 0.42, 0.5))
        if 1 <= page <= doc["page_count"]:
            if page not in nums_cache:
                nums_cache[page] = XR.number_words(XR.page_words(doc, path, page))
            rects = XR.fragment_rects(path, page, d.get("source_fragment", ""), doc["pages"][page - 1]["has_text_layer"])
            box, _ = XR.locate(d, r["evidence"] or {}, nums_cache[page], rects)
            sp = src[page - 1]
            if box:
                cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
                clip = pymupdf.Rect(max(0, cx - 240), max(0, cy - 55), min(sp.rect.width, cx + 240), min(sp.rect.height, cy + 55))
            else:
                clip = pymupdf.Rect(0, 0, sp.rect.width, min(sp.rect.height, 130))
            pix = sp.get_pixmap(dpi=110, clip=clip)
            ih = min(130, (W - 2 * M) * clip.height / max(1, clip.width))
            iw = ih * clip.width / max(1, clip.height)
            irect = pymupdf.Rect(M, y + 2, M + iw, y + 2 + ih)
            pg.insert_image(irect, pixmap=pix)
            pg.draw_rect(irect, color=(0.8, 0.84, 0.88), width=0.5)
            if box:
                sx, sy = iw / clip.width, ih / clip.height
                hb = pymupdf.Rect(irect.x0 + (box[0] - clip.x0) * sx - 2, irect.y0 + (box[1] - clip.y0) * sy - 2,
                                  irect.x0 + (box[2] - clip.x0) * sx + 2, irect.y0 + (box[3] - clip.y0) * sy + 2)
                pg.draw_rect(hb, color=(0.88, 0.63, 0.1), width=1.6)
            y = irect.y1 + 6
        pg.draw_line((M, y + 2), (W - M, y + 2), color=(0.88, 0.9, 0.93), width=0.5)
    if len(recs) > limit:
        pg = newpage()
        text(pg, 50, f"Показаны первые {limit} значений из {len(recs)} (сначала проблемные). Полный список — в экспорте CSV.", 10)
    data = out.tobytes(deflate=True, garbage=3)
    out.close()
    src.close()
    db.audit("ui", "export_passport", domain, split, pid, reason=f"evidence passport, {min(len(recs), limit)} values")
    c.commit()
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{pid}_passport.pdf"'})


# ------------------------------------------------------------------ frontend
DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404)
    index = DIST / "index.html"
    if not index.exists():
        return Response("Frontend is not built. Run: cd frontend && npm install && npm run build", media_type="text/plain")
    return FileResponse(index)
