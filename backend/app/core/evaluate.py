"""Quality evaluation against dev_gold. This is the ONLY module that reads dev_gold, and it runs
only after extraction (it never feeds anything back into the pipeline). test has no gold: for
test only technical coverage/verification statistics are reported.

Matching rule (documented in METRICS.md): one-to-one greedy matching within a publication.
  L1 value      : same source_page and the same number at reported precision
  L2 +metric    : L1 + same canonical metric family and same metric_k
  L3 strict     : L2 + dataset/config (RAG) or aggregation/scan direction (solar) agree
A number alone is never enough for the headline score: the headline is L3 (strict)."""
from __future__ import annotations

import collections
import csv
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import db
from . import domain as D
from .export import build_tables
from ..settings import DOMAINS

DIGITISED = re.compile(r"digitiz|digitis|vector point|geometry audit|calibrated axis|raster line", re.I)


def same_precision(a: str, b: str) -> bool:
    try:
        x, y = Decimal(str(a)), Decimal(str(b))
        if x == y:
            return True
        ex, ey = x.as_tuple().exponent, y.as_tuple().exponent
        if ex == ey:
            return False
        coarse, fine = (x, y) if ex > ey else (y, x)
        return fine.quantize(Decimal(1).scaleb(coarse.as_tuple().exponent), rounding=ROUND_HALF_UP) == coarse
    except (InvalidOperation, ValueError, TypeError):
        return False


