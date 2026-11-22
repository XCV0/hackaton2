"""CLI: python -m backend.cli process --domain rag --split dev [--pub D001] [--mode extended]
          python -m backend.cli export --domain rag --split dev --out runs/export/rag_dev
          python -m backend.cli evaluate --domain rag --split dev"""
import argparse, json, sys, warnings, logging
warnings.filterwarnings("ignore")
logging.disable(logging.WARNING)
from .app.core import pipeline, db
from .app.settings import list_pdfs

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["process", "export", "evaluate", "register", "conform"])
    ap.add_argument("--domain", default="rag"); ap.add_argument("--split", default="dev")
    ap.add_argument("--pub", nargs="*"); ap.add_argument("--mode", default="default"); ap.add_argument("--out"); ap.add_argument("--replay", action="store_true", help="reuse logged node replies with the models that produced them")
    ap.add_argument("--rules-only", action="store_true", help="deterministic node R only, no LLM calls")
    a = ap.parse_args()
    if a.cmd == "register":
        print(pipeline.register_corpus(), "registered")
    elif a.cmd == "process":
        pipeline.register_corpus()
        if a.replay:
            from .app.core import extract_llm
            extract_llm.REPLAY_ONLY = True
        for p in list_pdfs(a.domain, a.split):
            if a.pub and p.stem not in a.pub: continue
            try:
                models = pipeline.replay_models(a.domain, a.split, p.stem) if a.replay else None
                if a.replay and not (models or {}).get("model_a"):
                    models = {"_rules_only": True}  # replay never calls a live model: no logged LLM replies -> node R as before
                if a.rules_only:
                    models = {"_rules_only": True}
                mode = "extended" if (a.replay and models and models.get("model_b")) else a.mode
                pipeline.process(a.domain, a.split, p.stem, mode, models=models)
            except Exception as exc:
                import traceback; traceback.print_exc(); print("FAILED", p.stem, exc)
    elif a.cmd == "export":
        from .app.core import export
        print(json.dumps(export.export_csv(a.domain, a.split, a.out), ensure_ascii=False, indent=1))
    elif a.cmd == "conform":
        # export the service's records with the template contract, then check the folder independently of the kit scripts
        from .app.core import conformance, export
        from .app.settings import split_dir
        out = a.out or f"runs/export/{a.domain}_{a.split}"
        export.export_csv(a.domain, a.split, out)
        rep = conformance.check_folder(a.domain, out, split_dir(a.domain, a.split))
        import pathlib
        pathlib.Path(out, "conformance_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1))
        print(json.dumps({k: rep[k] for k in ("verdict", "structure_valid", "header_only", "content", "counts")}, ensure_ascii=False, indent=1))
    elif a.cmd == "evaluate":
        from .app.core import evaluate
        res = evaluate.evaluate(a.domain, a.split)
        from .app.settings import REPORTS_DIR
        (REPORTS_DIR / f"metrics_{a.domain}_{a.split}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        print(json.dumps({k: v for k, v in res.items() if k not in ("per_publication", "technical")}, ensure_ascii=False, indent=1))

if __name__ == "__main__":
    main()
