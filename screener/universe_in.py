"""Indian universe: NSE ticker -> BSE scrip code, sector.

`screener/india_universe.csv` (tracked, so a clean clone reproduces it) was
built from primary sources only:

  1. BSE's public scrip master (`ListofScripData`) returned all 5,082
     active equities with market cap, ISIN, and the NSE trading symbol.
  2. Ranked by market cap, the top 140 were checked against Yahoo `.NS`
     daily history; 123 had >=1000 trading days.
  3. The top 100 of those form the universe.

Neither the tickers nor the BSE scrip codes were typed from memory — a
wrong scrip code would silently pull another company's filing dates.

Sector labels come from BSE's own industry classification where present;
BSE leaves `INDUSTRY` null for much of the master, so sectors fall back to
"IN-UNCLASSIFIED" and those names z-score against the whole universe via
the existing MIN_SECTOR_SIZE fallback. That is weaker than the GICS
grouping the US path uses and the KSIC grouping Korea uses, and is stated
rather than papered over.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

UNIVERSE_CSV = Path(__file__).resolve().parent / "india_universe.csv"


@functools.lru_cache(maxsize=1)
def load_universe() -> pd.DataFrame:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str, "bse_scrip": str})
    df["bse_scrip"] = df["bse_scrip"].str.strip()
    if "sector" not in df.columns:
        df["sector"] = "IN-UNCLASSIFIED"
    df["sector"] = df["sector"].fillna("IN-UNCLASSIFIED")
    return df


def get_in_universe() -> dict[str, str]:
    """{NSE ticker: BSE scrip code} for run_india_ingest()."""
    u = load_universe()
    return dict(zip(u["ticker"], u["bse_scrip"]))


def get_in_sectors() -> dict[str, str]:
    u = load_universe()
    return dict(zip(u["ticker"], u["sector"]))


def get_in_names() -> dict[str, str]:
    u = load_universe()
    return dict(zip(u["ticker"], u["name"]))
