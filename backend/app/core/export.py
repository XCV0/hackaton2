"""Export to the official CSV formats. Column order comes from the official templates.
The export reads exactly the records the UI shows (same DB rows); rejected records are
excluded and every export is written to the audit log with file hashes."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import pathlib
import subprocess
import sys
import zipfile

from . import db
from . import domain as D
from .quotes import now
from ..settings import DOMAINS, RUNS_DIR, list_pdfs, split_dir


def _rows(domain, split, tbl, pub_ids=None, rec_filter=None):
    q = "SELECT * FROM records WHERE domain=? AND split=? AND tbl=?"
    args = [domain, split, tbl]
    rows = [db.row_to_record(r) for r in db.conn().execute(q + " ORDER BY pub_id, id", args).fetchall()]
    if pub_ids:
        rows = [r for r in rows if r["pub_id"] in pub_ids]
    rows = [r for r in rows if r["review_status"] != "rejected"]
    if rec_filter:
        rows = [r for r in rows if rec_filter(r)]
    return rows


def build_tables(domain: str, split: str, pub_ids=None, result_ids: set | None = None) -> dict[str, list[dict]]:
    cfg = D.load(domain)
    out = {}
    for tbl in cfg["table_order"]:
        flt = None
        if result_ids is not None and tbl == "results":
            flt = lambda r: (r["pub_id"], r["rec_id"]) in result_ids
        out[tbl] = [{c: (r["data"].get(c, "") or "") for c in cfg["tables"][tbl]} for r in _rows(domain, split, tbl, pub_ids, flt)]
    # a result without metric_name cannot be submitted (official checker error); it stays in the DB review queue
    def why_not(r):
        if not (r.get("metric_name") or "").strip():
            return "empty metric_name"
        if r.get("result_origin") == "cited" and not (r.get("cited_publication_id") or "").strip():
            return "cited value without a reference marker on the page (cited_publication_id would be invented)"
        return ""
    withheld = [(r, why_not(r)) for r in out["results"] if why_not(r)]
    out["results"] = [r for r in out["results"] if not why_not(r)]
    out["_withheld"] = [f"{r['publication_id']}/{r['result_id']}: {w} — kept in the service review queue" for r, w in withheld]
    # keep the relational export consistent: issues only reference exported results, duplicate_of only existing
    present = {(r["publication_id"], r["result_id"]) for r in out["results"]}
    for r in out["results"]:
        if r.get("duplicate_of") and (r["publication_id"], r["duplicate_of"]) not in present:
            r["duplicate_of"] = ""
    kept = []
    for i in out["issues"]:
        ids = [x for x in i["record_ids"].split(";") if x]
        ids2 = [x for x in ids if (i["publication_id"], x) in present]
        if ids and not ids2:
            continue
        i["record_ids"] = ";".join(ids2)
        kept.append(i)
    out["issues"] = kept
    if pub_ids is None and result_ids is None:
        # one publications row per PDF of the split, even if processing failed (flagged in reason)
        have = {r["publication_id"] for r in out["publications"]}
        for p in list_pdfs(domain, split):
            if p.stem not in have:
                row = {c: "" for c in cfg["tables"]["publications"]}
                row.update(publication_id=p.stem, in_scope="false", exclusion_reason="not processed: pipeline produced no record (see admin corpus status)")
                out["publications"].append(row)
        out["publications"].sort(key=lambda r: r["publication_id"])
    return out


def write_csv(tables: dict, folder: pathlib.Path, domain: str) -> dict:
    cfg = D.load(domain)
    folder.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for tbl, rows in tables.items():
        path = folder / f"{tbl}.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cfg["tables"][tbl], lineterminator="\n")
            w.writeheader()
            for r in rows:
                w.writerow(r)
        hashes[tbl] = {"rows": len(rows), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16]}
    return hashes


def export_csv(domain: str, split: str, out: str | None = None, actor: str = "cli", pub_ids=None, result_ids=None, label="full") -> dict:
    folder = pathlib.Path(out) if out else RUNS_DIR / "export" / f"{domain}_{split}_{label}"
    tables = build_tables(domain, split, pub_ids, result_ids)
    withheld = tables.pop("_withheld", [])
    hashes = write_csv(tables, folder, domain)
    (folder / "EXPORT_WITHHELD.txt").write_text("\n".join(withheld) + ("\n" if withheld else ""), encoding="utf-8")
    hashes["_withheld"] = len(withheld)
    db.audit(actor, "export", domain, split, "", after={"folder": str(folder), "tables": hashes, "label": label}, reason="export")
    db.conn().commit()
    return {"folder": str(folder), "tables": hashes}


def zip_bytes(domain: str, split: str, actor: str = "ui", pub_ids=None, result_ids=None, label="full") -> bytes:
    res = export_csv(domain, split, None, actor, pub_ids, result_ids, label)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(pathlib.Path(res["folder"]).glob("*.csv")):
            z.write(p, p.name)
        z.writestr("EXPORT_MANIFEST.json", json.dumps({**res, "ts": now(), "domain": domain, "split": split}, ensure_ascii=False, indent=1))
    return buf.getvalue()


def run_official_checker(domain: str, split: str, folder: str, ocr: bool = False) -> dict:
    """Run the unmodified official checker as a subprocess and capture its output."""
    ddir = DOMAINS[domain]["dir"]
    script = ddir / "tools" / "check_submission.py"
    py = sys.executable
    if domain == "rag":
        report = pathlib.Path(folder) / f"check_report{'_ocr' if ocr else ''}.json"
        cmd = [py, str(script), folder, str(split_dir(domain, split)), "--json-report", str(report)]
        if ocr:
            cmd += ["--ocr", "--ocr-language", "eng", "--tesseract", "/opt/homebrew/bin/tesseract"]
    else:
        report = None
        cmd = [py, str(script), folder, str(split_dir(domain, split))]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
    out = {"cmd": " ".join(cmd), "exit_code": p.returncode, "stdout_tail": p.stdout[-6000:], "stderr_tail": p.stderr[-2000:],
           "official": domain == "solar",
           "checker_kind": "официальный проверщик кейса (область 1)" if domain == "solar" else
                           "проверщик рекомендуемого формата RAG (schema.json: official_rag_template=false; «not an official VINITI scorer»)"}
    if domain == "solar":
        out["stdout"] = p.stdout  # the solar checker prints text only (no JSON option): its full output is kept verbatim
    if report and report.exists():
        rep = json.loads(report.read_text())
        out["report"] = {k: v for k, v in rep.items() if k not in ("errors", "warnings")}
        out["n_errors"], out["n_warnings"] = len(rep["errors"]), len(rep["warnings"])
        out["errors_head"], out["warnings_head"] = rep["errors"][:30], rep["warnings"][:30]
    log = pathlib.Path(folder) / f"checker{'_ocr' if ocr else ''}.log"
    log.write_text(p.stdout + "\n" + p.stderr)
    db.audit("system", "official_check", domain, split, "", after={k: out[k] for k in ("cmd", "exit_code")}, reason="official checker run")
    db.conn().commit()
    return out
