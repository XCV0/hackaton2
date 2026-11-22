"""Build the submission package for the mentor from the service's current records.

For every set: fresh export with the template contract -> independent template conformance check ->
the kit's unmodified tools/check_submission.py (solar: official checker, text output kept verbatim;
RAG: checker of the recommended format, its own --json-report file kept as is).
Nothing in the CSVs is edited here; problems are fixed in the pipeline and the corpus is re-run.

    python -m backend.scripts_submission [--ocr] [--out submission_for_mentor]
"""
import argparse
import datetime as dt
import json
import pathlib
import shutil
import subprocess
import sys
import zipfile

from .app.core import conformance, export
from .app.settings import DOMAINS, ROOT, split_dir

SETS = [("solar", "test"), ("solar", "dev"), ("rag", "test"), ("rag", "dev"), ("rag", "demo"), ("solar", "demo")]
TESS = shutil.which("tesseract") or "/opt/homebrew/bin/tesseract"


def kit_check(domain, split, folder, rep_dir, ocr):
    script = DOMAINS[domain]["dir"] / "tools" / "check_submission.py"
    pdfs = split_dir(domain, split)
    runs = []
    if domain == "solar":
        cmd = [sys.executable, str(script), str(folder), str(pdfs)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        out = {"checker": "официальный проверщик кейса, область 1 (tools/check_submission.py, без изменений)",
               "note": "скрипт выводит только текст (опции JSON у него нет); вывод сохранён дословно",
               "cmd": " ".join(cmd), "exit_code": p.returncode, "stdout": p.stdout, "stderr": p.stderr,
               "summary_line": next((ln for ln in p.stdout.splitlines() if ln.startswith("таблиц:")), "")}
        name = f"official_check_solar_{split}.json"
        (rep_dir / name).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        runs.append((name, out["exit_code"], out["summary_line"]))
    else:
        for use_ocr in ([False, True] if ocr else [False]):
            name = f"kit_check_rag_{split}{'_ocr' if use_ocr else ''}.json"
            cmd = [sys.executable, str(script), str(folder), str(pdfs), "--json-report", str(rep_dir / name)]
            if use_ocr:
                cmd += ["--ocr", "--ocr-language", "eng", "--tesseract", TESS]
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=14400)
            (rep_dir / name.replace(".json", ".log")).write_text(f"$ {' '.join(cmd)}\nexit {p.returncode}\n\n{p.stdout}\n{p.stderr}", encoding="utf-8")
            rep = json.loads((rep_dir / name).read_text()) if (rep_dir / name).exists() else {}
            runs.append((name, p.returncode, f"ошибок {len(rep.get('errors', []))}, на проверку {len(rep.get('warnings', []))}, цитаты {rep.get('quotes')}"))
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "submission_for_mentor"))
    ap.add_argument("--ocr", action="store_true", help="also run the RAG kit checker with --ocr (slow)")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    rep_dir = out / "reports"
    rep_dir.mkdir(parents=True)
    summary = []
    for domain, split in SETS:
        folder = out / domain / split
        export.export_csv(domain, split, str(folder), actor="submission")
        conf = conformance.check_folder(domain, folder, split_dir(domain, split))
        conf["withheld"] = [x for x in (folder / "EXPORT_WITHHELD.txt").read_text(encoding="utf-8").splitlines() if x]
        (rep_dir / f"conformance_{domain}_{split}.json").write_text(json.dumps(conf, ensure_ascii=False, indent=1), encoding="utf-8")
        kc = kit_check(domain, split, folder, rep_dir, a.ocr and split in ("test", "demo"))
        summary.append({"domain": domain, "split": split, "verdict": conf["verdict"], "structure_valid": conf["structure_valid"],
                        "errors": conf["counts"]["errors"], "warnings": conf["counts"]["warnings"], "content": conf["content"],
                        "withheld": len(conf["withheld"]), "kit_checks": kc})
        print(domain, split, conf["verdict"], kc, flush=True)
    for f in ("metrics_rag_dev.json", "metrics_solar_dev.json"):
        if (ROOT / "reports" / f).exists():
            shutil.copy(ROOT / "reports" / f, rep_dir / f)
    (rep_dir / "summary.json").write_text(json.dumps({"built": dt.datetime.now().isoformat(timespec="seconds"), "sets": summary},
                                                     ensure_ascii=False, indent=1), encoding="utf-8")
    z = out.with_suffix(".zip")
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out.rglob("*")):
            if p.is_file():
                zf.write(p, p.relative_to(out.parent))
    print("package:", z)


if __name__ == "__main__":
    main()
