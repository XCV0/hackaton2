"""Domain rule engines. A violated rule never rewrites a published value: it produces an
issue with numbers, formula and source pointers. Each function returns (issues, per-record
check results)."""
from __future__ import annotations

import collections
import re

from . import domain as D
from .normalize import fmt, to_float
from .quotes import now


def _iss(check, rids, desc, page="", frag="", kind="", formula="", inputs=None):
    return {"check_name": check, "record_ids": ";".join(dict.fromkeys(rids)), "description": desc,
            "source_page": str(page or ""), "source_fragment": frag or "", "_kind": kind or check,
            "_formula": formula, "_inputs": inputs or {}}


# ------------------------------------------------------------------- solar
def solar_rules(results: list[dict], entities: dict) -> tuple[list[dict], dict]:
    cfg = D.load("solar")["rules"]
    issues, per = [], collections.defaultdict(list)
    meas = {m["measurement_id"]: m for m in entities.get("measurements", [])}
    mats = {m["material_id"]: m for m in entities.get("materials", [])}

    def nv(r):
        return to_float(r.get("normalized_value"))

    # group J-V quadruples (same device, measurement, aggregation, same source row/location)
    groups = collections.defaultdict(dict)
    for r in results:
        if r.get("result_origin") != "primary" or r.get("extraction_status") != "extracted":
            continue
        ev = r.get("_evidence") or {}
        loc = (ev.get("page"), ev.get("table") or "", ev.get("row_label") or r.get("source_fragment", "")[:40])
        key = (r.get("device_id"), r.get("measurement_id"), r.get("aggregation"), r.get("time_point") or "") + loc
        if r["metric_name"] in ("PCE", "Voc", "Jsc", "FF") and nv(r) is not None:
            groups[key].setdefault(r["metric_name"], r)
    thr = cfg["pce_consistency"]["threshold_rel"]
    for key, g in groups.items():
        if len(g) < 4:
            continue
        m = meas.get(g["PCE"].get("measurement_id") or "", {})
        raw_pin, unit = to_float(m.get("light_intensity")), (m.get("intensity_unit") or "").lower().replace(" ", "").replace("²", "2")
        factor = {"mw/cm2": 1, "mwcm-2": 1, "w/m2": 0.1, "wm-2": 0.1, "sun": 100, "suns": 100, "w/cm2": 1000}.get(unit)
        unit_note = ""
        if factor is None and not unit and raw_pin in (100.0, 1000.0, 1.0):
            # one sun written without a unit is unambiguous; the interpretation is stated in the check
            factor = {100.0: 1, 1000.0: 0.1, 1.0: 100}[raw_pin]
            unit_note = f" (единица интенсивности не указана; {m.get('light_intensity')} понято как 1 sun = 100 мВт/см²)"
        if raw_pin is None:
            pin, pin_note = cfg["pce_consistency"]["default_pin_mw_cm2"], " (Pin не указан у измерения — принято 100 мВт/см², AM1.5G)"
        elif factor is None:
            rids = [g[k]["result_id"] for k in ("PCE", "Voc", "Jsc", "FF")]
            for rid in rids:
                per[rid].append({"check": "jv_consistency", "ts": now(), "outcome": "inconclusive",
                                 "detail": f"light_intensity {m.get('light_intensity')} {m.get('intensity_unit') or '(единица не указана)'}: нельзя привести к мВт/см²"})
            continue
        else:
            pin, pin_note = raw_pin * factor, (f" (Pin {m.get('light_intensity')} {m.get('intensity_unit')} = {raw_pin * factor:g} мВт/см²)" if factor != 1 and unit else unit_note)
        voc, jsc, ff, pce = nv(g["Voc"]), nv(g["Jsc"]), nv(g["FF"]), nv(g["PCE"])
        calc = voc * jsc * (ff / 100.0) / pin * 100.0
        rel = abs(calc - pce) / pce if pce else 1
        rids = [g[k]["result_id"] for k in ("PCE", "Voc", "Jsc", "FF")]
        res = {"check": "jv_consistency", "ts": now(), "formula": "PCE = Voc·Jsc·FF / Pin",
               "inputs": {"Voc_V": voc, "Jsc_mA_cm2": jsc, "FF_pct": ff, "Pin_mW_cm2": pin, "PCE_published": pce},
               "computed": round(calc, 3), "rel_diff": round(rel, 4), "threshold": thr, "outcome": "pass" if rel <= thr else "fail"}
        for rid in rids:
            per[rid].append(res)
        if rel > thr:
            agg = g["PCE"].get("aggregation") or "не указана"
            issues.append(_iss("jv_consistency", rids,
                               f"PCE по ВАХ: {voc:g} В × {jsc:g} мА/см² × {ff:g} % / {pin:g} мВт/см² = {calc:.2f} %; опубликовано {pce:g} % "
                               f"(расхождение {rel*100:.1f} % > {thr*100:.0f} %); агрегация: {agg}{pin_note}",
                               g["PCE"].get("source_page"), g["PCE"].get("source_fragment"), formula=res["formula"], inputs=res["inputs"]))
    # Voc < Eg/q
    with_eg = [m for m in mats.values() if to_float(m.get("bandgap_value")) is not None]
    for r in results:
        if r["metric_name"] != "Voc" or nv(r) is None or r.get("result_origin") == "cited":
            continue
        mat = mats.get(r.get("material_id") or "")
        if mat is None and len(with_eg) == 1:
            mat = with_eg[0]  # the paper has a single absorber with a stated band gap
        eg = to_float((mat or {}).get("bandgap_value"))
        if eg is None:
            continue
        ok = nv(r) < eg
        per[r["result_id"]].append({"check": "voc_limit", "ts": now(), "formula": "Voc < Eg/q", "inputs": {"Voc_V": nv(r), "Eg_eV": eg},
                                    "outcome": "pass" if ok else "fail"})
        if not ok:
            issues.append(_iss("voc_limit", [r["result_id"]], f"Voc = {nv(r):g} В не меньше Eg/q = {eg:g} В (материал {mat['material_id']})",
                               r.get("source_page"), r.get("source_fragment"), formula="Voc < Eg/q", inputs={"Voc": nv(r), "Eg": eg}))
    # Jsc(EQE) vs Jsc(J-V)
    by_dev = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in results:
        if r["metric_name"] in ("Jsc", "Jsc_EQE") and nv(r) is not None and r.get("device_id"):
            by_dev[r["device_id"]][r["metric_name"]].append(r)
    for dev, mm in by_dev.items():
        for e in mm.get("Jsc_EQE", []):
            jv = [x for x in mm.get("Jsc", []) if x.get("aggregation") in ("", "champion") and not x.get("duplicate_of")]
            if not jv:
                continue
            j = jv[0]
            rel = abs(nv(e) - nv(j)) / nv(j) if nv(j) else 1
            thr5 = cfg["jsc_eqe_vs_jv"]["threshold_rel"]
            res = {"check": "eqe_consistency", "ts": now(), "formula": "|Jsc_EQE − Jsc_JV| / Jsc_JV ≤ 5 %",
                   "inputs": {"Jsc_EQE": nv(e), "Jsc_JV": nv(j)}, "rel_diff": round(rel, 4), "outcome": "pass" if rel <= thr5 else "fail"}
            per[e["result_id"]].append(res)
            per[j["result_id"]].append(res)
            if rel > thr5:
                issues.append(_iss("eqe_consistency", [e["result_id"], j["result_id"]],
                                   f"Jsc из EQE {nv(e):g} мА/см² vs Jsc из ВАХ {nv(j):g} мА/см²: {rel*100:.1f} % > 5 % (проверить сопоставимость условий)",
                                   e.get("source_page"), e.get("source_fragment"), formula=res["formula"], inputs=res["inputs"]))
    # champion vs mean
    # champion vs batch mean: same device, or batch rows whose labels name the same sample ("Champion (additive)" /
    # "Average (additive), 20 devices") measured under the same measurement
    devs = {d["device_id"]: d for d in entities.get("devices", [])}
    STOP = {"champion", "best", "record", "average", "avg", "mean", "median", "device", "devices", "cell", "cells", "of", "the"}

    def batch_key(r):
        lab = (devs.get(r.get("device_id") or "") or {}).get("device_label", "")
        toks = tuple(sorted(t for t in re.findall(r"[a-zа-я0-9]+", lab.lower()) if t not in STOP and not t.isdigit()))
        return toks or (r.get("device_id"),)

    cm = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in results:
        if r.get("aggregation") in ("champion", "mean") and nv(r) is not None and r.get("device_id") and not r.get("duplicate_of"):
            cm[(batch_key(r), r["metric_name"], r.get("measurement_id"))][r["aggregation"]].append(r)
    for (bkey, metric, _), d in cm.items():
        dev = " ".join(bkey) if isinstance(bkey, tuple) else bkey
        if metric not in ("PCE",) or not d.get("champion") or not d.get("mean"):
            continue
        ch, mn = max(d["champion"], key=nv), max(d["mean"], key=nv)
        if nv(mn) > nv(ch):
            issues.append(_iss("champion_vs_mean", [mn["result_id"], ch["result_id"]],
                               f"Среднее {metric} {nv(mn):g} больше значения лучшего прибора {nv(ch):g} (прибор {dev})",
                               mn.get("source_page"), mn.get("source_fragment")))
    # ranges
    rng = cfg["ranges"]
    for r in results:
        lim = rng.get(r["metric_name"]) if isinstance(rng, dict) else None
        if lim and nv(r) is not None and not (lim[0] <= nv(r) <= lim[1]):
            issues.append(_iss("range", [r["result_id"]], f"{r['metric_name']} = {nv(r):g} {r.get('normalized_unit')} вне диапазона {lim}",
                               r.get("source_page"), r.get("source_fragment")))
            per[r["result_id"]].append({"check": "range", "ts": now(), "inputs": {"value": nv(r), "range": lim}, "outcome": "fail"})
    return issues, per


