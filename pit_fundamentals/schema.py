"""Database schema for the point-in-time fact store.

Why DuckDB rather than sqlite3: the downstream workload is analytical —
window functions over millions of rows to pick "latest filing per fiscal
period as of a date", cross-sectional pivots, etc. DuckDB executes those
queries orders of magnitude faster than SQLite, speaks Parquet/pandas
natively, and is still a single zero-config local file.

The one fact table stores EVERY filed value. If a company restates a number,
the restated value is a new row with its own `filed_date`; the original row
stays. `is_restatement` is True when a prior filing already covered the same
(cik, tag, fiscal_period_end).
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

DEFAULT_DB_PATH = os.environ.get("PIT_DB_PATH", str(Path("data") / "pit.duckdb"))

CREATE_FACTS_SQL = """
CREATE TABLE IF NOT EXISTS pit_facts (
    cik               TEXT,
    ticker            TEXT,
    tag               TEXT,
    fiscal_period_end DATE,
    start_date        DATE,      -- NULL for instant (balance-sheet) facts
    filed_date        DATE,      -- the PIT availability gate
    value             DOUBLE,
    unit              TEXT,
    form              TEXT,
    fy                INTEGER,
    fp                TEXT,
    is_restatement    BOOLEAN
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_pit_facts_lookup
ON pit_facts (ticker, tag, filed_date);
"""

CREATE_LOG_SQL = """
CREATE TABLE IF NOT EXISTS ingest_log (
    cik         TEXT PRIMARY KEY,
    ticker      TEXT,
    n_facts     INTEGER,
    ingested_at TIMESTAMP
);
"""


def connect(db_path: str | Path = DEFAULT_DB_PATH, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection, creating parent directories as needed."""
    path = Path(db_path)
    if not read_only:
        path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def init_db(con: duckdb.DuckDBPyConnection) -> None:
    """Create tables and indexes if they do not exist (idempotent)."""
    con.execute(CREATE_FACTS_SQL)
    con.execute(CREATE_INDEX_SQL)
    con.execute(CREATE_LOG_SQL)
