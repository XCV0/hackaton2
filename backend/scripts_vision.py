"""Acceptance 15.4 (Vision): printed value on a figure, architecture diagram without metrics, curve not digitised."""
import json, sys, warnings, time
warnings.filterwarnings("ignore"); sys.path.insert(0, ".")
from concurrent.futures import ThreadPoolExecutor
from backend.app.core import extract_llm, llm
from backend.app.settings import pdf_path, REPORTS_DIR
cases = [("printed values on a figure", "rag", "dev", "D002", 10, "Fig. 6: Impact of Retrievers (scan)"),
         ("architecture diagram without metrics", "rag", "dev", "D001", 3, "Figure 2: Overview of ThreadRAG"),
         ("curve: digitisation forbidden", "rag", "dev", "D001", 8, "Figure 3: Hyperparameter sensitivity (line plots)")]
model = llm.config()["model_vision"] or llm.config()["model_a"]
def run(c):
    name, d, s, pid, pg, what = c
    t = time.time()
    res = extract_llm.vision_page(model, d, s, pid, pdf_path(d, s, pid), pg)
    return {"case": name, "pub": pid, "page": pg, "figure": what, "model": model, "seconds": round(time.time() - t), "answer": res}
with ThreadPoolExecutor(3) as ex:
    out = list(ex.map(run, cases))
(REPORTS_DIR / "vision_acceptance.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
for o in out:
    a = o["answer"] or {}
    print(o["case"], o["pub"], o["page"], o["seconds"], "s | values:", len(a.get("values", []) if isinstance(a, dict) else []),
          "| diagrams:", a.get("diagrams_without_metrics") if isinstance(a, dict) else None, "| curves:", a.get("curves_not_digitised") if isinstance(a, dict) else None)
