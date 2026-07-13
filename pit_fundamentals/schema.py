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

`taxonomy` records which source normalized this row into the canonical tag
vocabulary (e.g. 'us-gaap' for SEC EDGAR XBRL, 'cvm-br' for Brazil's CVM
Dados Abertos standardized account codes). Every source adapter is
responsible for translating its native fields into the SAME canonical tags
(Assets, AssetsCurrent, NetIncomeLoss, ...) before insertion — get_fact_as_of
and build_pit_snapshot key only on (ticker, tag, filed_date) and never
branch on taxonomy, so adding a source never touches the US-GAAP query path.
`cik` holds the source's native entity ID (SEC CIK for us-gaap rows, CNPJ
for cvm-br rows) — it's an opaque identifier to the query layer either way.
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
    is_restatement    BOOLEAN,
    taxonomy          TEXT DEFAULT 'us-gaap'   -- 'us-gaap' (SEC EDGAR) or 'cvm-br' (Brazil CVM)
);
"""

# Tables created before the multi-taxonomy extension lack this column;
# ALTER TABLE ADD COLUMN IF NOT EXISTS is a no-op on fresh databases and a
# safe, additive migration on existing ones — the US-GAAP ingestion path
# never has to change.
ADD_TAXONOMY_COLUMN_SQL = """
ALTER TABLE pit_facts ADD COLUMN IF NOT EXISTS taxonomy TEXT DEFAULT 'us-gaap';
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
    con.execute(ADD_TAXONOMY_COLUMN_SQL)
    con.execute(CREATE_INDEX_SQL)
    con.execute(CREATE_LOG_SQL)
