"""Template conformance check (independent of the kits' check_submission.py scripts).

The contract is read from the kits themselves, never re-typed by hand where a file exists:
  * file names, headers and column order — from the empty CSVs in <kit>/submission_template/;
  * RAG closed / recommended enums — from <kit>/submission_template/schema.json;
  * solar vocabularies — from the tables of <kit>/submission_template/README.md (the solar kit has no schema.json).
Every finding carries the rule it comes from. The report separates
  «структура валидна» (files, headers, enums, keys, links) from
  «содержание» (how many publications were processed and how many values were extracted),
so a header-only template can never be reported as a successful run of the service."""
from __future__ import annotations

import csv
import math
import pathlib
import re

from ..settings import DOMAINS

# ---- rule sources (domain-specific parts not available as machine-readable files)
SOLAR_README_VOCAB = {  # submission_template/README.md, «Поля» tables (solar kit has no schema.json)
    "publications.in_scope": ["true", "false"],
    "materials.material_class": ["perovskite", "CIGS", "CdTe", "kesterite", "Sb2Se3", "thin-film Si", "other"],
    "materials.dimensionality": ["3D", "2D", "2D-3D"],
    "materials.bandgap_method": ["Tauc", "EQE", "PL", "cited"],
    "materials.bandgap_unit": ["eV"],
    "devices.device_role": ["control", "target", "record"],
    "devices.device_type": ["cell", "minimodule", "module"],
    "devices.architecture": ["n-i-p", "p-i-n", "substrate", "superstrate"],
    "devices.substrate_type": ["rigid", "flexible"],
    "devices.area_definition": ["designated illumination", "aperture", "total"],
    "devices.area_unit": ["cm2"],
    "layers.layer_function": ["front_contact", "ETL", "absorber", "passivation", "HTL", "interlayer", "recombination", "back_contact"],
    "layers.thickness_unit": ["nm"],
    "measurements.measurement_type": ["J-V", "MPP tracking", "EQE", "stability"],
    "measurements.scan_direction": ["reverse", "forward", "average"],
    "measurements.stability_protocol": ["ISOS-D", "ISOS-L", "ISOS-T", "other"],
    "measurements.mask_used": ["true", "false"],
    "measurements.certified": ["true", "false"],
    "results.aggregation": ["champion", "mean", "median"],
    "results.result_origin": ["primary", "cited"],
    "results.extraction_status": ["extracted", "present_not_extractable", "absent"],
}
SOLAR_TARGET_UNIT = {"PCE": "%", "FF": "%", "HI": "%", "retained_PCE": "%", "Voc": "V", "Jsc": "mA/cm2",
                     "Jsc_EQE": "mA/cm2", "Rs": "Ohm*cm2", "Rsh": "Ohm*cm2", "T80": "h"}

KEYS = {
    "solar": {"publications": "publication_id", "materials": "material_id", "devices": "device_id", "layers": "layer_id",
              "measurements": "measurement_id", "results": "result_id", "issues": "issue_id"},
}
LINKS = {  # (table, field, target, many)
    "solar": [("devices", "absorber_material_id", "materials", False), ("layers", "device_id", "devices", False),
              ("measurements", "device_id", "devices", True), ("results", "device_id", "devices", False),
              ("results", "measurement_id", "measurements", False), ("results", "material_id", "materials", False)],
    "rag": [("results", "experiment_id", "experiments", False), ("results", "config_id", "configurations", False),
            ("results", "dataset_id", "datasets", False), ("results", "task_id", "tasks", False)],
}
NUMERIC = {
    "solar": {"results.metric_value", "results.normalized_value", "results.spread_value", "results.n_devices", "results.time_point",
              "materials.bandgap_value", "devices.active_area", "layers.layer_order", "layers.layer_thickness",
              "measurements.light_intensity"},
    "rag": {"results.metric_k", "results.metric_value", "results.baseline_value", "results.sample_size", "results.normalized_value",
            "configurations.chunk_size", "configurations.chunk_overlap", "configurations.top_k",
            "experiments.latency_ms", "experiments.tokens_per_query", "experiments.sample_size"},
}
INTEGER = {"results.source_page", "issues.source_page", "layers.layer_order", "results.n_devices", "results.metric_k", "configurations.top_k"}
# exact spellings (case matters: «Na» is sodium, «nA» is nanoampere)
PLACEHOLDERS = {"NaN", "nan", "NAN", "null", "NULL", "Null", "None", "unknown", "Unknown", "UNKNOWN", "n/a", "N/A", "undefined",
                "inf", "-inf", "+inf", "Inf", "Infinity", "-Infinity"}
