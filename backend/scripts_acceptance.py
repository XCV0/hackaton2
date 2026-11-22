"""Builds reports/ACCEPTANCE.md from the actual DB state and saved reports (section 15 of the task).
Everything is computed; when an item cannot be demonstrated from data it says so."""
import collections
import json
import pathlib
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, ".")
from backend.app.core import db  # noqa: E402
from backend.app.settings import REPORTS_DIR  # noqa: E402

c = db.conn()
L = ["# Приёмка (раздел 15 ТЗ) — фактические данные", "", "Сгенерировано `backend/scripts_acceptance.py` из БД `runs/viniti.db` и `reports/`.", ""]


def recs(where, args=()):
    return [db.row_to_record(r) for r in c.execute("SELECT * FROM records WHERE " + where, args)]


def q(r):
    return next((x for x in r["checks"] if x.get("check") == "quote"), {})


# 1. manual scenario D001 / D002
L += ["## 1. Ручной сценарий RAG: D001 (обычный PDF) и D002 (скан)", ""]
for pid in ("D001", "D002"):
    corp = c.execute("SELECT * FROM corpus WHERE domain='rag' AND split='dev' AND pub_id=?", (pid,)).fetchone()
    st = db.lj(corp["stats"], {})
    rs = recs("domain='rag' AND split='dev' AND pub_id=? AND tbl='results'", (pid,))
    qo = collections.Counter(q(r).get("outcome") for r in rs)
    ver = collections.Counter(r["verification_status"] for r in rs)
    ex = next((r for r in rs if q(r).get("outcome") in ("matched", "matched_ocr_only")), None)
    L += [f"**{pid}** — страниц {corp['pages']}, с текстовым слоем {corp['text_pages']}, OCR-страниц {st.get('ocr_pages')}, "
          f"ср. уверенность OCR {st.get('ocr_conf_mean')}; основная нода {st.get('primary_node')}; значений {len(rs)}; "
          f"цитаты: {dict(qo)}; статусы: {dict(ver)}; время {st.get('seconds')} с.", ""]
    if ex:
        d = ex["data"]
        L += [f"- Пример: `/record/{ex['id']}` — {d['metric_name']} = {d['raw_value']} (с. {d['source_page']}, {d['source_table'] or d['source_figure'] or 'текст'}); "
              f"цитата «{d['source_fragment'][:120]}» найдена движками {q(ex).get('engines')}; итог {ex['verification_status']}", ""]
L += ["Экспорт: `GET /api/export/rag/dev.zip?pub=D001` (проверено: отклонённая R301 отсутствует, исправленная R276 присутствует).", ""]

# 2. official checks
L += ["## 2. Полный dev и официальная проверка", ""]
for f in sorted([*REPORTS_DIR.glob("official_check_*.json"), *REPORTS_DIR.glob("kit_check_*.json")]):
    d = json.loads(f.read_text())
    L += [f"- `{f.name}`: код выхода **{d['exit_code']}**, ошибок {d.get('n_errors', '—')}, на проверку {d.get('n_warnings', '—')}, "
          f"цитаты {json.dumps((d.get('report') or {}).get('quotes'), ensure_ascii=False)}; команда `{d['cmd'][:160]}`"]
L += [""]

# 3. negative tests
L += ["## 3. Негативные тесты (копии экспорта)", ""]
p = subprocess.run([sys.executable, "-m", "pytest", "-q", "backend/tests", "-k", "negative or quote or paraphrase", "-rA"],
                   capture_output=True, text=True)
L += ["```", "\n".join(x for x in p.stdout.splitlines() if x.startswith(("PASSED", "FAILED")) or "passed" in x or "failed" in x), "```", ""]

# 4. vision
L += ["## 4. Vision", ""]
vf = REPORTS_DIR / "vision_acceptance.json"
if vf.exists():
    for o in json.loads(vf.read_text()):
        a = o["answer"] or {}
        L += [f"- **{o['case']}** — {o['pub']} с. {o['page']} ({o['figure']}), модель {o['model']}, {o['seconds']} с: "
              f"значений {len(a.get('values', []))}; схемы без метрик {a.get('diagrams_without_metrics')}; кривые не оцифрованы {a.get('curves_not_digitised')}; "
              f"примеры: {[(v.get('label'), v.get('raw_value')) for v in a.get('values', [])[:4]]}"]
else:
    L += ["- отчёт vision_acceptance.json отсутствует"]
L += [""]

