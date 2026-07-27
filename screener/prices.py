"""Price data via yfinance: month-end adjusted closes, cached to parquet.

One batched download for the whole universe (yfinance handles chunking);
the parquet cache means re-runs during development don't re-hit Yahoo.
Split/dividend-adjusted closes (auto_adjust=True) so monthly percentage
changes are total-return-ish (dividends reinvested at ex-date).

Non-US exchanges need a Yahoo symbol suffix (KRX: "005930" -> "005930.KS").
That suffix is a VENDOR detail, so it is applied on the way out to Yahoo
and stripped on the way back: every DataFrame this module returns is keyed
by the canonical ticker used everywhere else in the project — the PIT
database, the score panel, the universe crosswalk. Nothing downstream ever
has to know which exchange a name came from.

Prices are returned in the listing currency, unconverted. Fundamentals are
in the same currency (KRW filings for KRX names), so every ratio the scores
compute is unit-free and needs no FX; see screener/universes.py.
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
    symbol_suffix: str = "",
) -> pd.DataFrame:
    """Month-end adjusted close per ticker (index: month-end dates).

    `symbol_suffix` is the Yahoo exchange suffix (e.g. ".KS" for KRX). It is
    appended for the download and stripped from the returned columns, so
    callers always work in canonical tickers.
    """
    cache_path = Path(cache_path)
    if cache_path.exists():
        cached = pd.read_parquet(cache_path)
        # Parquet round-trips DatetimeIndex as datetime64[ms]; pandas .asof /
        # .loc lookups against ns-resolution Timestamps then miss silently.
        cached.index = pd.DatetimeIndex(cached.index).as_unit("ns")
        if set(tickers) <= set(cached.columns):
            return cached[list(tickers)]
    import yfinance as yf

    symbols = [f"{t}{symbol_suffix}" for t in tickers]
    log.info("Downloading daily prices for %d tickers from Yahoo%s…",
             len(tickers), f" (suffix {symbol_suffix})" if symbol_suffix else "")
    # Extend the window so the first rebalance has a prior month-end price
    # and the last has a full forward window.
    px_start = (pd.Timestamp(start) - pd.DateOffset(months=2)).strftime("%Y-%m-%d")
    raw = yf.download(
        symbols, start=px_start, end=end, auto_adjust=True,
        progress=False, group_by="column", threads=True,
    )
    close = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(close, pd.Series):
        close = close.to_frame(symbols[0])
    if symbol_suffix:
        close = close.rename(columns=lambda c: c[: -len(symbol_suffix)]
                             if c.endswith(symbol_suffix) else c)
    # A ticker Yahoo knows nothing about is simply absent from the download;
    # reindex so the frame always has one column per requested ticker
    # (all-NaN for the unknown ones) rather than silently short columns.
    close = close.reindex(columns=list(tickers))
    monthly = close.resample("ME").last()
    monthly.to_parquet(cache_path)
    n_empty = int(monthly.isna().all().sum())
    if n_empty:
        log.warning("%d/%d tickers returned no price history (delisted/renamed/unknown)",
                    n_empty, len(tickers))
    return monthly


def monthly_returns(prices: pd.DataFrame) -> pd.DataFrame:
    """Simple month-over-month returns from month-end closes."""
    return prices.pct_change(fill_method=None)
