"""pit_fundamentals — a reusable point-in-time (PIT) fundamentals database.

This package ingests SEC EDGAR XBRL companyfacts into a DuckDB fact table
gated by *filing date*, so any query as of a historical date can only see
values that were actually public on that date. Restatements are stored as
additional rows (never overwritten) and become visible only after their own
filing date.

It is deliberately independent of the screener that ships alongside it:
import `get_fact_as_of` / `build_pit_snapshot` from any project.
"""

from pit_fundamentals.query import build_pit_snapshot, get_fact_as_of
from pit_fundamentals.schema import connect, init_db

__all__ = ["get_fact_as_of", "build_pit_snapshot", "connect", "init_db"]
__version__ = "0.1.0"