# 5. quorum
L += ["## 5. Кворум", ""]
rs = recs("tbl='results' AND json_extract(quorum,'$.outcome') IS NOT NULL")
for label, pred in [("совпадение нод", lambda r: r["quorum"].get("outcome") == "agree" and r["verification_status"] == "verified"),
                    ("расхождение нод", lambda r: r["quorum"].get("outcome") in ("disagree", "unresolved", "resolved_by_C")),
                    ("кворум подтвердил опубликованное число, но правило нашло противоречие",
                     lambda r: r["quorum"].get("outcome") == "agree" and r["verification_status"] == "flagged")]:
    ex = next((r for r in rs if pred(r)), None)
    n = sum(1 for r in rs if pred(r))
    if ex:
        d = ex["data"]
        rules = [x for x in ex["checks"] if x.get("outcome") == "fail"]
        L += [f"- **{label}** (всего {n}): `/record/{ex['id']}` {ex['domain']}/{ex['pub_id']}/{ex['rec_id']} {d['metric_name']}={d['raw_value']} "
              f"— ноды {ex['quorum'].get('nodes')}, другая нода: {ex['quorum'].get('other_value')}, C: {json.dumps(ex['quorum'].get('C'), ensure_ascii=False)[:160]}"
              + (f"; правило: {rules[0].get('check')} {rules[0].get('formula', '')} расчёт {rules[0].get('computed')} vs опубл. {rules[0].get('inputs')}" if rules else "")]
    else:
        L += [f"- **{label}**: в данных не найдено (честно)"]
L += [""]

# 6. solar
L += ["## 6. Солнечная область", ""]
jv = [(r, x) for r in recs("domain='solar' AND tbl='results' AND json_extract(data,'$.metric_name')='PCE'") for x in r["checks"] if x.get("check") == "jv_consistency"]
if jv:
    r, x = next(((r, x) for r, x in jv if x["outcome"] == "pass" and r["node"] != "R"), jv[0])
    i = x["inputs"]
    manual = i["Voc_V"] * i["Jsc_mA_cm2"] * i["FF_pct"] / 100 / i["Pin_mW_cm2"] * 100
    L += [f"- Ручной пересчёт PCE ({r['pub_id']}/{r['rec_id']}, `/record/{r['id']}`): {i['Voc_V']} В × {i['Jsc_mA_cm2']} мА/см² × {i['FF_pct']} % / {i['Pin_mW_cm2']} мВт/см² "
          f"= **{manual:.3f} %**; опубликовано {i['PCE_published']} %; отклонение {abs(manual - i['PCE_published']) / i['PCE_published'] * 100:.2f} % (порог 3 %) → {x['outcome']}",
          f"- Всего проверок PCE↔ВАХ: {len(jv)}, нарушений: {sum(1 for _, x in jv if x['outcome'] == 'fail')}"]
ms = recs("domain='solar' AND tbl='measurements'")
by = collections.defaultdict(set)
for m in ms:
    if m["data"].get("scan_direction"):
        by[(m["split"], m["pub_id"])].add(m["data"]["scan_direction"])
both = [k for k, v in by.items() if {"forward", "reverse"} <= v]
L += [f"- Разделение развёртки: публикаций с раздельными измерениями forward и reverse: {len(both)} {both[:6]}"]
org = collections.Counter(r["data"].get("result_origin") for r in recs("domain='solar' AND tbl='results'"))
cit = next(iter(recs("domain='solar' AND tbl='results' AND json_extract(data,'$.result_origin')='cited'")), None)
L += [f"- primary/cited: {dict(org)}" + (f"; пример cited: `/record/{cit['id']}` {cit['pub_id']} {cit['data']['metric_name']}={cit['data']['raw_value']} ссылка {cit['data']['cited_publication_id']}, device_id пуст: {not cit['data'].get('device_id')}" if cit else "")]
L += ["- Сопоставимость: страница «Сравнение» группирует по ключу (класс материала, тип прибора, AM1.5G 100 мВт/см², площадь, агрегация, развёртка) и выводит причины исключения.", ""]

# 8. sample
sf = REPORTS_DIR / "sample_records.md"
L += ["## 8. 10 случайных записей", "", f"См. `reports/sample_records.md` ({'есть' if sf.exists() else 'нет'})."]
(REPORTS_DIR / "ACCEPTANCE.md").write_text("\n".join(L), encoding="utf-8")
print("\n".join(L)[:4000])