# ------------------------------------------------------------------- rag
BOUNDED = re.compile(r"(?i)^(accuracy|acc\.?|precision|recall|f1|exact match|em|hit(?:s)?|mrr|ndcg|map|rouge-?[l12]|bleu|faithfulness)$")


DUP_FIELDS = ["experiment_id", "config_id", "dataset_id", "task_id", "metric_name", "metric_variant", "metric_k", "metric_unit",
              "aggregation", "sample_size", "result_origin", "cited_publication_id"]


def dup_compatible(a: dict, b: dict) -> bool:
    """duplicate_of is only allowed when every field the official checker compares is identical."""
    return all((a.get(f) or "") == (b.get(f) or "") for f in DUP_FIELDS) and \
        fmt(to_float(a.get("metric_value"))) == fmt(to_float(b.get("metric_value")))


RESTATE_FIELDS = ("experiment_id", "task_id", "sample_size", "metric_unit", "aggregation")


def restates(o: dict, main: dict, same_variant: bool) -> bool:
    """o repeats main's value elsewhere (abstract, figure label, discussion). Fields o leaves unstated are taken from main,
    with a note; then duplicate_of is set only if every field the official checker compares is identical."""
    if fmt(to_float(o.get("metric_value"))) != fmt(to_float(main.get("metric_value"))):
        return False
    trial, mtrial = dict(o), dict(main)
    filled, mfilled = [], []
    for f in RESTATE_FIELDS:
        if not (trial.get(f) or "") and (main.get(f) or ""):
            trial[f] = main[f]
            filled.append(f)
        elif (trial.get(f) or "") and not (main.get(f) or "") and f in ("sample_size", "aggregation"):
            mtrial[f] = trial[f]  # stated only in the restatement (e.g. the abstract gives the sample size)
            mfilled.append(f)
    if same_variant and (trial.get("metric_variant") or "") != (main.get("metric_variant") or ""):
        trial["metric_variant"] = main.get("metric_variant") or ""
        filled.append("metric_variant")
    if not dup_compatible(trial, mtrial):
        return False
    for f in mfilled:
        main[f] = mtrial[f]
    if mfilled:
        main["note"] = (main.get("note", "") + "; " if main.get("note") else "") + f"{', '.join(mfilled)} stated in restatement {o['result_id']}"
    for f in filled:
        o[f] = trial[f]
        if f == "metric_unit":
            o["normalized_unit"] = main.get("normalized_unit") or main[f]
    o["duplicate_of"] = main["result_id"]
    if filled:
        o["note"] = (o.get("note", "") + "; " if o.get("note") else "") + f"restates {main['result_id']}: {', '.join(filled)} taken from it"
    return True


