"""Normalisation driven by domains/<id>.yaml. Raw value/unit are never modified; normalised
values are computed only for explicit units (no rescaling by metric name alone)."""
from __future__ import annotations

import re

from . import domain as D


def fmt(v: float | None) -> str:
    if v is None:
        return ""
    s = f"{round(v, 10):.10g}"
    return "0" if s in ("-0",) else s


UNIT_CANON = [
    (r"^%$|^percent$", "%"),
    (r"^fraction\b|^frac$|^fractions\b", "fraction"),
    (r"^m\s*v$", "mV"), (r"^v$", "V"),
    (r"^m\s*a\s*(/|·|\s)?\s*cm\s*(\^|-|−|–)?\s*-?2$|^ma\s*cm\s*[-−–]\s*2$|^ma/cm2$|^ma cm-2$", "mA/cm2"),
    (r"^a\s*/\s*m2$|^a m-2$", "A/m2"),
    (r"^(ω|ohm|Ω)\s*(·|\*|\s)?\s*cm\s*\^?2$|^ohm\*cm2$|^ωcm2$", "Ohm*cm2"),
    (r"^k(ω|ohm|Ω)\s*(·|\*|\s)?\s*cm\s*\^?2$", "kOhm*cm2"),
    (r"^ev$", "eV"), (r"^mev$", "meV"),
    (r"^h$|^hr?s?$|^hours?$", "h"), (r"^min$|^minutes?$", "min"), (r"^s$|^sec$|^seconds?$", "s"), (r"^ms$", "ms"),
    (r"^days?$|^d$", "days"),
    (r"^nm$", "nm"), (r"^(µ|μ|u)m$", "µm"), (r"^cm2$|^cm\^2$|^cm²$", "cm2"), (r"^mm2$|^mm²$", "mm2"),
]


def canon_unit(u: str) -> str:
    if not u:
        return ""
    s = u.strip().lower().replace("²", "2").replace("−", "-")
    for rx, c in UNIT_CANON:
        if re.match(rx, s, re.I):
            return c
    return u.strip()


def normalize_result(domain: str, r: dict) -> dict:
    """Fill raw/normalized/metric fields of a result according to the domain config.
    Input r carries 'value' (parsed number), 'unit', 'raw_value', 'raw_unit'. Output keeps
    a normalisation trace in r['_norm']."""
    cfg = D.load(domain)
    val, unit = r.get("value"), canon_unit(r.get("unit") or r.get("raw_unit") or "")
    trace = {"input_value": val, "input_unit": unit}
    if r.get("raw_unit"):
        r["raw_unit"] = r["raw_unit"]
    if val is None:
        r["normalized_value"] = r["metric_value"] = ""
        r["normalized_unit"] = r["metric_unit"] = ""
        trace["rule"] = "no numeric value"
    elif domain == "solar":
        metric = r.get("metric_name", "")
        table = cfg["units"].get(metric)
        target = (cfg["metrics"].get(metric) or {}).get("unit", "")
        if table and unit in table:
            nv = val * table[unit]
            r["normalized_value"], r["normalized_unit"] = fmt(nv), target
            trace["rule"] = f"{unit} x {table[unit]} -> {target}"
        elif table and not unit:
            r["normalized_value"], r["normalized_unit"] = "", ""
            trace["rule"] = "unit unknown: not normalised"
        elif not table:
            r["normalized_value"], r["normalized_unit"] = fmt(val), unit
            trace["rule"] = "metric outside official list: kept as is"
        else:
            r["normalized_value"], r["normalized_unit"] = "", ""
            trace["rule"] = f"unit {unit} not convertible for {metric}"
        r["metric_value"], r["metric_unit"] = r["normalized_value"], r["normalized_unit"]
    else:  # rag
        spec = cfg["units"].get(unit)
        if spec and spec.get("factor") and spec["canonical"] != unit:
            nv = val * spec["factor"]
            r["normalized_value"], r["normalized_unit"] = fmt(nv), spec["canonical"]
            trace["rule"] = f"{unit} x {spec['factor']} -> {spec['canonical']} (explicit unit)"
        else:
            r["normalized_value"], r["normalized_unit"] = fmt(val), unit
            trace["rule"] = "kept on the published scale (no rescaling by metric name)"
        r["metric_value"], r["metric_unit"] = r["normalized_value"], r["normalized_unit"]
    trace["output"] = [r.get("normalized_value"), r.get("normalized_unit")]
    r["_norm"] = trace
    return r


def to_float(s) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None