SOFT_PLACEHOLDERS = {"none", "NONE", "-", "—", "?"}  # may be a printed value («retrieval: none»): reported for review
FREE_TEXT = {"note", "description", "source_fragment", "title", "evaluation_protocol", "exclusion_reason", "authors", "source_section",
             "rag_variant", "device_label", "material_name_raw", "stress_conditions", "hardware", "prompt_strategy", "context_strategy"}
DUP_FIELDS = {
    "rag": ["experiment_id", "config_id", "dataset_id", "task_id", "metric_name", "metric_variant", "metric_k", "metric_unit",
            "metric_value", "aggregation", "sample_size", "result_origin", "cited_publication_id"],
    "solar": ["device_id", "measurement_id", "material_id", "metric_name", "metric_unit", "metric_value", "aggregation",
              "time_point", "time_unit", "result_origin", "cited_publication_id"],
}


def kit_dir(domain: str) -> pathlib.Path:
    return DOMAINS[domain]["dir"]


def contract(domain: str) -> dict:
    """Headers (in order) of every template file, keys, enums, with their sources."""
    tdir = kit_dir(domain) / "submission_template"
    files = sorted(tdir.glob("*.csv"))
    headers = {}
    for f in files:
        with open(f, encoding="utf-8-sig", newline="") as fh:
            headers[f.stem] = next(csv.reader(fh), [])
    c = {"template_dir": str(tdir), "headers": headers, "sources": {"headers": f"{tdir.name}/*.csv (заголовки пустых таблиц)"}}
    if domain == "rag":
        import json
        schema = json.loads((tdir / "schema.json").read_text(encoding="utf-8"))
        c["schema_headers"] = schema["tables"]
        c["keys"] = schema["keys"]
        c["enums"] = schema.get("enums", {})
        c["recommended_enums"] = schema.get("recommended_enums", {})
        c["official"] = bool(schema.get("official_rag_template"))
        c["schema_version"] = schema.get("version")
        c["sources"].update(enums="submission_template/schema.json: enums (закрытые), recommended_enums (рекомендуемые)",
                            rules="submission_template/README.md RAG-комплекта")
    else:
        c["keys"] = KEYS["solar"]
        c["enums"] = SOLAR_README_VOCAB
        c["recommended_enums"] = {}
        c["official"] = True
        c["sources"].update(enums="submission_template/README.md, таблицы раздела «Поля» (schema.json в солнечном комплекте нет)",
                            rules="submission_template/README.md солнечного комплекта")
    return c


