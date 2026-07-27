"""Universe definitions: what the backtest runs on, and where its data lives.

Before this module the pipeline was hardcoded to the S&P 500 in three
separate places (ticker source, price download, decile count). A second
market made those assumptions explicit rather than implicit, so each one
is now a field on a `Universe`:

  * `price_symbol` — the exchange suffix Yahoo needs. US tickers are bare
    ("AAPL"); KRX tickers need ".KS" ("005930" -> "005930.KS"). Prices come
    back keyed by the CANONICAL ticker, so nothing downstream of
    prices.get_monthly_prices ever sees the vendor-specific symbol.
  * `n_buckets` — 10 for the S&P 500, fewer for a thinner cross-section.
    Sorting ~90 names into deciles leaves ~9 per bucket, at which point a
    "decile return" is mostly the idiosyncratic noise of a handful of
    stocks. The bucket count is a property of the universe's width, not a
    global constant.
  * `currency` — fundamentals and prices must share it. Both sides of
    every ratio the scores compute (market cap / total liabilities,
    sales / assets) are same-currency, so the scores are unit-free and
    need no FX conversion. Returns are then LOCAL-currency returns, which
    is the correct basis for a within-market long-short spread: an FX
    translation would multiply both legs by the same factor and cancel.
    A cross-market comparison of these levels would NOT be valid without
    conversion — see FINDINGS.md.

Adding a third market means adding a Universe, not editing the backtest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

import config


@dataclass(frozen=True)
class Universe:
    name: str
    currency: str
    price_symbol_suffix: str
    db_path: Path
    n_buckets: int
    prices_cache: Path
    panel_path: Path
    bucket_returns_path: Path
    coefs_path: Path
    validation_path: Path
    rolling_path: Path
    start: str
    end: str
    # Populated lazily so importing this module never triggers a network call.
    _tickers: tuple[str, ...] | None = field(default=None)

    def tickers(self) -> list[str]:
        raise NotImplementedError

    def sectors(self) -> pd.Series:
        raise NotImplementedError

    def membership(self) -> pd.DataFrame | None:
        """Point-in-time constituent history, or None to use a static list."""
        return None

    @property
    def top_bucket(self) -> str:
        return f"D{self.n_buckets}"

    @property
    def bottom_bucket(self) -> str:
        return "D1"


@dataclass(frozen=True)
class SP500Universe(Universe):
    def tickers(self) -> list[str]:
        from screener.universe import get_sp500_constituents

        return get_sp500_constituents()["ticker"].tolist()

    def sectors(self) -> pd.Series:
        from screener.universe import get_sectors

        return get_sectors(self.tickers())

    def membership(self) -> pd.DataFrame | None:
        from screener.universe import build_membership, get_sp500_constituents

        if not config.USE_PIT_UNIVERSE:
            return None
        return build_membership(get_sp500_constituents())


@dataclass(frozen=True)
class KospiUniverse(Universe):
    def tickers(self) -> list[str]:
        from screener.universe_kr import get_kr_blue_chips

        return list(get_kr_blue_chips().keys())

    def sectors(self) -> pd.Series:
        from screener.universe_kr import get_kr_sectors

        return pd.Series(get_kr_sectors())


SP500 = SP500Universe(
    name="sp500",
    currency="USD",
    price_symbol_suffix="",
    db_path=config.DB_PATH,
    n_buckets=config.N_DECILES,
    prices_cache=config.PRICES_CACHE_PATH,
    panel_path=config.SCORES_PANEL_PATH,
    bucket_returns_path=config.DECILE_RETURNS_PATH,
    coefs_path=config.COEFS_PATH,
    validation_path=config.VALIDATION_SUMMARY_PATH,
    rolling_path=config.ROLLING_SPREAD_PATH,
    start=config.BACKTEST_START,
    end=config.BACKTEST_END,
)

KOSPI = KospiUniverse(
    name="kospi",
    currency="KRW",
    price_symbol_suffix=".KS",
    db_path=config.KR_DB_PATH,
    n_buckets=config.KR_N_BUCKETS,
    prices_cache=config.KR_PRICES_CACHE_PATH,
    panel_path=config.KR_SCORES_PANEL_PATH,
    bucket_returns_path=config.KR_BUCKET_RETURNS_PATH,
    coefs_path=config.KR_COEFS_PATH,
    validation_path=config.KR_VALIDATION_SUMMARY_PATH,
    rolling_path=config.KR_ROLLING_SPREAD_PATH,
    start=config.KR_BACKTEST_START,
    end=config.KR_BACKTEST_END,
)

UNIVERSES: dict[str, Universe] = {u.name: u for u in (SP500, KOSPI)}


def get_universe(name: str) -> Universe:
    if name not in UNIVERSES:
        raise KeyError(f"unknown universe {name!r}; known: {sorted(UNIVERSES)}")
    return UNIVERSES[name]
