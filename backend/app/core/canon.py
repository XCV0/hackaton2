"""Publication-level canonicalisation (entity resolution) after per-page extraction.

Per-page extraction creates one entity per mention ("BM25 configuration" in the abstract, the Table 1 column,
the Table 2 row label). This step resolves mentions to canonical entities with conservative, explainable rules:

  * same printed name and no conflicting field (values that only extend each other, "test" vs "test (1000 q.)", agree);
  * a sparse mention (label only) whose name is printed inside exactly one compatible richer entity of the same table
    (e.g. a Table 2 row label that the Table 1 entity records as its column header);
  * a sparse mention whose every reported value is reported for exactly one other entity (abstract restating the table);
  * a task name that is a word-subset of exactly one other task;
  * experiments of a single-dataset/single-task publication that do not conflict in any numeric field.

Entities that are running-header text (printed in the repeated page header and nowhere in the body) and entities with no
content at all are removed; their result links move to the single remaining entity of that table, or are cleared.
Every decision is written to the entity/result note and to the returned log — nothing is silently rewritten.
Raw values, printed fragments and source locators are never changed here."""
from __future__ import annotations

import collections
import re

from . import domain as D

PREFIX = {"configurations": "C", "datasets": "DS", "tasks": "T", "experiments": "E"}
NAME = {"configurations": "rag_variant", "datasets": "dataset_name", "tasks": "task_type", "experiments": "evaluation_protocol"}
NUMERIC_EXP = ("sample_size", "latency_ms", "tokens_per_query", "cost")


def _n(s) -> str:
    return re.sub(r"[^a-z0-9а-я]+", " ", str(s or "").lower()).strip()


def _note(row: dict, text: str):
    if "note" in row:
        row["note"] = (row["note"] + "; " if row.get("note") else "") + text


def _compat_val(a: str, b: str) -> bool:
    a, b = _n(a), _n(b)
    if not a or not b or a == b:
        return True
    return a.startswith(b + " ") or b.startswith(a + " ")  # "test" vs "test 1000 question test split"


def _substantive(row: dict, key: str, name: str) -> list[str]:
    return [c for c, v in row.items() if v and c not in (key, "publication_id", "note", name)]


class _UF:
    def __init__(self, ids):
        self.p = {i: i for i in ids}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, keep, other):
        a, b = self.find(keep), self.find(other)
        if a != b:
            self.p[b] = a


def page_header_lines(doc) -> list[str]:
    """Lines repeated at the top of several pages (digits ignored): running headers / footers."""
    cnt = collections.Counter()
    for p in doc.get("pages", []):
        t = p.get("pymupdf") or p.get("pypdf") or ""
        lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
        if len(lines) < 6:
            continue
        for ln in set(lines[:2] + lines[-2:]):
            cnt[re.sub(r"\d+", "#", ln)] += 1
    return [ln for ln, k in cnt.items() if k >= 2]


def _body_text(doc, headers: list[str]) -> str:
    """Page text without the running header/footer lines (OCR copies of a header are recognised fuzzily)."""
    import difflib
    hs = [re.sub(r"\d+", "", _n(h)).strip() for h in headers]
    out = []
    for p in doc.get("pages", []):
        t = p.get("pymupdf") or p.get("pypdf") or p.get("ocr") or ""
        for ln in t.splitlines():
            k = re.sub(r"\d+", "", _n(ln)).strip()
            if k and any(k == h or difflib.SequenceMatcher(None, k, h).ratio() >= 0.85 for h in hs):
                continue
            out.append(ln)
    return _n(" ".join(out))