def _toks(s):
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _sim(a, b):
    ta, tb = _toks(a), _toks(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= 0.5 or ta <= tb or tb <= ta


def load_gold(domain: str) -> dict[str, list[dict]]:
    gdir = DOMAINS[domain]["dir"] / "dev_gold"
    cfg = D.load(domain)
    out = {}
    for t in cfg["table_order"]:
        with (gdir / f"{t}.csv").open(encoding="utf-8-sig", newline="") as f:
            out[t] = list(csv.DictReader(f))
    return out


def _ctx(domain, tables):
    idx = collections.defaultdict(dict)
    for t, rows in tables.items():
        if t in ("results", "issues", "publications"):
            continue
        key = D.load(domain)["keys"][t]
        for r in rows:
            idx[(r["publication_id"], t)][r[key]] = r
    return idx


def _kind(r, evidence=None):
    if evidence and evidence.get("kind") in ("table", "text", "figure"):
        return evidence["kind"]
    if r.get("source_table"):
        return "table"
    if r.get("source_figure"):
        return "figure"
    return "text"


def _match_level(domain, g, p, gctx, pctx):
    if str(g.get("source_page")) != str(p.get("source_page")):
        return 0
    gv = g.get("normalized_value") or g.get("metric_value")
    pv = p.get("normalized_value") or p.get("metric_value")
    if not gv or not pv or not same_precision(gv, pv):
        # allow raw-vs-raw equality when units differ only in notation
        try:
            if not (g.get("raw_value") and p.get("raw_value") and same_precision(re.sub(r"[^\d.\-]", "", g["raw_value"]) or "x",
                                                                                 re.sub(r"[^\d.\-]", "", p["raw_value"]) or "y")):
                return 0
        except Exception:
            return 0
    lvl = 1
    gm, gk = D.canonical_metric(domain, g.get("metric_name", ""))
    pm, pk = D.canonical_metric(domain, p.get("metric_name", ""))
    gk = g.get("metric_k") or gk
    pk = p.get("metric_k") or pk
    if gm.lower() != pm.lower() and not _sim(g.get("metric_name"), p.get("metric_name")):
        return lvl
    if str(gk or "") != str(pk or ""):
        return lvl
    lvl = 2
    pid = g["publication_id"]
    if domain == "rag":
        gd = gctx[(pid, "datasets")].get(g.get("dataset_id"), {}).get("dataset_name", "")
        pd = pctx[(pid, "datasets")].get(p.get("dataset_id"), {}).get("dataset_name", "")
        gc = gctx[(pid, "configurations")].get(g.get("config_id"), {})
        pc = pctx[(pid, "configurations")].get(p.get("config_id"), {})
        if _sim(gd, pd) and (_sim(gc.get("rag_variant"), pc.get("rag_variant")) or _sim(gc.get("rag_variant"), pc.get("generator_model"))):
            lvl = 3
    else:
        gms = gctx[(pid, "measurements")].get(g.get("measurement_id"), {}).get("scan_direction", "")
        pms = pctx[(pid, "measurements")].get(p.get("measurement_id"), {}).get("scan_direction", "")
        if (g.get("aggregation") or "") == (p.get("aggregation") or "") and gms == pms and g.get("result_origin") == p.get("result_origin"):
            lvl = 3
    return lvl


def evaluate(domain: str, split: str = "dev") -> dict:
    if split != "dev":
        return technical_report(domain, split)
    gold = load_gold(domain)
    pred = build_tables(domain, split)
    pred.pop("_withheld", None)
    gctx, pctx = _ctx(domain, gold), _ctx(domain, pred)
    corpus = {r["pub_id"]: r for r in db.conn().execute("SELECT * FROM corpus WHERE domain=? AND split=?", (domain, split)).fetchall()}
    recs = {(r["pub_id"], r["rec_id"]): db.row_to_record(r) for r in db.conn().execute(
        "SELECT * FROM records WHERE domain=? AND split=? AND tbl='results'", (domain, split)).fetchall()}
    gres = [g for g in gold["results"] if g["extraction_status"] == "extracted"]
    printed = lambda g: not (g.get("raw_value", "").startswith("~") or DIGITISED.search(g.get("note", "")))
    by_pub_g, by_pub_p = collections.defaultdict(list), collections.defaultdict(list)
    for g in gres:
        by_pub_g[g["publication_id"]].append(g)
    for p in pred["results"]:
        if p["extraction_status"] == "extracted":
            by_pub_p[p["publication_id"]].append(p)
    matches = {1: [], 2: [], 3: []}
    for pid in set(by_pub_g) | set(by_pub_p):
        G, P = by_pub_g[pid], by_pub_p[pid]
        pidx = collections.defaultdict(list)
        for j, p in enumerate(P):
            pidx[str(p.get("source_page"))].append(j)
        for level in (3, 2, 1):
            used_g, used_p = set(), set()
            for i, g in enumerate(G):
                for j in pidx.get(str(g.get("source_page")), []):
                    if j in used_p:
                        continue
                    if _match_level(domain, g, P[j], gctx, pctx) >= level:
                        used_g.add(i)
                        used_p.add(j)
                        matches[level].append((g, P[j]))
                        break
    def prf(level, gfilter=lambda g: True, pfilter=lambda p: True):
        m = [(g, p) for g, p in matches[level] if gfilter(g) and pfilter(p)]
        ng = sum(1 for g in gres if gfilter(g))
        np_ = sum(1 for p in pred["results"] if p["extraction_status"] == "extracted" and pfilter(p))
        P = len(m) / np_ if np_ else 0.0
        R = len(m) / ng if ng else 0.0
        F = 2 * P * R / (P + R) if P + R else 0.0
        return {"matched": len(m), "gold": ng, "pred": np_, "precision": round(P, 4), "recall": round(R, 4), "f1": round(F, 4)}
    scan_pubs = {pid for pid, c in corpus.items() if c["is_scan"]}
    ev = lambda p: (recs.get((p["publication_id"], p["result_id"])) or {}).get("evidence") or {}
    qv = lambda p: ((recs.get((p["publication_id"], p["result_id"])) or {}).get("quorum") or {}).get("outcome")
    out = {
        "domain": domain, "split": split, "gold_publications": len(gold["publications"]),
        "matching_rule": __doc__.split("Matching rule")[1].strip() if "Matching rule" in __doc__ else "",
        "headline_strict_L3": prf(3), "L2_value_metric": prf(2), "L1_value_page": prf(1),
        "printed_subset_L3": prf(3, printed), "printed_subset_L2": prf(2, printed),
        "gold_digitised_share": round(1 - sum(printed(g) for g in gres) / max(1, len(gres)), 4),
        "slices_L2": {
            "scan_pdfs": prf(2, lambda g: g["publication_id"] in scan_pubs, lambda p: p["publication_id"] in scan_pubs),
            "native_pdfs": prf(2, lambda g: g["publication_id"] not in scan_pubs, lambda p: p["publication_id"] not in scan_pubs),
            "table": prf(2, lambda g: _kind(g) == "table", lambda p: _kind(p, ev(p)) == "table"),
            "text": prf(2, lambda g: _kind(g) == "text", lambda p: _kind(p, ev(p)) == "text"),
            "figure": prf(2, lambda g: _kind(g) == "figure", lambda p: _kind(p, ev(p)) == "figure"),
            "primary": prf(2, lambda g: g["result_origin"] == "primary", lambda p: p["result_origin"] == "primary"),
            "cited": prf(2, lambda g: g["result_origin"] == "cited", lambda p: p["result_origin"] == "cited"),
            "quorum_agreed_only": prf(2, pfilter=lambda p: qv(p) in ("agree", "resolved_by_C")),
        },
    }
    gpub = {r["publication_id"]: r["in_scope"] for r in gold["publications"]}
    ppub = {r["publication_id"]: r["in_scope"] for r in pred["publications"]}
    out["scope_agreement"] = {"agree": sum(gpub[k] == ppub.get(k) for k in gpub), "total": len(gpub),
                              "disagreements": {k: {"gold": gpub[k], "pred": ppub.get(k)} for k in gpub if gpub[k] != ppub.get(k)}}
    per_pub = {}
    for pid in sorted(by_pub_g):
        m3 = sum(1 for g, _ in matches[3] if g["publication_id"] == pid)
        m2 = sum(1 for g, _ in matches[2] if g["publication_id"] == pid)
        per_pub[pid] = {"gold": len(by_pub_g[pid]), "gold_printed": sum(printed(g) for g in by_pub_g[pid]), "pred": len(by_pub_p[pid]),
                        "match_L2": m2, "match_L3": m3, "scan": pid in scan_pubs}
    out["per_publication"] = per_pub
    out["technical"] = technical_report(domain, split)
    return out


def technical_report(domain: str, split: str) -> dict:
    c = db.conn()
    rows = [db.row_to_record(r) for r in c.execute("SELECT * FROM records WHERE domain=? AND split=? AND tbl='results'", (domain, split)).fetchall()]
    corpus = c.execute("SELECT * FROM corpus WHERE domain=? AND split=?", (domain, split)).fetchall()
    n = len(rows) or 1
    q = collections.Counter()
    for r in rows:
        qo = next((x.get("outcome") for x in r["checks"] if x.get("check") == "quote"), "none")
        q[qo] += 1
    iss = collections.Counter(db.lj(r["data"])["check_name"] for r in c.execute(
        "SELECT data FROM records WHERE domain=? AND split=? AND tbl='issues'", (domain, split)).fetchall())
    runs = c.execute("SELECT node, COUNT(*) n, SUM(seconds) s, SUM(tokens_in) ti, SUM(tokens_out) tt, SUM(cost_usd) cost, SUM(error IS NOT NULL) err "
                     "FROM node_runs WHERE domain=? AND split=? GROUP BY node", (domain, split)).fetchall()
    stats = [db.lj(x["stats"], {}) for x in corpus if x["stats"]]
    return {
        "publications": len(corpus), "processed": sum(1 for x in corpus if x["status"] == "done"),
        "errors": sum(1 for x in corpus if x["status"] == "error"),
        "excluded": c.execute("SELECT COUNT(*) FROM records WHERE domain=? AND split=? AND tbl='publications' AND json_extract(data,'$.in_scope')='false'",
                              (domain, split)).fetchone()[0],
        "scans": sum(1 for x in corpus if x["is_scan"]), "ocr_pages": sum(s.get("ocr_pages", 0) for s in stats),
        "results": len(rows), "coverage_pubs_with_results": len({r["pub_id"] for r in rows}),
        "quote_outcomes": dict(q), "quote_literal_share": round((q["matched"]) / n, 4),
        "quote_ocr_only_share": round(q["matched_ocr_only"] / n, 4),
        "verification": dict(collections.Counter(r["verification_status"] for r in rows)),
        "review": dict(collections.Counter(r["review_status"] for r in rows)),
        "manual_review_share": round(sum(r["review_status"] in ("confirmed", "corrected", "rejected") for r in rows) / n, 4),
        "quorum": dict(collections.Counter((r["quorum"] or {}).get("outcome", "none") for r in rows)),
        "issues_by_type": dict(iss),
        "node_runs": [dict(x) for x in runs],
        "processing_seconds": round(sum(s.get("seconds", 0) for s in stats), 1),
        "cost_usd": round(sum(s.get("cost_usd", 0) for s in stats), 4),
    }
