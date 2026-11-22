"""Acceptance tests. Negative tests mutate COPIES of exported results, never the originals."""
import csv
import importlib.util
import pathlib
import re
import shutil
import sys
import warnings

import pytest

warnings.filterwarnings("ignore")
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.app.core import domain as D, normalize, rules  # noqa: E402
from backend.app.core.pdftext import extract_document  # noqa: E402
from backend.app.core.pipeline import compare_nodes  # noqa: E402
from backend.app.core.quotes import verify_quote  # noqa: E402
from backend.app.settings import DOMAINS, RUNS_DIR  # noqa: E402

RAG = DOMAINS["rag"]["dir"]


def _checker():
    spec = importlib.util.spec_from_file_location("official_rag_checker", RAG / "tools" / "check_submission.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def d001():
    return extract_document(RAG / "dev" / "D001.pdf", "rag", "dev_D001", do_ocr=False)


# ------------------------------------------------------------------ quote verification
def test_quote_matched(d001):
    q = verify_quote(d001, 7, "Table 2: Ablation study of the STM (SN, STG) and", ".422")
    assert q["outcome"] == "matched" and "pymupdf" in q["engines"]


def test_quote_wrong_page(d001):
    q = verify_quote(d001, 3, "Table 2: Ablation study of the STM (SN, STG) and")
    assert q["outcome"] == "wrong_page" and 7 in q["other_pages"]


def test_paraphrase_is_not_a_quote(d001):
    q = verify_quote(d001, 7, "Table 2, row SN, column HotpotQA", ".422")
    assert q["outcome"] == "not_found" and q["paraphrase_suspect"]


def test_page_outside_pdf(d001):
    assert verify_quote(d001, 999, "anything")["outcome"] == "bad_page"


def test_value_anchoring(d001):
    q = verify_quote(d001, 7, "Table 2: Ablation study of the STM (SN, STG) and", "0.999")
    assert q["outcome"] == "matched" and q["value_in_fragment"] is False


def test_no_cross_engine_or_cross_page_glue(d001):
    p6 = d001["pages"][5]["pymupdf"].split()
    p7 = d001["pages"][6]["pymupdf"].split()
    glued = " ".join(p6[-3:] + p7[:3])
    assert verify_quote(d001, 6, glued)["outcome"] != "matched"


# ------------------------------------------------------------------ official checker on mutated copies
@pytest.fixture(scope="module")
def export_copy(tmp_path_factory):
    src = RUNS_DIR / "export" / "rag_dev_R"
    if not (src / "results.csv").exists():
        pytest.skip("run `python -m backend.cli export --domain rag --split dev --out runs/export/rag_dev_R` first")
    return src


def _mutate(src, tmp, fn):
    dst = tmp / "sub"
    shutil.copytree(src, dst)
    for f in dst.glob("*.json"):
        f.unlink()
    rows = list(csv.DictReader(open(dst / "results.csv", encoding="utf-8")))
    fields = list(rows[0].keys())
    rows = fn(rows)
    with open(dst / "results.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    # restrict to one publication to keep the test fast
    for t in dst.glob("*.csv"):
        rr = list(csv.DictReader(open(t, encoding="utf-8")))
        fl = list(csv.DictReader(open(t, encoding="utf-8")).fieldnames)
        with open(t, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fl, lineterminator="\n")
            w.writeheader()
            w.writerows([r for r in rr if r["publication_id"] in ("D001", "D099")])
    pdfdir = tmp / "pdf"
    pdfdir.mkdir()
    (pdfdir / "D001.pdf").symlink_to(RAG / "dev" / "D001.pdf")
    return _checker().validate(dst, pdfdir)


def _first_d001(rows, pred=lambda r: True):
    return next(i for i, r in enumerate(rows) if r["publication_id"] == "D001" and r["source_fragment"] and pred(r))


def test_checker_baseline_clean(export_copy, tmp_path):
    rep = _mutate(export_copy, tmp_path, lambda rows: rows)
    assert rep["errors"] == [] and rep["quotes"]["matched"] == rep["quotes"]["requested"]


def test_negative_wrong_page(export_copy, tmp_path):
    def f(rows):
        i = _first_d001(rows)
        rows[i]["source_page"] = "1"
        return rows
    rep = _mutate(export_copy, tmp_path, f)
    assert any("quote not found on declared page" in w for w in rep["warnings"]) and rep["exit_code"] == 2


def test_negative_paraphrase(export_copy, tmp_path):
    def f(rows):
        i = _first_d001(rows)
        rows[i]["source_fragment"] = "Таблица 1, строка RA-CoT, столбец EM"
        return rows
    rep = _mutate(export_copy, tmp_path, f)
    assert rep["quotes"]["unresolved"] >= 1 and rep["exit_code"] == 2


def test_negative_unknown_publication(export_copy, tmp_path):
    def f(rows):
        r = dict(rows[_first_d001(rows)])
        r["publication_id"], r["result_id"] = "D099", "R9999"
        return rows + [r]
    rep = _mutate(export_copy, tmp_path, f)
    assert any("publication does not exist" in e for e in rep["errors"]) and rep["exit_code"] == 1


def test_negative_broken_link(export_copy, tmp_path):
    def f(rows):
        rows[_first_d001(rows)]["config_id"] = "C_DOES_NOT_EXIST"
        return rows
    rep = _mutate(export_copy, tmp_path, f)
    assert any("does not exist in configurations" in e for e in rep["errors"])


def test_negative_duplicate_cycle(export_copy, tmp_path):
    def f(rows):
        a = _first_d001(rows)
        b = _first_d001(rows[a + 1:]) + a + 1
        rows[a]["duplicate_of"] = rows[b]["result_id"]
        rows[b]["duplicate_of"] = rows[a]["result_id"]
        return rows
    rep = _mutate(export_copy, tmp_path, f)
    assert any("duplicate_of cycle" in e for e in rep["errors"])
    # our own graph check detects it too
    res = [{"result_id": "R1", "duplicate_of": "R2"}, {"result_id": "R2", "duplicate_of": "R1"}, {"result_id": "R3", "duplicate_of": "R3"}]
    errs = rules.duplicate_graph_errors(res)
    assert any("cycle" in e for e in errs) and any("self" in e for e in errs)


# ------------------------------------------------------------------ normalisation
def _res(metric, raw, unit, **kw):
    r = {"metric_name": metric, "raw_value": raw, "raw_unit": unit, "value": float(raw.replace(",", "")), "unit": unit, **kw}
    return normalize.normalize_result("solar", r)


def test_solar_normalisation_units():
    assert _res("Voc", "1123", "mV")["normalized_value"] == "1.123"
    assert _res("FF", "0.71", "fraction")["normalized_value"] == "71"
    assert _res("PCE", "21.3", "%")["normalized_unit"] == "%"
    r = _res("Jsc", "23.1", "")
    assert r["normalized_value"] == "" and "unit unknown" in r["_norm"]["rule"]


def test_rag_no_rescaling_by_metric_name():
    r = normalize.normalize_result("rag", {"metric_name": "EM", "raw_value": ".422", "value": 0.422, "unit": ""})
    assert r["normalized_value"] == "0.422" and r["normalized_unit"] == ""
    r = normalize.normalize_result("rag", {"metric_name": "Latency", "raw_value": "1.5", "value": 1.5, "unit": "s"})
    assert r["normalized_value"] == "1500" and r["normalized_unit"] == "ms"


# ------------------------------------------------------------------ solar rules
def _solar_set(voc, jsc, ff, pce, agg="champion"):
    base = dict(device_id="DV1", measurement_id="MS1", aggregation=agg, result_origin="primary", extraction_status="extracted",
                _evidence={"page": 5, "table": "Table 1", "row_label": "best"}, source_page=5, source_fragment="x")
    out = []
    for i, (m, v, u) in enumerate([("Voc", voc, "V"), ("Jsc", jsc, "mA/cm2"), ("FF", ff, "%"), ("PCE", pce, "%")]):
        r = {**base, "result_id": f"R{i}", "metric_name": m, "raw_value": str(v), "raw_unit": u, "value": v, "unit": u}
        out.append(normalize.normalize_result("solar", r))
    return out


def test_pce_recalculation_consistent():
    res = _solar_set(1.10, 24.0, 80.0, 21.1)  # 1.10*24*0.80 = 21.12
    issues, per = rules.solar_rules(res, {"measurements": [{"measurement_id": "MS1", "light_intensity": "100"}]})
    assert not [i for i in issues if i["check_name"] == "jv_consistency"]
    chk = per["R3"][0]
    assert chk["outcome"] == "pass" and abs(chk["computed"] - 21.12) < 0.01


def test_pce_recalculation_violation_keeps_published_value():
    res = _solar_set(1.10, 24.0, 80.0, 23.5)
    issues, _ = rules.solar_rules(res, {"measurements": [{"measurement_id": "MS1", "light_intensity": "100"}]})
    iss = [i for i in issues if i["check_name"] == "jv_consistency"]
    assert iss and "21.12" in iss[0]["description"] and "23.5" in iss[0]["description"]
    assert next(r for r in res if r["metric_name"] == "PCE")["normalized_value"] == "23.5"


def test_voc_limit_and_champion_vs_mean():
    res = _solar_set(1.95, 20.0, 70.0, 27.3)
    res += [dict(res[3], result_id="R9", aggregation="mean", raw_value="28", value=28.0, normalized_value="28")]
    issues, _ = rules.solar_rules(res, {"materials": [{"material_id": "M1", "bandgap_value": "1.6"}],
                                        "measurements": [{"measurement_id": "MS1"}]})
    for r in res:
        r["material_id"] = "M1"
    issues, _ = rules.solar_rules(res, {"materials": [{"material_id": "M1", "bandgap_value": "1.6"}], "measurements": []})
    kinds = {i["check_name"] for i in issues}
    assert "voc_limit" in kinds and "champion_vs_mean" in kinds


def test_forward_reverse_are_separate_groups():
    a = _solar_set(1.10, 24.0, 80.0, 21.1)
    b = _solar_set(1.00, 24.0, 70.0, 16.8)
    for r in b:
        r["measurement_id"] = "MS2"
        r["result_id"] += "f"
    issues, per = rules.solar_rules(a + b, {"measurements": [{"measurement_id": "MS1", "scan_direction": "reverse"},
                                                             {"measurement_id": "MS2", "scan_direction": "forward"}]})
    assert not [i for i in issues if i["check_name"] == "jv_consistency"]
    assert per["R3"][0]["inputs"]["Voc_V"] == 1.10 and per["R3f"][0]["inputs"]["Voc_V"] == 1.00


# ------------------------------------------------------------------ rag rules
def test_rag_scale_and_k():
    res = [normalize.normalize_result("rag", {"result_id": "R1", "metric_name": "Recall@5", "metric_k": "", "raw_value": "1.3",
                                              "value": 1.3, "unit": "fraction", "extraction_status": "extracted"})]
    issues, _ = rules.rag_rules(res, {})
    kinds = {i["check_name"] for i in issues}
    assert {"metric_scale", "metric_k"} <= kinds


def test_rag_contradiction_not_duplicate():
    base = dict(experiment_id="E1", config_id="C1", dataset_id="DS1", task_id="T1", metric_name="EM", metric_variant="", metric_k="",
                aggregation="", result_origin="primary", cited_publication_id="", extraction_status="extracted", metric_unit="")
    res = [dict(base, result_id="R1", metric_value="45.1", raw_value="45.1", source_page=5, source_fragment="a"),
           dict(base, result_id="R2", metric_value="45.1", raw_value="45.1", source_page=1, source_fragment="b"),
           dict(base, result_id="R3", metric_value="47.0", raw_value="47.0", source_page=2, source_fragment="c")]
    issues, _ = rules.rag_rules(res, {"datasets": [{"dataset_id": "DS1", "dataset_name": "HotpotQA"}]})
    assert res[1].get("duplicate_of") == "R1" and not res[2].get("duplicate_of")
    assert any(i["check_name"] == "contradiction" and "R3" in i["record_ids"] for i in issues)


# ------------------------------------------------------------------ quorum
def test_quorum_agree_and_disagree():
    ents = {"configurations": [{"config_id": "C1", "rag_variant": "ThreadRAG"}]}
    mk = lambda v: normalize.normalize_result("rag", {"metric_name": "EM", "metric_k": "", "raw_value": v, "value": float(v), "unit": "",
                                                       "source_page": 6, "config_id": "C1"})
    a = {"results": [mk("0.422"), mk("0.513")], "entities": ents}
    b = {"results": [mk("0.422"), mk("0.531")], "entities": ents}
    out = compare_nodes("rag", a, b)
    assert out[0]["outcome"] == "agree" and out[1]["outcome"] == "disagree" and out[1]["other_value"] == "0.531"


# ------------------------------------------------------------------ gold isolation
def test_pipeline_never_reads_gold():
    core = ROOT / "backend" / "app" / "core"
    offenders = [p.name for p in core.glob("*.py") if p.name != "evaluate.py" and "dev_gold" in p.read_text()]
    assert offenders == []


def test_domain_schema_from_official_templates():
    for dom in ("rag", "solar"):
        cfg = D.load(dom)
        assert len(cfg["tables"]) == 7 and "results" in cfg["tables"]


# ------------------------------------------------------------------ LLM fallback chain (offline, no network)
def test_llm_fallback_chain(monkeypatch):
    import time as _t
    from backend.app.core import llm
    calls = []

    def fake_one(s, model, system, user, **kw):
        calls.append(f"{s['provider']}/{model}")
        if s["provider"] == "agentrouter":
            raise llm.LLMError('AgentRouter HTTP 403: {"code":"insufficient_user_quota"}')
        if model == "claude-haiku-5-5":
            raise llm.LLMError("Модель не ответила после 4 попыток (HTTP 503).")
        return {"text": "{}", "tokens_in": 1, "tokens_out": 1, "seconds": 0, "model": model, "params": {}, "cost_usd": 0}

    monkeypatch.setattr(llm, "_chat_one", fake_one)
    monkeypatch.setattr(llm, "_usable", lambda p: True)
    monkeypatch.setattr(llm, "config", lambda provider=None, key_index=0: {**llm.DEFAULTS, "provider": provider or "agentrouter", "model_a": "gpt-5.6-sol",
                                                              "fallback_chain": llm.DEFAULTS["fallback_chain"], "breaker_minutes": 30})
    llm._breaker.clear()
    r = llm.chat("gpt-5.6-sol", "s", "u")
    assert calls == ["agentrouter/gpt-5.6-sol", "klinch/claude-haiku-5-5", "klinch/gpt-6-luna"]
    assert r["params"]["served_by"] == "klinch/gpt-6-luna"
    # quota breaker: the exhausted provider is skipped on the next call, a transient 503 is not
    calls.clear()
    llm.chat("gpt-5.6-sol", "s", "u")
    assert calls == ["klinch/claude-haiku-5-5", "klinch/gpt-6-luna"]
    # images never go to the local CLI
    llm._breaker["klinch/gpt-6-luna"] = _t.time() + 60
    with pytest.raises(llm.LLMError):
        llm.chat("gpt-5.6-sol", "s", "u", images=[b"x"])
    llm._breaker.clear()


def test_llm_backup_key_rotation(monkeypatch):
    """Quota on the main key -> same provider/model with the backup key, before moving down the chain."""
    from backend.app.core import llm
    calls = []
    keys = {"klinch": ["kl_main_xxxxxxxx", "kl_backup_yyyyyy"]}

    def fake_config(provider=None, key_index=0):
        prov = provider or "klinch"
        pool = keys.get(prov, [])
        return {**llm.DEFAULTS, "provider": prov, "model_a": "claude-haiku-5-5", "base_url": "x", "api": "chat",
                "api_key": pool[key_index] if key_index < len(pool) else "", "key_count": len(pool),
                "fallback_chain": [{"provider": "klinch", "model": "gpt-6-luna"}, {"provider": "claude-cli", "model": "haiku"}],
                "breaker_minutes": 30}

    def fake_one(s, model, system, user, **kw):
        calls.append((s["provider"], model, s.get("api_key")))
        if s.get("api_key") == "kl_main_xxxxxxxx":
            raise llm.LLMError('API вернул ошибку HTTP 403: {"code":"insufficient_user_quota"}')
        return {"text": "{}", "tokens_in": 1, "tokens_out": 1, "seconds": 0, "model": model, "params": {}, "cost_usd": 0}

    monkeypatch.setattr(llm, "config", fake_config)
    monkeypatch.setattr(llm, "_usable", lambda p: True)
    monkeypatch.setattr(llm, "_chat_one", fake_one)
    llm._breaker.clear()
    r = llm.chat("claude-haiku-5-5", "s", "u")
    assert calls == [("klinch", "claude-haiku-5-5", "kl_main_xxxxxxxx"), ("klinch", "claude-haiku-5-5", "kl_backup_yyyyyy")]
    assert r["params"]["served_by"] == "klinch/claude-haiku-5-5 (ключ 2)"
    calls.clear()
    llm.chat("claude-haiku-5-5", "s", "u")  # main key is paused by the quota breaker: straight to the backup key
    assert calls == [("klinch", "claude-haiku-5-5", "kl_backup_yyyyyy")]
    llm._breaker.clear()


def test_range_and_metric_names():
    from backend.app.core.pipeline import RANGE_RE
    assert RANGE_RE.search("0.61 and 0.65") and RANGE_RE.search("0.61–0.65") and not RANGE_RE.search("-0.3")
    assert not RANGE_RE.search("1,850") and not RANGE_RE.search("4.39 ± 0.81")
    assert D.canonical_metric("rag", "PubMedQA accuracy")[0] == "Accuracy"
    assert D.canonical_metric("rag", "nDCG@10") == ("nDCG", 10)


def test_variants_in_one_sentence_are_linking_not_contradiction():
    base = dict(experiment_id="E9", config_id="C1", dataset_id="DS1", task_id="", metric_name="accuracy", metric_variant="",
                metric_k="", aggregation="", result_origin="primary", cited_publication_id="", extraction_status="extracted",
                metric_unit="", source_page=3)
    res = [dict(base, result_id="R1", metric_value="0.728", raw_value="0.728", source_fragment="with 3 kept passages accuracy is 0.728"),
           dict(base, result_id="R2", metric_value="0.735", raw_value="0.735", source_fragment="with 10 it is 0.735")]
    page = lambda pg: "Reranking depth matters: with 3 kept passages accuracy is 0.728, with 10 it is 0.735. Next sentence."
    issues, _ = rules.rag_rules(res, {"datasets": [{"dataset_id": "DS1", "dataset_name": "PubMedQA"}]}, page)
    kinds = [i["check_name"] for i in issues]
    assert "extraction_linking" in kinds and "contradiction" not in kinds