def canonicalize(domain: str, ents: dict, results: list[dict], doc: dict) -> list[str]:
    if domain != "rag":
        return []
    cfg = D.load(domain)
    log: list[str] = []
    headers = page_header_lines(doc)
    header_n = " | ".join(_n(h) for h in headers)
    body = _body_text(doc, headers)
    remap: dict[tuple[str, str], str] = {}
    dropped: dict[tuple[str, str], str] = {}

    def res_of(t, ids):
        f = {"configurations": "config_id", "datasets": "dataset_id", "tasks": "task_id", "experiments": "experiment_id"}[t]
        return [r for r in results if r.get(f) in ids]

    for t in ("datasets", "tasks", "configurations", "experiments"):
        rows = ents.get(t) or []
        if not rows:
            continue
        key, name = cfg["keys"][t], NAME[t]
        byid = {r[key]: r for r in rows}

        # 1) noise: running-header text, or nothing but a note
        keep = []
        for r in rows:
            nm = _n(r.get(name))
            subst = _substantive(r, key, name)
            if nm and header_n and nm in header_n and (" " + nm + " ") not in (" " + body + " ") and len(subst) <= 2:
                dropped[(t, r[key])] = f"«{r.get(name)}» is running-header text (printed only in the repeated page header)"
                continue
            if not nm and not subst and t != "experiments":
                dropped[(t, r[key])] = "no name and no content (empty mention)"
                continue
            keep.append(r)
        for (tt, rid), why in dropped.items():
            if tt == t:
                log.append(f"{t}: removed {rid} — {why}")
        rows = keep
        uf = _UF([r[key] for r in rows])

        def compatible(a, b, text_fields_free=False):
            for c in set(a) | set(b):
                if c in (key, "publication_id", "note") or (text_fields_free and c not in NUMERIC_EXP):
                    continue
                if c == name and t != "experiments":
                    continue
                if not _compat_val(a.get(c, ""), b.get(c, "")):
                    return False
            return True

        def cluster_rows(rid):
            root = uf.find(rid)
            return [r for r in rows if uf.find(r[key]) == root]

        def cluster_compatible(x, y):
            return all(compatible(a, b, t == "experiments") for a in cluster_rows(x) for b in cluster_rows(y))

        def rich_first(a, b):
            """keep the entity with more content as the canonical one"""
            sa = len(_substantive(a, key, name))
            sb = len(_substantive(b, key, name))
            return (a, b) if sa >= sb else (b, a)

        # 2) same printed name, nothing conflicting
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if t != "experiments" and _n(a.get(name)) and _n(a.get(name)) == _n(b.get(name)) and cluster_compatible(a[key], b[key]):
                    k, o = rich_first(a, b)
                    uf.union(k[key], o[key])
                    log.append(f"{t}: {o[key]} = {k[key]} (same name «{a.get(name)}», no conflicting field)")
        if t == "configurations":
            # 3) a label-only mention whose name is printed inside exactly one richer entity of the same table
            for x in rows:
                nx = _n(x.get(name))
                if len(nx) < 4 or len(_substantive(x, key, name)) > 2:
                    continue
                cands = {uf.find(y[key]) for y in rows if uf.find(y[key]) != uf.find(x[key])
                         and len(_substantive(y, key, name)) > len(_substantive(x, key, name))
                         and (" " + nx + " ") in (" " + _n(" ".join(str(v) for c, v in y.items() if c != key)) + " ")
                         and cluster_compatible(x[key], y[key])}
                if len(cands) == 1:
                    tgt = cands.pop()
                    uf.union(tgt, x[key])
                    log.append(f"configurations: {x[key]} «{x.get(name)}» = {tgt} (the label is printed in {tgt}'s description)")
            # 4) a sparse mention whose every value is reported for exactly one other entity (abstract restating the table)
            def vals(ids):
                out = set()
                for r in res_of(t, ids):
                    if r.get("result_origin") == "primary" and r.get("value") is not None:
                        out.add((D.canonical_metric("rag", r.get("metric_name", ""))[0].lower(), str(r.get("metric_k") or ""), f"{float(r['value']):.6g}"))
                return out
            for x in rows:
                if len(_substantive(x, key, name)) > 2:
                    continue
                if len(cluster_rows(x[key])) > 1:
                    continue
                vx = vals({x[key]})
                if not vx:
                    continue
                roots = {uf.find(y[key]) for y in rows} - {uf.find(x[key])}
                hits = [rt for rt in roots if vx <= vals({r[key] for r in cluster_rows(rt)}) and cluster_compatible(x[key], rt)]
                if len(hits) == 1:
                    uf.union(hits[0], x[key])
                    log.append(f"configurations: {x[key]} «{x.get(name)}» = {hits[0]} (all its values {sorted(v[2] for v in vx)} are reported for {hits[0]} only)")
        if t == "tasks":
            for x in rows:
                tx = set(_n(x.get(name)).split())
                if not tx:
                    continue
                cands = {uf.find(y[key]) for y in rows if y is not x and tx < set(_n(y.get(name)).split()) and cluster_compatible(x[key], y[key])}
                if len(cands) == 1:
                    tgt = cands.pop()
                    uf.union(tgt, x[key])
                    log.append(f"tasks: {x[key]} «{x.get(name)}» = {tgt} (a more general name of the same task)")
        if t == "experiments":
            n_ds = len(ents.get("datasets") or [])
            n_task = len(ents.get("tasks") or [])
            # latency / tokens / hardware describe the conditions of particular configurations: such an experiment is never merged
            # into the others (RAG template README: these values must not spread to every configuration of an experiment)
            cond = lambda r: any(r.get(c) for c in ("latency_ms", "tokens_per_query", "hardware"))
            primary_ids = [r[key] for r in rows if not cond(r)
                           and (not res_of(t, {r[key]}) or any(x.get("result_origin") == "primary" for x in res_of(t, {r[key]})))]
            if n_ds <= 1 and n_task <= 1 and len(primary_ids) > 1:
                base = primary_ids[0]
                for other in primary_ids[1:]:
                    if cluster_compatible(base, other):
                        uf.union(base, other)
                        log.append(f"experiments: {other} = {base} (one dataset and one task in the paper; no conflicting sample size/cost — page fragments of one evaluation)")

        # materialise clusters: canonical row = richest member; others contribute missing fields and their names
        new_rows = []
        for r in rows:
            if uf.find(r[key]) != r[key]:
                continue
            members = cluster_rows(r[key])
            canon = max(members, key=lambda m: (len(_substantive(m, key, name)), len(_n(m.get(name))) if t == "tasks" else 0, -members.index(m)))
            row = dict(canon)
            row[key] = r[key] if canon is r else canon[key]
            others = [m for m in members if m is not canon]
            for m in others:
                for c, v in m.items():
                    if c in (key, "note", "publication_id"):
                        continue
                    if v and not row.get(c):
                        row[c] = v
                    elif t == "experiments" and c == name and v and _n(v) not in _n(row.get(c)):
                        row[c] = f"{row[c]}; {v}"
            names = [m.get(name) for m in others if t != "experiments" and m.get(name) and _n(m.get(name)) != _n(row.get(name))]
            if others:
                _note(row, f"merged mentions {', '.join(m[key] for m in others)}" + (f"; also referred to as: {'; '.join(dict.fromkeys(names))}" if names else ""))
            for m in members:
                remap[(t, m[key])] = row[key]
            new_rows.append(row)
        ents[t] = new_rows
        # dropped entities: relink to the single remaining entity, if there is exactly one
        for (tt, rid), why in list(dropped.items()):
            if tt != t:
                continue
            remap[(t, rid)] = new_rows[0][key] if len(new_rows) == 1 and t in ("datasets", "tasks") else ""
        # cluster-level de-dup is done; rewrite result links for this table now (later tables use them)
        f = {"configurations": "config_id", "datasets": "dataset_id", "tasks": "task_id", "experiments": "experiment_id"}[t]
        for r in results:
            old = r.get(f) or ""
            if not old or (t, old) not in remap:
                continue
            new = remap[(t, old)]
            if new != old:
                why = dropped.get((t, old))
                if why:
                    _note(r, f"{f} {old} removed ({why})" + (f"; linked to the only {t[:-1]} {new}" if new else ""))
                r[f] = new
    return log


