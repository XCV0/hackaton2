"""Domain plug-in loader: schema columns come from the official templates; vocabularies,
normalisation and rule parameters come from domains/<id>.yaml. The core never hard-codes
domain fields."""
from __future__ import annotations

import csv
import functools
import json
import re

import yaml

from ..settings import CONFIG_DIR, DOMAINS


@functools.lru_cache(maxsize=None)
def load(domain: str) -> dict:
    cfg = yaml.safe_load((CONFIG_DIR / f"{domain}.yaml").read_text(encoding="utf-8"))
    tdir = DOMAINS[domain]["dir"] / cfg["template_dir"]
    tables = {}
    for path in sorted(tdir.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            tables[path.stem] = next(csv.reader(f))
    schema_json = tdir / "schema.json"
    if schema_json.exists():
        sj = json.loads(schema_json.read_text(encoding="utf-8"))
        for t, cols in sj["tables"].items():
            if tables.get(t) and tables[t] != cols:
                raise ValueError(f"template CSV and schema.json disagree for {t}")
        cfg["schema_json"] = sj
    cfg["tables"] = tables
    order = ["publications"] + cfg["entity_tables"] + ["results", "issues"]
    cfg["table_order"] = [t for t in order if t in tables]
    # string-ify enums ("true"/"false")
    cfg["closed_enums"] = {k: [str(v).lower() if isinstance(v, bool) else str(v) for v in vals]
                           for k, vals in cfg.get("closed_enums", {}).items()}
    cfg["keys"] = {t: cols[1] if t != "publications" else "publication_id" for t, cols in tables.items()}
    alias = {}
    for canon, spec in cfg.get("metrics", {}).items():
        alias[canon.lower()] = canon
        for a in spec.get("aliases", []):
            alias[a.lower()] = canon
    cfg["metric_alias"] = alias
    return cfg


def reload(domain: str) -> dict:
    load.cache_clear()
    return load(domain)


def canonical_metric(domain: str, name: str) -> tuple[str, int | None]:
    """Return canonical metric family and @k (if the name carries one). Never changes the stored name."""
    cfg = load(domain)
    if not name:
        return "", None
    k = None
    m = re.search(r"@\s*(\d+)\b(?![.\d])", name)
    if m:
        k = int(m.group(1))
    base = re.sub(r"@\s*\d+(\.\d+)?", "", name).strip().lower()
    base = re.sub(r"[\s_]+", " ", base)
    hit = cfg["metric_alias"].get(base, cfg["metric_alias"].get(base.replace("-", " ")))
    if hit:
        return hit, k
    # a longer printed name that contains exactly one metric alias as a whole word ("PubMedQA accuracy", "strict accuracy")
    found = {canon for alias, canon in cfg["metric_alias"].items()
             if len(alias) > 1 and re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", base)}
    return (found.pop() if len(found) == 1 else name.strip()), k
