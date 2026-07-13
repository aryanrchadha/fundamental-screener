"""Universe construction: current S&P 500 constituents + historical changes.

Both tables come from Wikipedia's maintained "List of S&P 500 companies"
page. The current-constituents table also carries GICS sector, which we use
as the primary sector source (it IS the GICS classification, from a single
cached request) with yfinance as a per-ticker fallback — yfinance's `.info`
endpoint is slow and fragile, so it is only hit for tickers Wikipedia
doesn't cover, and results are cached to disk with a long TTL.

The historical changes table lets the backtest optionally restrict each
rebalance date's cross-section to actual constituents at that date
(survivorship-bias correction; see build_membership / was_member).
"""

from __future__ import annotations

import io
import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import requests_cache

import config

log = logging.getLogger(__name__)

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


def _fetch_wiki_tables() -> list[pd.DataFrame]:
    session = requests_cache.CachedSession(
        str(config.HTTP_CACHE_PATH), backend="sqlite",
        expire_after=config.CACHE_TTL_WIKIPEDIA,
    )
    session.headers.update({"User-Agent": config.SEC_USER_AGENT})
    resp = session.get(WIKI_SP500_URL, timeout=60)
    resp.raise_for_status()
    return pd.read_html(io.StringIO(resp.text))


def get_sp500_constituents() -> pd.DataFrame:
    """Current S&P 500 members: columns [ticker, name, sector]."""
    tables = _fetch_wiki_tables()
    df = tables[0]
    out = pd.DataFrame(
        {
            "ticker": df["Symbol"].astype(str).str.upper().str.replace(".", "-", regex=False),
            "name": df["Security"],
            "sector": df["GICS Sector"],
        }
    )
    if config.MAX_TICKERS:
        out = out.head(config.MAX_TICKERS)
    return out.reset_index(drop=True)


def get_sp500_changes() -> pd.DataFrame:
    """Historical constituent changes: columns [date, added, removed].

    Parsed from Wikipedia's "Selected changes" table. NOTE (documented
    limitation): Wikipedia labels this table 'selected' — early-year coverage
    is incomplete, which is why survivorship correction is an optional
    toggle rather than the default.
    """
    tables = _fetch_wiki_tables()
    changes = None
    for t in tables:
        cols = ["".join(map(str, c)) if isinstance(c, tuple) else str(c) for c in t.columns]
        if any("Added" in c for c in cols) and any("Removed" in c for c in cols):
            changes = t.copy()
            changes.columns = cols
            break
    if changes is None:
        raise RuntimeError("Could not locate S&P 500 changes table on Wikipedia")
    added_col = next(c for c in changes.columns if c.startswith("Added"))
    removed_col = next(c for c in changes.columns if c.startswith("Removed"))
    date_col = next(c for c in changes.columns if "Date" in c)
    out = pd.DataFrame(
        {
            "date": pd.to_datetime(changes[date_col], errors="coerce"),
            "added": changes[added_col].astype(str).str.upper().str.replace(".", "-", regex=False),
            "removed": changes[removed_col].astype(str).str.upper().str.replace(".", "-", regex=False),
        }
    ).dropna(subset=["date"])
    out = out.replace({"added": {"NAN": None}, "removed": {"NAN": None}})
    return out.sort_values("date").reset_index(drop=True)


def build_membership(current: pd.DataFrame | None = None, changes: pd.DataFrame | None = None) -> pd.DataFrame:
    """Reconstruct historical membership by unwinding changes backward from
    today's list. Returns [ticker, start (may be NaT = 'since before the
    table begins'), end (NaT = still a member)]."""
    current = current if current is not None else get_sp500_constituents()
    changes = changes if changes is not None else get_sp500_changes()
    members: dict[str, dict] = {t: {"start": pd.NaT, "end": pd.NaT} for t in current["ticker"]}
    episodes: list[dict] = []
    # Walk changes newest -> oldest, undoing each: an 'added' on date d means
    # the ticker was NOT a member before d; a 'removed' means it WAS.
    for _, row in changes.sort_values("date", ascending=False).iterrows():
        d = row["date"]
        if row["added"] and row["added"] in members and pd.isna(members[row["added"]]["start"]):
            members[row["added"]]["start"] = d
        if row["removed"] and row["removed"] not in members:
            episodes.append({"ticker": row["removed"], "start": pd.NaT, "end": d})
    for t, span in members.items():
        episodes.append({"ticker": t, "start": span["start"], "end": pd.NaT})
    return pd.DataFrame(episodes)


def was_member(ticker: str, on: date, membership: pd.DataFrame) -> bool:
    """True if `ticker` was a constituent on `on` per the membership table."""
    on_ts = pd.Timestamp(on)
    rows = membership[membership["ticker"] == ticker.upper()]
    for _, r in rows.iterrows():
        start_ok = pd.isna(r["start"]) or r["start"] <= on_ts
        end_ok = pd.isna(r["end"]) or r["end"] > on_ts
        if start_ok and end_ok:
            return True
    return False


def get_sectors(tickers: list[str]) -> pd.Series:
    """Sector per ticker: Wikipedia GICS primary, yfinance fallback, with a
    long-TTL JSON disk cache for the yfinance lookups."""
    wiki = get_sp500_constituents().set_index("ticker")["sector"]
    sectors = {t: wiki.get(t) for t in tickers}
    missing = [t for t, s in sectors.items() if s is None or pd.isna(s)]
    if missing:
        cache: dict[str, str] = {}
        cache_file = Path(config.SECTOR_CACHE_PATH)
        if cache_file.exists():
            cache = json.loads(cache_file.read_text())
        import yfinance as yf

        for t in missing:
            if t in cache:
                sectors[t] = cache[t]
                continue
            try:
                info = yf.Ticker(t).info
                sec = info.get("sector")
                if sec:
                    sectors[t] = sec
                    cache[t] = sec
            except Exception as exc:  # yfinance raises a zoo of exceptions
                log.warning("yfinance sector lookup failed for %s: %s", t, exc)
        cache_file.write_text(json.dumps(cache, indent=2))
    return pd.Series(sectors, name="sector")
