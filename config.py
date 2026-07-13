"""Central configuration for the composite fundamental screener.

Every tunable that a researcher might reasonably want to change lives here:
universe choice, date ranges, SEC etiquette settings, cache TTLs, and file
locations. Modules import from this file rather than hardcoding constants so
that a single edit (e.g. swapping the universe) propagates everywhere.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

DB_PATH = DATA_DIR / "pit.duckdb"                 # point-in-time fact database
HTTP_CACHE_PATH = DATA_DIR / "http_cache"         # requests-cache SQLite (no ext)
SECTOR_CACHE_PATH = DATA_DIR / "sector_cache.json"
PRICES_CACHE_PATH = DATA_DIR / "prices_monthly.parquet"
SCORES_PANEL_PATH = DATA_DIR / "scores_panel.parquet"
DECILE_RETURNS_PATH = DATA_DIR / "decile_returns.parquet"
COEFS_PATH = DATA_DIR / "lasso_coefs.parquet"
VALIDATION_SUMMARY_PATH = DATA_DIR / "validation_summary.csv"
ROLLING_SPREAD_PATH = DATA_DIR / "rolling_spread.parquet"

# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------
# Default universe is the S&P 500 built from Wikipedia's maintained
# constituent table. To swap to the Russell 3000 (or anything else), replace
# `screener.universe.get_sp500_constituents` with a function returning the
# same (ticker, sector) schema and change this constant.
UNIVERSE = "sp500"

# Cap on tickers processed end-to-end. None = full universe. The Colab
# quickstart sets this to SMALL_UNIVERSE_SIZE to keep runtimes reasonable.
MAX_TICKERS: int | None = None
SMALL_UNIVERSE_SIZE = 50

# If True, restrict each rebalance date's cross-section to names that were
# actually S&P 500 constituents on that date (survivorship-bias correction,
# built from Wikipedia's historical changes table). Off by default because
# the changes table is incomplete in the early years — see README.
USE_PIT_UNIVERSE = False

# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
# EDGAR companyfacts coverage is thin before ~2010 (XBRL mandate phased in
# 2009-2011), so the backtest starts in 2012 to avoid a sparse early sample.
BACKTEST_START = "2012-01-01"
BACKTEST_END = "2025-12-31"
REBALANCE_FREQ = "ME"          # month-end rebalancing
FORWARD_RETURN_MONTHS = 6      # LASSO training label horizon
ROLLING_WINDOW_MONTHS = 24     # rolling OOS decile-spread chart window

# ---------------------------------------------------------------------------
# SEC EDGAR etiquette (fair-use policy)
# ---------------------------------------------------------------------------
# SEC requires a descriptive User-Agent identifying the requester.
# REPLACE THE PLACEHOLDER EMAIL with your real contact address.
SEC_USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "fundamental-screener research REPLACE_ME_contact@example.com",
)
SEC_MAX_REQUESTS_PER_SEC = 8
SEC_BACKOFF_BASE_SECONDS = 2.0
SEC_MAX_RETRIES = 5

# ---------------------------------------------------------------------------
# HTTP cache TTLs (seconds)
# ---------------------------------------------------------------------------
CACHE_TTL_EDGAR = 30 * 86400      # companyfacts: filings change slowly
CACHE_TTL_WIKIPEDIA = 7 * 86400
CACHE_TTL_YAHOO = 1 * 86400
CACHE_TTL_SECTOR = 180 * 86400    # sector classification rarely changes

# ---------------------------------------------------------------------------
# Modeling
# ---------------------------------------------------------------------------
MIN_SECTOR_SIZE = 5           # below this, z-score vs whole universe instead
LASSO_ALPHAS = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1]
LASSO_CV_SPLITS = 5
MIN_TRAIN_MONTHS = 18         # months of labeled history before first LASSO fit
N_DSR_TRIALS = 4              # F, Z, O, composite — see validation.py
N_DECILES = 10

# Optional FMP fallback: only used if the env var is set; pipeline runs
# correctly without it (missing company-quarters are skipped and logged).
FMP_API_KEY = os.environ.get("FMP_API_KEY")
