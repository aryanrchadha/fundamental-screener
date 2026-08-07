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
# KOSPI (South Korea) universe — see screener/universes.py
# ---------------------------------------------------------------------------
KR_DB_PATH = DATA_DIR / "pit_kr.duckdb"
KR_PRICES_CACHE_PATH = DATA_DIR / "kr_prices_monthly.parquet"
KR_SCORES_PANEL_PATH = DATA_DIR / "kr_scores_panel.parquet"
KR_BUCKET_RETURNS_PATH = DATA_DIR / "kr_bucket_returns.parquet"
KR_COEFS_PATH = DATA_DIR / "kr_lasso_coefs.parquet"
KR_VALIDATION_SUMMARY_PATH = DATA_DIR / "kr_validation_summary.csv"
KR_ROLLING_SPREAD_PATH = DATA_DIR / "kr_rolling_spread.parquet"

# DART's structured financial data begins with FY2015, so the first usable
# annual snapshot is only public in 2016 (filings land ~Mar of the
# following year). Starting the backtest mid-2016 guarantees every
# rebalance sees a filed annual report rather than an empty snapshot.
KR_BACKTEST_START = "2016-07-31"
KR_BACKTEST_END = "2025-12-31"

# 120 liquid names, of which ~2/3 are fully scoreable after honest tag
# exclusions -> quintiles hold ~15 names each. Deciles would hold ~7, at
# which point a "decile return" is mostly a handful of stocks' idiosyncratic
# noise rather than a cross-sectional signal.
KR_N_BUCKETS = 5

# ---------------------------------------------------------------------------
# India (BSE/NSE) — screener only, see screener/universes.py
# ---------------------------------------------------------------------------
IN_DB_PATH = DATA_DIR / "pit_in.duckdb"
IN_PRICES_CACHE_PATH = DATA_DIR / "in_prices_monthly.parquet"
IN_SCORES_PANEL_PATH = DATA_DIR / "in_scores_panel.parquet"
IN_BUCKET_RETURNS_PATH = DATA_DIR / "in_bucket_returns.parquet"      # written; descriptive only
IN_COEFS_PATH = DATA_DIR / "in_lasso_coefs.parquet"                  # never written — no LASSO fit
IN_VALIDATION_SUMMARY_PATH = DATA_DIR / "in_validation_summary.csv"  # never written — no NW/DSR table
IN_ROLLING_SPREAD_PATH = DATA_DIR / "in_rolling_spread.parquet"      # written when >=1 window fits

# Yahoo serves ~5 annual periods per Indian filer, and only three of those
# have broad coverage once a prior year is required for the YoY deltas
# (FY2024/25/26, ~90 companies each). The screen therefore starts once
# FY2024 results were filed. Buckets exist so the table can show a decile
# column. `backtestable=False` on the Universe is what actually stops the
# LASSO fit and validation table — see screener/universes.py.
IN_SCREEN_START = "2024-05-31"
IN_SCREEN_END = "2026-12-31"
IN_N_BUCKETS = 5

# ---------------------------------------------------------------------------
# Russell 3000 (US, broader universe) — see screener/universes.py
# ---------------------------------------------------------------------------
# Same taxonomy and data source as the S&P 500 (SEC EDGAR, us-gaap) — only
# the ticker list differs — so this shares BACKTEST_START/END and the
# rebalance frequency, but gets its own database and output paths so a
# Russell 3000 run never collides with an S&P 500 one.
R3K_DB_PATH = DATA_DIR / "pit_r3k.duckdb"
R3K_PRICES_CACHE_PATH = DATA_DIR / "r3k_prices_monthly.parquet"
R3K_SCORES_PANEL_PATH = DATA_DIR / "r3k_scores_panel.parquet"
R3K_BUCKET_RETURNS_PATH = DATA_DIR / "r3k_bucket_returns.parquet"
R3K_COEFS_PATH = DATA_DIR / "r3k_lasso_coefs.parquet"
R3K_VALIDATION_SUMMARY_PATH = DATA_DIR / "r3k_validation_summary.csv"
R3K_ROLLING_SPREAD_PATH = DATA_DIR / "r3k_rolling_spread.parquet"

# The full Russell 3000 is ~2,580 names in the free IWV-holdings proxy this
# project uses (screener.universe.get_russell3000_constituents). An initial
# committed run capped this to the top 300 by index weight, but checking the
# ticker sets directly showed 286 of those 300 were already S&P 500
# constituents — that run was a pipeline consistency check, not a test of
# whether the null result is specific to large-cap names. Of the full
# ~2,582-name universe, 2,086 names are NOT S&P 500 constituents, so this is
# set to None (full universe, no cap) to actually test that question against
# the genuinely non-overlapping mid/small-cap tail. Live-verified: 2,547 of
# 2,582 requested symbols return real Yahoo price history (the remainder
# are genuinely delisted/unknown, confirmed by 3 retries each still failing
# — see screener/prices.py's chunked-download retry logic, added after this
# scale first triggered Yahoo's undocumented rate limit on a single-batch
# request). The result at this scale is NOT a clean "no effect" like every
# other market/universe in this project — see FINDINGS.md's Russell 3000
# section for why it should be read as a survivorship-bias/outlier-
# concentration artifact rather than a genuine edge before citing it.
RUSSELL3000_MAX_TICKERS: int | None = None

# ---------------------------------------------------------------------------
# Modeling
# ---------------------------------------------------------------------------
# A cross-section is only ranked if it can fill every bucket this deeply.
# Without it, a thin early cross-section still forms buckets — the KOSPI
# panel averages ~29 scoreable names in 2017, which across quintiles is ~6
# per bucket, so a "bucket return" there is a handful of stocks'
# idiosyncratic noise rather than a cross-sectional signal. Stated as a
# uniform rule (not a hand-picked start date) so it applies identically to
# every universe and cannot be tuned to flatter a result.
MIN_NAMES_PER_BUCKET = 5

MIN_SECTOR_SIZE = 5           # below this, z-score vs whole universe instead
LASSO_ALPHAS = [1e-4, 3e-4, 1e-3, 3e-3, 1e-2, 3e-2, 1e-1]
LASSO_CV_SPLITS = 5
MIN_TRAIN_MONTHS = 18         # months of labeled history before first LASSO fit
N_DSR_TRIALS = 4              # F, Z, O, composite — see validation.py
N_DECILES = 10

# Optional FMP fallback: only used if the env var is set; pipeline runs
# correctly without it (missing company-quarters are skipped and logged).
FMP_API_KEY = os.environ.get("FMP_API_KEY")