# ---------------------------------------------------------------- result-level fixes

OCR_SWAP = set("0123456789")


def ocr_metric_fix(domain: str, r: dict, doc: dict) -> dict | None:
    """A metric name read by OCR that is not a known metric but differs from a known alias in one character, where one of
    the two characters is a digit (F1 -> FA, R0UGE -> ROUGE), and that alias is printed in the paper's text layer."""
    if domain != "rag" or not (r.get("_evidence") or {}).get("ocr"):
        return None
    nm = (r.get("metric_name") or "").strip()
    cfg = D.load(domain)
    if not nm or nm.lower() in cfg["metric_alias"] or len(nm) > 12:
        return None
    text = " ".join((p.get("pymupdf") or p.get("pypdf") or "") for p in doc["pages"] if p.get("has_text_layer"))
    hits = []
    for canon, spec in (cfg.get("metrics") or {}).items():
        for alias in {canon, *spec.get("aliases", [])}:
            if len(alias) != len(nm):
                continue
            diff = [(a, b) for a, b in zip(alias.lower(), nm.lower()) if a != b]
            if len(diff) == 1 and (diff[0][0] in OCR_SWAP or diff[0][1] in OCR_SWAP):
                if re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])", text, re.I):
                    hits.append((canon, alias))
    canons = {c for c, _ in hits}
    if len(canons) != 1:
        return None
    canon, alias = hits[0]
    pages = sorted({p["page"] for p in doc["pages"] if re.search(r"(?<![A-Za-z0-9])" + re.escape(alias) + r"(?![A-Za-z0-9])",
                                                              p.get("pymupdf") or p.get("pypdf") or "", re.I)})
    return {"from": nm, "to": canon, "pages": pages,
            "detail": f"OCR read the metric name as «{nm}»; one character differs from «{canon}», which the paper prints in its text (p. {', '.join(map(str, pages))})"}


