"""Price data via yfinance: month-end adjusted closes, cached to parquet.

One batched download for the whole universe (yfinance handles chunking);
the parquet cache means re-runs during development don't re-hit Yahoo.
Split/dividend-adjusted closes (auto_adjust=True) so monthly percentage
changes are total-return-ish (dividends reinvested at ex-date).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

import config

log = logging.getLogger(__name__)


def get_monthly_prices(
    tickers: list[str],
    start: str = config.BACKTEST_START,
    end: str = config.BACKTEST_END,
    cache_path: str | Path = config.PRICES_CACHE_PATH,
) -> pd.DataFrame:
    """Month-end adjusted close per ticker (index: month-end dates)."""
    cache_path = Path(cache_path)
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        # Parquet round-trips DatetimeIndex as datetime64[ms]; pandas .asof /
        # .loc lookups against ns-resolution Timestamps then miss silently.
        cached.index = pd.DatetimeIndex(cached.index).as_unit("ns")
        if set(tickers) <= set(cached.columns):
            return cached[list(tickers)]
    import yfinance as yf

    log.info("Downloading daily prices for %d tickers from Yahoo…", len(tickers))
    # Extend the window so the first rebalance has a prior month-end price
    # and the last has a full forward window.
    px_start = (pd.Timestamp(start) - pd.DateOffset(months=2)).strftime("%Y-%m-%d")
    raw = yf.download(
        tickers, start=px_start, end=end, auto_adjust=True,
        progress=False, group_by="column", threads=True,
    )
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(tickers[0])
    monthly = close.resample("ME").last()
    monthly.to_parquet(cache_path)
    n_empty = int(monthly.isna().all().sum())
    if n_empty:
        log.warning("%d tickers returned no price history (delisted/renamed)", n_empty)
    return monthly


def monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple month-over-month returns from month-end closes."""
    return prices.pct_change(fill_method=None)
