"""Price data via yfinance: month-end adjusted closes, cached to parquet.

Non-US exchanges need a Yahoo symbol suffix (KRX: "005930" -> "005930.KS").
That suffix is a VENDOR detail, so it is applied on the way out to Yahoo
and stripped on the way back: every DataFrame this module returns is keyed
by the canonical ticker used everywhere else in the project — the PIT
database, the score panel, the universe crosswalk. Nothing downstream ever
has to know which exchange a name came from.

Prices are returned in the listing currency, unconverted. Fundamentals are
in the same currency (KRW filings for KRX names), so every ratio the scores
compute is unit-free and needs no FX; see screener/universes.py.

Downloads are chunked (`_CHUNK_SIZE` symbols per `yf.download()` call, with
a pause between chunks). A single request for thousands of symbols was
tried first and silently degrades: confirmed live on a real 2,582-symbol
Russell 3000 pull, Yahoo's undocumented rate limit turned into
`YFRateLimitError` on most of the batch, and yfinance swallows that into
NaN columns rather than raising — so the failure never surfaces as an
exception, only as a downstream "no price history" universe that looks
like a data problem instead of a request-shape one. Chunking at a size
that stays under the limit (confirmed live at 600 symbols in one call)
fixes this without needing paid API access.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd

import config

log = logging.getLogger(__name__)

_CHUNK_SIZE = 250
_CHUNK_PAUSE_SECONDS = 2.0
_MAX_RETRIES = 3
_RETRY_BACKOFF_SECONDS = 20.0


def _download(symbols: list[str], px_start: str, end: str) -> pd.DataFrame:
    import yfinance as yf

    raw = yf.download(
        symbols, start=px_start, end=end, auto_adjust=True,
        progress=False, group_by="column", threads=True,
    )
    # A batch where Yahoo recognizes none of the symbols (e.g. every symbol
    # in a retry is genuinely unknown) comes back with no "Close" level at
    # all rather than an all-NaN one — treat that the same as "no data" for
    # these symbols instead of letting the KeyError propagate.
    if "Close" not in raw.columns.get_level_values(0):
        return pd.DataFrame(index=raw.index, columns=symbols, dtype=float)
    c = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(c, pd.Series):
        c = c.to_frame(symbols[0])
    return c


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
    symbols = [f"{t}{symbol_suffix}" for t in tickers]
    log.info("Downloading daily prices for %d tickers from Yahoo%s, in chunks of %d…",
             len(tickers), f" (suffix {symbol_suffix})" if symbol_suffix else "", _CHUNK_SIZE)
    # Extend the window so the first rebalance has a prior month-end price
    # and the last has a full forward window.
    px_start = (pd.Timestamp(start) - pd.DateOffset(months=2)).strftime("%Y-%m-%d")

    chunks = [symbols[i : i + _CHUNK_SIZE] for i in range(0, len(symbols), _CHUNK_SIZE)]
    closes = []
    for i, chunk in enumerate(chunks):
        c = _download(chunk, px_start, end)
        # A partial-batch failure (Yahoo's undocumented rate limit hitting
        # mid-chunk) comes back as NaN columns, not an exception — retry
        # just the missing symbols with an escalating backoff rather than
        # accepting an arbitrary, rate-limit-shaped subset of the universe
        # as if it were a representative sample. Confirmed live: retrying
        # failed symbols after a real pause recovers most of them, whereas
        # accepting the first pass silently biases which names end up
        # in-sample toward "whichever chunk Yahoo happened to serve".
        missing = [s for s in chunk if s not in c.columns or c[s].isna().all()]
        attempt = 0
        while missing and attempt < _MAX_RETRIES:
            attempt += 1
            wait = _RETRY_BACKOFF_SECONDS * attempt
            log.warning("Chunk %d/%d: %d/%d symbols missing after attempt %d, "
                        "retrying after %.0fs…", i + 1, len(chunks), len(missing),
                        len(chunk), attempt, wait)
            time.sleep(wait)
            retry_c = _download(missing, px_start, end)
            for s in list(missing):
                if s in retry_c.columns and retry_c[s].notna().any():
                    c[s] = retry_c[s]
                    missing.remove(s)
        closes.append(c)
        log.info("Chunk %d/%d: %d/%d symbols returned data%s",
                  i + 1, len(chunks), int(c.notna().any().sum()), len(chunk),
                  f" ({len(missing)} unrecovered after retries)" if missing else "")
        if i + 1 < len(chunks):
            time.sleep(_CHUNK_PAUSE_SECONDS)
    close = pd.concat(closes, axis=1)
    if symbol_suffix:
        close = close.rename(columns=lambda c: c[: -len(symbol_suffix)]
                             if c.endswith(symbol_suffix) else c)
    # A ticker Yahoo knows nothing about is simply absent from the download;
    # reindex so the frame always has one column per requested ticker
    # (all-NaN for the unknown ones) rather than silently short columns.
    close = close.reindex(columns=list(tickers))
    # Yahoo pads a ticker's pre-listing history with literal 0.0 rather than
    # NaN (confirmed on real data: DEC/Diversified Energy, IPO'd Nov 2023,
    # returns 0.0 for every month back to the download window's start
    # instead of an absent row) — a real market close is never exactly
    # $0.00 even for a penny stock, so treat it as missing rather than a
    # genuine price. Left as 0 this becomes an infinite forward return
    # (p1 / p0 with p0 == 0) once the ticker actually starts trading.
    close = close.replace(0.0, np.nan)
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