def _num(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def check_folder(domain: str, folder: str | pathlib.Path, pdf_dir: str | pathlib.Path | None = None) -> dict:
    folder = pathlib.Path(folder)
    C = contract(domain)
    findings = []

    def add(sev, rule, where, msg):
        findings.append({"severity": sev, "rule": rule, "where": where, "message": msg})

    # ---- files and headers
    data: dict[str, list[dict]] = {}
    for t, hdr in C["headers"].items():
        p = folder / f"{t}.csv"
        if not p.exists():
            add("error", "files", f"{t}.csv", "нет файла из шаблона")
            data[t] = []
            continue
        raw = p.read_bytes()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            add("error", "encoding", f"{t}.csv", "файл не в UTF-8")
            text = raw.decode("utf-8", "replace")
        if text.startswith("﻿"):
            add("warning", "encoding", f"{t}.csv", "UTF-8 с BOM (шаблон без BOM)")
            text = text[1:]
        rows = list(csv.reader(text.splitlines(keepends=True) if text else []))
        got = rows[0] if rows else []
        if got != hdr:
            miss = [c for c in hdr if c not in got]
            extra = [c for c in got if c not in hdr]
            add("error", "headers", f"{t}.csv", "заголовок не совпадает с шаблоном"
                + (f"; нет колонок: {', '.join(miss)}" if miss else "") + (f"; лишние: {', '.join(extra)}" if extra else "")
                + ("; порядок колонок другой" if not miss and not extra else ""))
        if domain == "rag" and C["schema_headers"].get(t) != hdr:
            add("error", "schema", f"{t}.csv", "заголовок пустого шаблона расходится с schema.json")
        recs = []
        for i, r in enumerate(rows[1:], 2):
            if len(r) != len(got):
                add("error", "csv", f"{t}.csv:{i}", f"в строке {len(r)} ячеек, в заголовке {len(got)}")
                continue
            recs.append({"_line": i, **dict(zip(got, r))})
        data[t] = recs
    for p in folder.glob("*.csv"):
        if p.stem not in C["headers"]:
            add("warning", "files", p.name, "CSV, которого нет в шаблоне")

    # ---- cell hygiene, enums, numbers
    for t, recs in data.items():
        for r in recs:
            w = f"{t}.csv:{r['_line']}"
            for col, v in r.items():
                if col == "_line" or v is None:
                    continue
                if v != v.strip():
                    add("warning", "cells", w, f"{col}: пробелы по краям «{v[:40]}»")
                if v.strip() in PLACEHOLDERS and col not in FREE_TEXT:
                    add("error", "empty_cells", w, f"{col} = «{v}»: вместо пропуска должна быть пустая ячейка")
                elif v.strip() in SOFT_PLACEHOLDERS and col not in FREE_TEXT and not col.startswith("raw_"):
                    add("warning", "empty_cells", w, f"{col} = «{v}»: если это пропуск — ячейка должна быть пустой; если напечатано в статье — пояснить в note")
                q = f"{t}.{col}"
                if v and q in C["enums"] and v not in C["enums"][q]:
                    add("error", "enum", w, f"{col} = «{v}» нет в словаре {C['enums'][q]}")
                if v and q in C["recommended_enums"] and v not in C["recommended_enums"][q]:
                    add("warning", "enum", w, f"{col} = «{v}» не из рекомендуемых {C['recommended_enums'][q]}")
                if v and q in NUMERIC[domain] and _num(v) is None:
                    add("error", "number", w, f"{col} = «{v}» не число")
                if v and q in INTEGER and not re.fullmatch(r"\d+", v):
                    add("error", "number", w, f"{col} = «{v}» должен быть целым")

    # ---- keys
    pubs = {}
    for r in data.get("publications", []):
        if r["publication_id"] in pubs:
            add("error", "keys", f"publications.csv:{r['_line']}", f"publication_id {r['publication_id']} повторяется")
        pubs[r["publication_id"]] = r
    ids: dict[str, set] = {}
    for t, key in C["keys"].items():
        if t == "publications" or t not in data:
            continue
        seen = set()
        for r in data[t]:
            k = (r["publication_id"], r.get(key, ""))
            if not r.get(key):
                add("error", "keys", f"{t}.csv:{r['_line']}", f"пустой {key}")
            elif k in seen:
                add("error", "keys", f"{t}.csv:{r['_line']}", f"{key} {k[1]} повторяется в публикации {k[0]}")
            seen.add(k)
            if r["publication_id"] not in pubs:
                add("error", "links", f"{t}.csv:{r['_line']}", f"публикации {r['publication_id']} нет в publications.csv")
        ids[t] = seen

    # ---- publications: scope
    for pid, r in pubs.items():
        w = f"publications.csv:{r['_line']}"
        if r.get("in_scope") == "false":
            if not r.get("exclusion_reason"):
                add("error", "scope", w, f"{pid}: исключена без exclusion_reason")
            for t, recs in data.items():
                if t != "publications" and any(x["publication_id"] == pid for x in recs):
                    add("error", "scope", w, f"{pid}: исключена, но есть строки в {t}.csv")
        elif r.get("in_scope") == "true" and r.get("exclusion_reason") and domain == "rag":
            add("error", "scope", w, f"{pid}: in_scope=true, но exclusion_reason заполнен")
        elif not r.get("in_scope"):
            add("error", "scope", w, f"{pid}: пустой in_scope")

    # ---- links
    for t, col, target, many in LINKS[domain]:
        for r in data.get(t, []):
            v = (r.get(col) or "").strip()
            if not v:
                continue
            vals = [x.strip() for x in v.split(";")] if many else [v]
            if not many and ";" in v:
                add("error", "links", f"{t}.csv:{r['_line']}", f"{col} = «{v}»: ссылочное поле должно содержать один идентификатор")
            for x in vals:
                if x and (r["publication_id"], x) not in ids.get(target, set()):
                    add("error", "links", f"{t}.csv:{r['_line']}", f"{col} = {x}: нет такой записи в {target}.csv той же публикации")

    # ---- results
    res = {(r["publication_id"], r["result_id"]): r for r in data.get("results", [])}
    for r in data.get("results", []):
        w = f"results.csv:{r['_line']}"
        st = r.get("extraction_status", "")
        if not r.get("metric_name"):
            add("error", "results", w, "пустой metric_name")
        if not st:
            add("error", "results", w, "пустой extraction_status")
        if st == "extracted":
            if not r.get("raw_value"):
                add("error", "provenance", w, "extracted без raw_value")
            sp = r.get("source_page", "")
            if not re.fullmatch(r"\d+", sp or "") or int(sp) < 1:
                add("error", "provenance", w, f"extracted без source_page ≥ 1 (source_page = «{sp}»)")
            if not (r.get("source_fragment") or r.get("source_table") or r.get("source_figure")):
                add("error", "provenance", w, "extracted без source_fragment / source_table / source_figure")
        o = r.get("result_origin", "")
        if o == "cited" and not r.get("cited_publication_id"):
            add("error", "cited", w, "cited без cited_publication_id")
        if o == "primary" and r.get("cited_publication_id"):
            add("error", "cited", w, "primary с заполненным cited_publication_id")
        if domain == "solar" and o == "cited" and (r.get("device_id") or r.get("measurement_id")):
            add("error", "cited", w, "у cited device_id и measurement_id остаются пустыми (README солнечного шаблона)")
        mv, nv = r.get("metric_value", ""), r.get("normalized_value", "")
        if (mv == "") != (nv == "") or (mv and nv and _num(mv) is not None and _num(nv) is not None and _num(mv) != _num(nv)):
            add("error", "normalization", w, f"metric_value «{mv}» не совпадает с normalized_value «{nv}»")
        if r.get("metric_unit", "") != r.get("normalized_unit", ""):
            add("error", "normalization", w, f"metric_unit «{r.get('metric_unit')}» не совпадает с normalized_unit «{r.get('normalized_unit')}»")
        if domain == "solar":
            tu = SOLAR_TARGET_UNIT.get(r.get("metric_name", ""))
            if tu and nv and r.get("normalized_unit") != tu:
                add("error", "normalization", w, f"{r['metric_name']}: normalized_unit «{r.get('normalized_unit')}», по шаблону «{tu}»")
        d = r.get("duplicate_of", "")
        if d:
            tgt = res.get((r["publication_id"], d))
            if not tgt:
                add("error", "duplicate_of", w, f"duplicate_of = {d}: нет такой записи")
            elif d == r["result_id"]:
                add("error", "duplicate_of", w, "duplicate_of ссылается сам на себя")
            else:
                if tgt.get("duplicate_of"):
                    add("error", "duplicate_of", w, f"основная запись {d} сама помечена как повтор (у основной записи duplicate_of пуст)")
                diff = [f for f in DUP_FIELDS[domain] if (tgt.get(f) or "") != (r.get(f) or "")
                        and not (f == "metric_value" and _num(tgt.get(f)) is not None and _num(tgt.get(f)) == _num(r.get(f)))]
                if diff:
                    add("error", "duplicate_of", w, f"повтор {d} отличается полями: {', '.join(diff)}")

    # ---- issues
    for r in data.get("issues", []):
        w = f"issues.csv:{r['_line']}"
        rids = [x.strip() for x in (r.get("record_ids") or "").split(";") if x.strip()]
        if not rids:
            add("warning", "issues", w, "record_ids пуст")
        for x in rids:
            if (r["publication_id"], x) not in res:
                add("error", "issues", w, f"record_ids: {x} нет в results.csv")
        if not r.get("check_name"):
            add("error", "issues", w, "пустой check_name")
        if not r.get("description"):
            add("error", "issues", w, "пустой description")
        sp = r.get("source_page", "")
        if sp and (not re.fullmatch(r"\d+", sp) or int(sp) < 1):
            add("error", "issues", w, f"source_page = «{sp}» должен быть целым ≥ 1")

    # ---- coverage of the PDF set: a publications row for every PDF and nothing else
    pdfs = sorted(p.stem for p in pathlib.Path(pdf_dir).glob("*.pdf")) if pdf_dir else []
    if pdf_dir:
        for pid in pdfs:
            if pid not in pubs:
                add("error", "coverage", "publications.csv", f"нет строки для {pid}.pdf (строка нужна для каждого PDF набора)")
        for pid in pubs:
            if pid not in pdfs:
                add("error", "coverage", "publications.csv", f"{pid}: нет такого PDF в наборе")

    errors = [f for f in findings if f["severity"] == "error"]
    rows_total = sum(len(v) for v in data.values())
    results = data.get("results", [])
    content = {
        "pdfs_in_set": len(pdfs) if pdf_dir else None,
        "publications": len(pubs),
        "in_scope": sum(1 for p in pubs.values() if p.get("in_scope") == "true"),
        "excluded": sum(1 for p in pubs.values() if p.get("in_scope") == "false"),
        "publications_with_results": len({r["publication_id"] for r in results}),
        "results": len(results),
        "extracted": sum(1 for r in results if r.get("extraction_status") == "extracted"),
        "duplicates": sum(1 for r in results if r.get("duplicate_of")),
        "cited": sum(1 for r in results if r.get("result_origin") == "cited"),
        "issues": len(data.get("issues", [])),
        "rows_by_table": {t: len(v) for t, v in data.items()},
    }
    if rows_total == 0:
        verdict = "ПУСТОЙ НАБОР: структура совпадает с шаблоном, но данных нет — это не проверка работы сервиса"
    elif errors:
        verdict = f"СТРУКТУРА НЕ ВАЛИДНА: {len(errors)} ошибок"
    else:
        verdict = (f"структура валидна; обработано публикаций: {content['publications']} (в области {content['in_scope']}, "
                   f"исключено {content['excluded']}), извлечено результатов: {content['extracted']}")
    by_rule = {}
    for f in findings:
        by_rule.setdefault(f"{f['severity']}:{f['rule']}", 0)
        by_rule[f"{f['severity']}:{f['rule']}"] += 1
    return {
        "domain": domain, "folder": str(folder), "pdf_dir": str(pdf_dir) if pdf_dir else None,
        "template": {"dir": C["template_dir"], "official": C["official"], "schema_version": C.get("schema_version"),
                     "sources": C["sources"]},
        "structure_valid": not errors and rows_total > 0,
        "header_only": rows_total == 0,
        "verdict": verdict,
        "content": content,
        "counts": {"errors": len(errors), "warnings": len(findings) - len(errors), "by_rule": by_rule},
        "findings": findings,
    }


def check_template_itself(domain: str) -> dict:
    """The empty template must pass as «header-only» — and never as a successful run."""
    return check_folder(domain, kit_dir(domain) / "submission_template")