SCALE_RE = re.compile(r"(fractions?\s+on\s+the\s+0\s*[-–−]\s*1\s+scale|on\s+(?:a|the)\s+0\s*[-–−]\s*1\s+scale|reported\s+as\s+fractions)", re.I)


def stated_scale(doc: dict) -> tuple[str, int] | None:
    for p in doc["pages"]:
        t = re.sub(r"\s+", " ", p.get("pymupdf") or p.get("pypdf") or p.get("ocr") or "")
        m = SCALE_RE.search(t)
        if m:
            return m.group(0), p["page"]
    return None


DELTA_WORD = re.compile(r"\b(improv\w*|gain\w*|drop\w*|increas\w*|decreas\w*|reduc\w*|outperform\w*|lower\w*|higher)\b", re.I)
BASELINE_RE = re.compile(r"\b(?:relative to|compared (?:to|with)|over|versus|vs\.?|than)\s+(?:the\s+)?([A-Za-z0-9][\w\-+/.]*(?:\s[A-Za-z0-9][\w\-+/.]*){0,3}?)(?=[.,;:)]|\s+(?:on|in|for|at|by|with|and)\b|$)", re.I)


def is_delta(r: dict) -> bool:
    raw = (r.get("raw_value") or "").strip()
    unit = (r.get("raw_unit") or r.get("metric_unit") or "").lower()
    frag = r.get("source_fragment") or ""
    if re.search(r"\bpoints?\b|\bpp\b|percentage points", unit):
        return True
    if raw and re.search(r"\bby\s+[+−-]?" + re.escape(raw) + r"\b", frag) and DELTA_WORD.search(frag):
        return True
    return bool(re.search(r"\b(delta|difference|improvement|gain)\b|Δ", f"{r.get('metric_name', '')} {r.get('metric_variant', '')}", re.I))


def delta_baseline(r: dict, configs: list[dict]) -> tuple[str, str]:
    """Baseline named in the sentence ("relative to BM25") -> the single configuration whose names contain it."""
    for src in (r.get("source_fragment") or "", r.get("metric_variant") or ""):
        m = BASELINE_RE.search(src)
        if not m:
            continue
        label = m.group(1).strip()
        nl = _n(label)
        if not nl:
            continue
        hits = [c for c in configs if (" " + nl + " ") in (" " + _n(f"{c.get('rag_variant', '')} {c.get('note', '')} {c.get('retrieval_method', '')}") + " ")
                and c.get("config_id") != r.get("config_id")]
        if len(hits) == 1:
            return hits[0]["config_id"], label
        return "", label
    return "", ""
