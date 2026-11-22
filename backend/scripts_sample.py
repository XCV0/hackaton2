"""Acceptance 15.8: random records with the full processing chain -> reports/sample_records.md.
Quotas: >=2 from scans, 2 from tables, 1 from a figure, 1 cited, 1 flagged, 1 after quorum; rest random.
A quota that cannot be met is reported as missing (never faked)."""
import json
import random
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from backend.app.core import db  # noqa: E402
from backend.app.settings import REPORTS_DIR  # noqa: E402

random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 2026)
c = db.conn()
rows = [db.row_to_record(r) for r in c.execute("SELECT * FROM records WHERE tbl='results'")]
scans = {(r["domain"], r["split"], r["pub_id"]) for r in c.execute("SELECT domain, split, pub_id FROM corpus WHERE is_scan=1")}
quotas = [
    ("скан", lambda r: (r["domain"], r["split"], r["pub_id"]) in scans, 2),
    ("таблица", lambda r: r["evidence"].get("kind") == "table" and (r["domain"], r["split"], r["pub_id"]) not in scans, 2),
    ("рисунок", lambda r: r["evidence"].get("kind") == "figure" or (r["data"].get("source_figure") and not r["data"].get("source_table")), 1),
    ("cited", lambda r: r["data"].get("result_origin") == "cited", 1),
    ("flagged", lambda r: r["verification_status"] == "flagged", 1),
    ("после кворума", lambda r: (r["quorum"] or {}).get("outcome") in ("agree", "disagree", "resolved_by_C", "unresolved"), 1),
]
picked, missing = [], []
used = set()
for name, pred, n in quotas:
    pool = [r for r in rows if pred(r) and r["id"] not in used]
    if len(pool) < n:
        missing.append(f"{name}: нужно {n}, доступно {len(pool)}")
    for r in random.sample(pool, min(n, len(pool))):
        used.add(r["id"])
        picked.append((name, r))
rest = [r for r in rows if r["id"] not in used]
for r in random.sample(rest, max(0, 10 - len(picked))):
    picked.append(("случайная", r))

out = ["# 10 случайных записей с полной цепочкой обработки", "",
       f"Сгенерировано `backend/scripts_sample.py` (seed={sys.argv[1] if len(sys.argv) > 1 else 2026}). "
       "Ссылки ведут в UI (http://127.0.0.1:8077/record/<id>).", ""]
if missing:
    out += ["**Невыполненные квоты (честно):** " + "; ".join(missing), ""]
for k, (name, r) in enumerate(picked, 1):
    d = r["data"]
    q = next((x for x in r["checks"] if x.get("check") == "quote"), {})
    rules = [x for x in r["checks"] if x.get("check") not in ("quote", "table_cell")]
    issues = [db.lj(i["data"]) for i in c.execute("SELECT data FROM records WHERE domain=? AND split=? AND pub_id=? AND tbl='issues'",
                                                  (r["domain"], r["split"], r["pub_id"]))]
    issues = [i for i in issues if r["rec_id"] in i.get("record_ids", "").split(";")]
    out += [f"## {k}. [{name}] {r['domain']}/{r['split']}/{r['pub_id']} {r['rec_id']} — {d.get('metric_name')} = {d.get('raw_value')} {d.get('raw_unit')}",
            f"- UI: /record/{r['id']}",
            f"- PDF: `{r['pub_id']}.pdf`, страница **{d.get('source_page')}**, раздел «{d.get('source_section')}», таблица «{d.get('source_table')}», рисунок «{d.get('source_figure')}»"
            + (" — **скан, текст из OCR**" if (r["domain"], r["split"], r["pub_id"]) in scans else ""),
            f"- Цитата: «{d.get('source_fragment')}»",
            f"- Нода: {r['node']} ({r['evidence'].get('kind')}); строка/столбец: {r['evidence'].get('row_label', '')} / {r['evidence'].get('col_label', '')}",
            f"- Нормализация: raw `{d.get('raw_value')} {d.get('raw_unit')}` → `{d.get('normalized_value')} {d.get('normalized_unit')}` ({(r['evidence'].get('norm') or {}).get('rule')})",
            f"- Проверка цитаты: **{q.get('outcome')}**, движки {q.get('engines')}, число в цитате: {q.get('value_in_fragment')}, ts {q.get('ts')}",
            f"- Кворум: {json.dumps(r['quorum'], ensure_ascii=False)[:300]}",
            f"- Правила: " + ("; ".join(f"{x['check']}={x.get('outcome')}" + (f" ({x.get('formula')}, расчёт {x.get('computed')})" if x.get("formula") else "") for x in rules) or "не применимы"),
            f"- Итог: verification=**{r['verification_status']}**, review={r['review_status']}, причины: {r['evidence'].get('reasons')}",
            f"- Замечания: " + ("; ".join(f"{i['check_name']}: {i['description'][:160]}" for i in issues) or "нет"), ""]
(REPORTS_DIR / "sample_records.md").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out[:6]), f"\n... {len(picked)} records written to reports/sample_records.md")
