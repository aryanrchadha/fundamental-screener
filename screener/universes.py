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

from dataclasses import dataclass, field, replace
from pathlib import Path

import pandas as pd

import config


def _suffixed(path: Path, suffix: str) -> Path:
    """data/x.parquet + '_pit' -> data/x_pit.parquet"""
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


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
    # When True, each rebalance is restricted to names that were actually
    # listed/constituents on that date (survivorship-bias-corrected mode).
    survivorship_corrected: bool = False
    # False for markets whose data cannot support a return-series backtest.
    # India's source yields ~3 usable annual cross-sections, which is enough
    # to rank a screen and far too little for Newey-West/Deflated-Sharpe
    # inference, so no bucket returns or validation table are produced for
    # it and the dashboard hides the views that would depend on them.
    backtestable: bool = True
    # Populated lazily so importing this module never triggers a network call.
    _tickers: tuple[str, ...] | None = field(default=None)

    def tickers(self) -> list[str]:
        raise NotImplementedError

    def sectors(self) -> pd.Series:
        raise NotImplementedError

    def membership(self) -> pd.DataFrame | None:
        """Point-in-time constituent history, or None to use a static list."""
        return None

    def corrected(self) -> "Universe":
        """A survivorship-corrected twin writing to its own `_pit` outputs.

        Separate paths matter: the point of the correction is to compare the
        two runs side by side, which is impossible if the second overwrites
        the first. The PIT database and price cache are deliberately SHARED
        — the same facts and prices feed both runs, and only the per-date
        universe filter differs.
        """
        return replace(
            self,
            survivorship_corrected=True,
            panel_path=_suffixed(self.panel_path, "_pit"),
            bucket_returns_path=_suffixed(self.bucket_returns_path, "_pit"),
            coefs_path=_suffixed(self.coefs_path, "_pit"),
            validation_path=_suffixed(self.validation_path, "_pit"),
            rolling_path=_suffixed(self.rolling_path, "_pit"),
        )

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
        """Wikipedia's 'selected changes' table, unwound backwards from
        today's list. Only consulted in survivorship-corrected mode (or if
        config.USE_PIT_UNIVERSE is set globally, kept for back-compat)."""
        from screener.universe import build_membership, get_sp500_constituents

        if not (self.survivorship_corrected or config.USE_PIT_UNIVERSE):
            return None
        return build_membership(get_sp500_constituents())


@dataclass(frozen=True)
class IndiaUniverse(Universe):
    def tickers(self) -> list[str]:
        from screener.universe_in import get_in_universe

        return list(get_in_universe().keys())

    def sectors(self) -> pd.Series:
        from screener.universe_in import get_in_sectors

        return pd.Series(get_in_sectors())


@dataclass(frozen=True)
class KospiUniverse(Universe):
    def tickers(self) -> list[str]:
        from screener.universe_kr import get_kr_blue_chips

        return list(get_kr_blue_chips().keys())

    def sectors(self) -> pd.Series:
        from screener.universe_kr import get_kr_sectors

        return pd.Series(get_kr_sectors())

    def membership(self) -> pd.DataFrame | None:
        """First-KOSPI-annual-filing dates per company. Corrects look-ahead
        (13 of the 120 listed after 2016); delisting survivorship is NOT
        correctable with free data — see build_kr_membership's docstring."""
        from screener.universe_kr import build_kr_membership

        if not self.survivorship_corrected:
            return None
        return build_kr_membership()


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

INDIA = IndiaUniverse(
    name="india",
    currency="INR",
    price_symbol_suffix=".NS",
    db_path=config.IN_DB_PATH,
    n_buckets=config.IN_N_BUCKETS,
    prices_cache=config.IN_PRICES_CACHE_PATH,
    panel_path=config.IN_SCORES_PANEL_PATH,
    bucket_returns_path=config.IN_BUCKET_RETURNS_PATH,
    coefs_path=config.IN_COEFS_PATH,
    validation_path=config.IN_VALIDATION_SUMMARY_PATH,
    rolling_path=config.IN_ROLLING_SPREAD_PATH,
    start=config.IN_SCREEN_START,
    end=config.IN_SCREEN_END,
    backtestable=False,
)

UNIVERSES: dict[str, Universe] = {u.name: u for u in (SP500, KOSPI, INDIA)}


def get_universe(name: str) -> Universe:
    if name not in UNIVERSES:
        raise KeyError(f"unknown universe {name!r}; known: {sorted(UNIVERSES)}")
    return UNIVERSES[name]
