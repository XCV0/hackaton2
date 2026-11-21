import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA_DIR = pathlib.Path(os.environ.get("VINITI_DATA", ROOT / "data"))
RUNS_DIR = pathlib.Path(os.environ.get("VINITI_RUNS", ROOT / "runs"))
CACHE_DIR = RUNS_DIR / "cache"
DB_PATH = pathlib.Path(os.environ.get("VINITI_DB", RUNS_DIR / "viniti.db"))
REPORTS_DIR = ROOT / "reports"
CONFIG_DIR = ROOT / "backend" / "app" / "domains"
for d in (RUNS_DIR, CACHE_DIR, REPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

DOMAINS = {
    "solar": {"dir": DATA_DIR / "domain1_solar", "title": "Тонкоплёночные солнечные элементы"},
    "rag": {"dir": DATA_DIR / "domain2_rag", "title": "Retrieval-Augmented Generation"},
}
SPLITS = ("dev", "test")


def pdf_path(domain: str, split: str, pid: str) -> pathlib.Path:
    return DOMAINS[domain]["dir"] / split / f"{pid}.pdf"


def list_pdfs(domain: str, split: str) -> list[pathlib.Path]:
    return sorted((DOMAINS[domain]["dir"] / split).glob("*.pdf"))
