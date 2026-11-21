"""SQLite persistence (WAL). PostgreSQL was unavailable in the environment (no server, Docker
daemon off); the schema is plain SQL and portable. All record changes go through
`save_record`/`audit` so every automatic and manual change is auditable."""
from __future__ import annotations

import json
import sqlite3
import threading

from ..settings import DB_PATH
from .quotes import now

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS corpus (
  domain TEXT, split TEXT, pub_id TEXT, sha256 TEXT, bytes INTEGER, pages INTEGER, text_pages INTEGER,
  is_scan INTEGER, doi TEXT, title TEXT, status TEXT, stage TEXT, error TEXT, processed_at TEXT,
  stats TEXT, PRIMARY KEY (domain, split, pub_id));
CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT, split TEXT, pub_id TEXT, tbl TEXT, rec_id TEXT,
  data TEXT, node TEXT, extraction_status TEXT, verification_status TEXT, review_status TEXT,
  checks TEXT, quorum TEXT, evidence TEXT, created TEXT, updated TEXT,
  UNIQUE (domain, split, pub_id, tbl, rec_id));
CREATE INDEX IF NOT EXISTS rec_pub ON records(domain, split, pub_id, tbl);
CREATE INDEX IF NOT EXISTS rec_ver ON records(verification_status);
CREATE TABLE IF NOT EXISTS node_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, domain TEXT, split TEXT, pub_id TEXT, node TEXT, purpose TEXT,
  model TEXT, params TEXT, prompt TEXT, input_ref TEXT, raw_response TEXT, parsed TEXT, error TEXT,
  started TEXT, seconds REAL, tokens_in INTEGER, tokens_out INTEGER, cost_usd REAL);
CREATE INDEX IF NOT EXISTS nr_pub ON node_runs(domain, split, pub_id);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT, domain TEXT, split TEXT,
  pub_id TEXT, tbl TEXT, rec_id TEXT, before TEXT, after TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, params TEXT, status TEXT, progress REAL, total INTEGER,
  done INTEGER, log TEXT, created TEXT, started TEXT, finished TEXT, error TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(domain UNINDEXED, split UNINDEXED, pub_id UNINDEXED,
  page UNINDEXED, engine UNINDEXED, text, tokenize='unicode61');
"""


def conn() -> sqlite3.Connection:
    c = getattr(_local, "c", None)
    if c is None:
        c = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
        c.executescript(SCHEMA)
        _local.c = c
    return c


def j(v) -> str:
    return json.dumps(v, ensure_ascii=False, default=str)


def lj(v, default=None):
    if v is None:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


def get_setting(key: str, default=None):
    r = conn().execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return lj(r["value"], default) if r else default


def set_setting(key: str, value) -> None:
    conn().execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, j(value)))
    conn().commit()


def audit(actor: str, action: str, domain: str, split: str, pub_id: str, tbl: str = "", rec_id: str = "",
          before=None, after=None, reason: str = "") -> None:
    conn().execute("INSERT INTO audit(ts,actor,action,domain,split,pub_id,tbl,rec_id,before,after,reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                   (now(), actor, action, domain, split, pub_id, tbl, rec_id, j(before) if before is not None else None,
                    j(after) if after is not None else None, reason))


def row_to_record(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("data", "checks", "quorum", "evidence"):
        d[k] = lj(d.get(k), {} if k != "checks" else [])
    return d