def _sentences(text: str) -> list[str]:
    t = re.sub(r"-\s*\n\s*(?=\w)", "", text or "")
    t = re.sub(r"\s+", " ", t)
    return re.split(r"(?<=[.!?])\s+(?=[A-ZА-Я(\[])", t)


def rag_rules(results: list[dict], entities: dict, page_text=None) -> tuple[list[dict], dict]:
    issues, per = [], collections.defaultdict(list)
    for r in results:
        name = r.get("metric_name", "")
        base = re.sub(r"@\s*\d+.*$", "", name).strip()
        v = to_float(r.get("metric_value"))
        unit = r.get("metric_unit")
        if v is not None and BOUNDED.match(base) and unit in ("fraction", "%"):
            lim = 1 if unit == "fraction" else 100
            ok = 0 <= v <= lim
            per[r["result_id"]].append({"check": "metric_scale", "ts": now(), "inputs": {"value": v, "unit": unit, "limit": lim}, "outcome": "pass" if ok else "fail"})
            if not ok:
                issues.append(_iss("metric_scale", [r["result_id"]], f"{name} = {v:g} {unit} вне шкалы [0, {lim}]", r.get("source_page"), r.get("source_fragment")))
        if v is not None and BOUNDED.match(base) and not unit and v > 1:
            per[r["result_id"]].append({"check": "metric_scale", "ts": now(), "inputs": {"value": v, "unit": ""}, "outcome": "unknown_scale",
                                        "detail": "scale not stated; value kept as published, not rescaled"})
        if re.search(r"@\d+(?![\d.])\b", name) and not r.get("metric_k"):
            issues.append(_iss("metric_k", [r["result_id"]], f"Метрика {name} содержит @k, но metric_k пуст", r.get("source_page"), r.get("source_fragment")))
        mk = re.search(r"@(\d+)(?![\d.])", name)
        if mk and r.get("metric_k") and r["metric_k"] != mk.group(1):
            issues.append(_iss("metric_k", [r["result_id"]], f"metric_k={r['metric_k']} не совпадает с k в названии {name}", r.get("source_page"), r.get("source_fragment")))
        if r.get("result_origin") == "cited" and r.get("baseline_value"):
            issues.append(_iss("protocol_mismatch", [r["result_id"]], "baseline_value заполнен у цитируемого значения: протокол не подтверждён", r.get("source_page")))
    # same slot, different values -> contradiction; same value in another place -> duplicate_of.
    # Slots use the canonical metric family ("PubMedQA accuracy" = "accuracy"); improvement/drop values are differences,
    # not scores, and never take part. duplicate_of itself still requires checker-identical fields (dup_compatible).
    unspecified_ds = {d["dataset_id"] for d in entities.get("datasets", []) if not d.get("dataset_name")}
    DELTA = re.compile(r"improv|gain|drop|delta|differ|increase|decrease|reduction|↑|↓", re.I)

    def cm(r):
        return D.canonical_metric("rag", r.get("metric_name", ""))[0].lower()

    def usable(r):
        return (r.get("extraction_status") == "extracted" and to_float(r.get("metric_value")) is not None
                and not DELTA.search(f"{r.get('metric_name', '')} {r.get('metric_variant', '')}"))

    def same_sentence(x, y):
        """Both numbers printed in one sentence of the page (or of one quote) = several variants listed together, not two
        competing claims. Checked on the page text itself, because nodes may quote each number separately."""
        if str(x.get("source_page")) != str(y.get("source_page")):
            return False
        vx, vy = x.get("raw_value", ""), y.get("raw_value", "")
        if not vx or not vy or vx == vy:
            return False
        for f in (x.get("source_fragment") or "", y.get("source_fragment") or ""):
            if vx in f and vy in f:
                return True
        if page_text and not x.get("source_table") and not y.get("source_table"):
            try:
                text = page_text(int(x.get("source_page")))
            except (TypeError, ValueError):
                text = ""
            num = lambda v: re.compile(r"(?<![\d.])" + re.escape(v) + r"(?![\d])")
            return any(num(vx).search(sn) and num(vy).search(sn) for sn in _sentences(text))
        return False

    linked = set()
    slots = collections.defaultdict(list)
    for r in results:
        if not usable(r):
            continue
        slots[(r.get("experiment_id"), r.get("config_id"), r.get("dataset_id"), r.get("task_id"), cm(r),
               r.get("metric_variant"), r.get("metric_k"), r.get("aggregation"), r.get("result_origin"), r.get("cited_publication_id"),
               (r.get("_evidence") or {}).get("col_label", "") if (r.get("_evidence") or {}).get("kind") == "table" and r.get("_node_index") is not None and (r.get("_evidence") or {}).get("cell_bbox") else "")].append(r)
    for key, rs in slots.items():
        if len(rs) < 2 or not key[1] or key[1] in ("CT",) or not key[2] or key[2] in unspecified_ds:
            continue
        rs = sorted(rs, key=lambda r: (not r.get("source_table"), bool(r.get("source_figure"))))  # a table cell is the main record
        main = rs[0]
        for o in rs[1:]:
            if o.get("source_page") == main.get("source_page") and o.get("source_table") == main.get("source_table") and o.get("source_fragment") == main.get("source_fragment") and not same_sentence(o, main):
                continue
            if fmt(to_float(o["metric_value"])) == fmt(to_float(main["metric_value"])):
                restates(o, main, True)
            elif (str(o.get("source_page")) == str(main.get("source_page")) and (o.get("source_table") or "") == (main.get("source_table") or "")
                  and o.get("source_table")) or same_sentence(o, main):
                # one table row-slot / one sentence cannot hold two values: the extractor merged distinct variants
                linked.update([main["result_id"], o["result_id"]])
                where = f"в одной таблице {o.get('source_table')}" if o.get("source_table") else "в одном предложении"
                issues.append(_iss("extraction_linking", [main["result_id"], o["result_id"]],
                                   f"{key[4]}: {main['raw_value']} и {o['raw_value']} {where} (с. {o.get('source_page')}) привязаны к одной "
                                   "конфигурации/набору — вероятно, нода слила разные варианты. Ошибка извлечения, а не статьи.",
                                   o.get("source_page"), ""))
            else:
                issues.append(_iss("contradiction", [main["result_id"], o["result_id"]],
                                   f"{key[4]}: {main['raw_value']} (с. {main.get('source_page')}) vs {o['raw_value']} (с. {o.get('source_page')}) для одной конфигурации/набора",
                                   o.get("source_page"), o.get("source_fragment")))
    # second pass: a value restated in running text (abstract, discussion) vs the table value of the same
    # configuration/dataset/metric. Nodes often give each page its own experiment id, so experiment is not required here.
    # a variant word that the paper's own protocol uses to define the metric ("token-level F1") is the default
    # definition, not a different variant
    protocol = " ".join((e.get("evaluation_protocol") or "") for e in entities.get("experiments", [])).lower()

    def vkey(r):
        v = (r.get("metric_variant") or "").strip().lower()
        if v and protocol and re.search(re.escape(v) + r"\s+" + re.escape(D.canonical_metric("rag", r.get("metric_name", ""))[0].lower()), protocol):
            return ""
        return v

    loose = collections.defaultdict(list)
    for r in results:
        if not usable(r) or r["result_id"] in linked:
            continue
        if not r.get("config_id") or not r.get("dataset_id") or r.get("dataset_id") in unspecified_ds:
            continue
        loose[(r.get("config_id"), r.get("dataset_id"), cm(r), vkey(r), r.get("metric_k"),
               r.get("result_origin"), r.get("cited_publication_id"))].append(r)
    flagged_pairs = {tuple(sorted(i_["record_ids"].split(";"))) for i_ in issues}
    for key, rs in loose.items():
        tables = [r for r in rs if r.get("source_table") and not r.get("duplicate_of")]
        texts = [r for r in rs if not r.get("source_table") and not r.get("duplicate_of")]  # running text and printed figure labels
        if not tables or not texts:
            continue
        main = tables[0]
        for o in texts:
            if fmt(to_float(o["metric_value"])) == fmt(to_float(main["metric_value"])):
                restates(o, main, vkey(o) == vkey(main))
            elif o.get("source_figure"):
                continue  # a different number read from a figure is a reading question (figure review), not a contradiction
            elif tuple(sorted([main["result_id"], o["result_id"]])) not in flagged_pairs:
                issues.append(_iss("contradiction", [main["result_id"], o["result_id"]],
                                   f"{main.get('metric_name')}: в тексте {o['raw_value']} (с. {o.get('source_page')}), в {main.get('source_table')} "
                                   f"{main['raw_value']} (с. {main.get('source_page')}) для одной конфигурации/набора",
                                   o.get("source_page"), o.get("source_fragment")))
    # a printed difference ("improves F1 by 3.3 points relative to BM25") is checked against the absolute values when both are printed
    for r in results:
        d = r.get("_delta") or {}
        if not d.get("baseline_config_id") or to_float(r.get("metric_value")) is None:
            continue
        def absval(cfg_id):
            xs = [x for x in results if x.get("config_id") == cfg_id and cm(x) == (d["metric"] or "").lower() and not x.get("_delta")
                  and x.get("dataset_id") == r.get("dataset_id") and x.get("source_table") and to_float(x.get("metric_value")) is not None]
            return xs[0] if xs else None
        a, b = absval(r.get("config_id")), absval(d["baseline_config_id"])
        if not a or not b:
            continue
        diff = to_float(a["metric_value"]) - to_float(b["metric_value"])
        if (a.get("metric_unit") or "") == "fraction" or (not a.get("metric_unit") and abs(diff) < 1 and to_float(r["metric_value"]) > 1):
            diff *= 100
        ok = abs(diff - to_float(r["metric_value"])) <= 0.051
        per[r["result_id"]].append({"check": "delta_consistency", "ts": now(), "outcome": "pass" if ok else "fail",
                                    "formula": f"{a['result_id']} − {b['result_id']} = {a['raw_value']} − {b['raw_value']}",
                                    "computed": round(diff, 4), "inputs": {"printed_delta": r.get("raw_value"), "unit": r.get("metric_unit")}})
        if not ok:
            issues.append(_iss("contradiction", [r["result_id"], a["result_id"], b["result_id"]],
                               f"Разница {r.get('raw_value')} не совпадает с {a['raw_value']} − {b['raw_value']} = {diff:.3g}",
                               r.get("source_page"), r.get("source_fragment")))
    return issues, per


def duplicate_graph_errors(results: list[dict]) -> list[str]:
    idx = {r["result_id"]: r for r in results}
    errs = []
    for r in results:
        seen, cur = set(), r
        while cur.get("duplicate_of"):
            if cur["result_id"] in seen:
                errs.append(f"duplicate_of cycle at {r['result_id']}")
                break
            seen.add(cur["result_id"])
            if cur["duplicate_of"] == cur["result_id"]:
                errs.append(f"self duplicate {cur['result_id']}")
                break
            cur = idx.get(cur["duplicate_of"], {})
            if not cur:
                errs.append(f"duplicate_of target missing for {r['result_id']}")
                break
    return errs


def run(domain: str, results, entities, page_text=None):
    return solar_rules(results, entities) if domain == "solar" else rag_rules(results, entities, page_text)
