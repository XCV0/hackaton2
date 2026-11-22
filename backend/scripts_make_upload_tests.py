"""Second set of synthetic test PDFs, meant to be uploaded by users through the UI (not pre-registered).
Answer key: test_pdfs_for_upload/ANSWER_KEY.md"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from backend.scripts_make_demo import W, H, M, page, para, heading, table, bar_chart, curve_chart, to_scan  # noqa: E402
import pymupdf  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parents[1] / "test_pdfs_for_upload"


def make_rag2(path):
    doc = pymupdf.open()
    p = page(doc, 1)
    y = 60
    y = para(p, y, "MedRerank-RAG: Cross-Encoder Reranking for Biomedical Question Answering", 15, bold=True)
    y = para(p, y, "Ivan Testov; Olga Proverkina", 10)
    y = para(p, y, "Proceedings of Synthetic Test Documents, 2025. DOI: 10.5555/demo.rag.2025.007", 9)
    y = heading(p, y + 6, "Abstract")
    y = para(p, y, "MedRerank-RAG retrieves passages from a PubMed abstract collection with a dense retriever (BGE-base), "
                   "reranks them with a cross-encoder (MiniLM-L6) and generates answers with Mistral-7B-Instruct. On PubMedQA it "
                   "reaches an accuracy of 0.742, compared with 0.701 for the same pipeline without reranking.")
    y = heading(p, y + 4, "1 Background")
    y = para(p, y, "The original RAG model reported 44.5 EM on Natural Questions (Lewis et al., 2020). Prior biomedical systems "
                   "report accuracies between 0.61 and 0.65 on PubMedQA [3].")
    p = page(doc, 2)
    y = 60
    y = heading(p, y, "2 Setup")
    y = para(p, y, "Each question retrieves top_k = 20 candidate passages, of which the 5 highest-scoring after reranking are "
                   "kept as context. Passages are 200-word chunks without overlap. We evaluate on 250 questions sampled from "
                   "the 1,000-question PubMedQA labeled set (test portion) and on the BioASQ 11b factoid test set (500 questions). "
                   "Retrieval quality is measured with nDCG@10.")
    y = table(p, y + 6, "Table 1: Results on PubMedQA (accuracy, fraction) and BioASQ (strict accuracy, %).",
              [["System", "PubMedQA Acc", "BioASQ Acc", "nDCG@10", "BLEU"]],
              [["Mistral-7B (no retrieval)", "0.584", "31.2", "-", "12.4"],
               ["Dense-RAG (no rerank)", "0.701", "40.6", "0.552", "18.9"],
               ["MedRerank-RAG", "0.742", "44.9", "0.618", "21.3"],
               ["MedRerank-RAG + GPT-4o generator", "1.07", "47.3", "0.618", "24.0"]],
              [170, 75, 70, 60, 50])
    y = para(p, y, "MedRerank-RAG uses on average 1,850 tokens per query (prompt and context); Dense-RAG uses 1,400.")
    p = page(doc, 3)
    y = 60
    y = heading(p, y, "3 Analysis")
    y = bar_chart(p, y, "Figure 1: PubMedQA accuracy (values printed above bars).",
                  [("No-ret.", 0.584), ("Dense", 0.701), ("Rerank", 0.742)], "Accuracy")
    y = para(p, y, "Reranking depth matters: with 3 kept passages accuracy is 0.728, with 10 it is 0.735. "
                   "In our conclusion we confirm that MedRerank-RAG achieves 0.742 accuracy on PubMedQA.")
    y = curve_chart(p, y, "Figure 2: Accuracy versus number of kept passages (no values printed).",
                    [0.55, 0.68, 0.74, 0.73, 0.70], "kept passages", "Acc")
    y = para(p, y, "In the error analysis section we state that MedRerank-RAG reaches 0.724 accuracy on PubMedQA.")
    to_scan(doc, 2)  # page 3 is image-only: OCR is required
    doc.set_metadata({"title": "MedRerank-RAG (synthetic test document)", "author": "Ivan Testov; Olga Proverkina"})
    doc.save(path)


def make_solar2(path):
    doc = pymupdf.open()
    p = page(doc, 1)
    y = 60
    y = para(p, y, "Ga-Grading and KF Post-Deposition Treatment in Cu(In,Ga)Se2 Thin-Film Solar Cells", 15, bold=True)
    y = para(p, y, "Pavel Testov; Nina Demo; Ruslan Proverkin", 10)
    y = para(p, y, "Journal of Synthetic Test Documents, 2025. DOI: 10.5555/demo.solar.2025.011", 9)
    y = heading(p, y + 6, "Abstract")
    y = para(p, y, "We report single-junction Cu(In,Ga)Se2 (CIGS) solar cells in substrate configuration. The best cell reaches "
                   "19.0% efficiency (aperture area) and an independently certified efficiency of 18.8%. The CIGS world record "
                   "is 23.6% [8].")
    y = heading(p, y + 4, "2 Experimental")
    y = para(p, y, "Stack: soda-lime glass / Mo (500 nm) / CIGS (2.0 um) / CdS (50 nm) / i-ZnO (80 nm) / ZnO:Al (300 nm) / "
                   "Ni-Al grid. The CIGS absorber with [Ga]/([Ga]+[In]) = 0.30 has a band gap of 1.15 eV determined from EQE. "
                   "Cells have an aperture area of 0.50 cm2 and a total area of 0.55 cm2. J-V curves were recorded under AM1.5G, "
                   "1000 W/m2, at 25 C.")
    p = page(doc, 2)
    y = 60
    y = heading(p, y, "3 Results")
    y = table(p, y, "Table 1: J-V parameters of the best cells (FF given as a fraction).",
              [["Cell", "Area", "Voc (mV)", "Jsc (mA/cm2)", "FF", "PCE (%)"]],
              [["Reference (no KF)", "aperture", "690", "34.2", "0.741", "17.5"],
               ["KF-PDT best", "aperture", "712", "35.1", "0.762", "19.0"],
               ["KF-PDT best", "total", "712", "31.9", "0.762", "17.3"],
               ["Ga-graded, KF-PDT", "aperture", "690", "34.0", "0.740", "20.9"]],
              [120, 60, 60, 80, 50, 55])
    y = para(p, y, "The KF-PDT best cell has a series resistance of 0.35 Ohm cm2 and a shunt resistance of 1200 Ohm cm2. "
                   "The Jsc integrated from its EQE is 34.8 mA/cm2. The certified measurement (Fraunhofer ISE CalLab) gave "
                   "Voc = 709 mV, Jsc = 34.9 mA/cm2, FF = 76.0% and PCE = 18.8%.")
    p = page(doc, 3)
    y = 60
    y = heading(p, y, "4 Stability")
    y = para(p, y, "Encapsulated KF-PDT cells retained 95% of their initial efficiency after 1000 h of damp-heat testing at "
                   "85 C / 85% relative humidity in the dark (ISOS-D-3).")
    y = curve_chart(p, y + 4, "Figure 1: Normalised PCE during damp heat (no values printed).", [0.99, 0.98, 0.97, 0.96, 0.95],
                    "time", "PCE/PCE0")
    para(p, y, "Conclusion: KF post-deposition treatment raises the efficiency of CIGS cells to 19.0% (aperture).")
    doc.set_metadata({"title": "KF-PDT CIGS (synthetic test document)", "author": "Pavel Testov; Nina Demo; Ruslan Proverkin"})
    doc.save(path)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    make_rag2(OUT / "TEST_RAG_MedRerank.pdf")
    make_solar2(OUT / "TEST_SOLAR_CIGS.pdf")
    print(sorted(p.name for p in OUT.glob("*.pdf")))
