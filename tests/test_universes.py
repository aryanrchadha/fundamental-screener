"""Tests for the Universe abstraction that lets one backtest serve two markets.

These guard the specific things that were previously hardcoded to the S&P
500 and would regress silently: the Yahoo exchange suffix, the bucket count,
and the per-universe output paths (two universes writing to one path would
have each overwritten the other's results).
"""

import pandas as pd
import pytest

from screener.prices import get_monthly_prices
from screener.universes import KOSPI, SP500, get_universe


def test_kospi_uses_krx_suffix_and_sp500_does_not():
    assert SP500.price_symbol_suffix == ""
    assert KOSPI.price_symbol_suffix == ".KS"


def test_bucket_count_scales_with_universe_width():
    """120 KOSPI names split into deciles would leave ~7 per bucket after
    score exclusions, so the Korean universe uses quintiles. The count is a
    property of the universe, not a global constant."""
    assert SP500.n_buckets == 10
    assert KOSPI.n_buckets == 5
    assert SP500.top_bucket == "D10" and KOSPI.top_bucket == "D5"
    assert SP500.bottom_bucket == KOSPI.bottom_bucket == "D1"


def test_universes_never_share_an_output_path():
    """Two universes writing to the same parquet would silently clobber each
    other's panel, returns, and validation table."""
    for attr in ("db_path", "prices_cache", "panel_path", "bucket_returns_path",
                 "coefs_path", "validation_path", "rolling_path"):
        assert getattr(SP500, attr) != getattr(KOSPI, attr), f"{attr} collides"


def test_get_universe_rejects_unknown_name():
    assert get_universe("kospi") is KOSPI
    with pytest.raises(KeyError):
        get_universe("nikkei")


def test_kospi_universe_csv_is_well_formed():
    """The universe ships as a tracked CSV so a clean clone reproduces the
    exact backtest set without an API key."""
    from screener.universe_kr import get_kr_blue_chips, get_kr_sectors, load_universe

    u = load_universe()
    assert len(u) == 120
    assert u["ticker"].str.fullmatch(r"\d{6}").all()      # KRX 6-digit codes
    assert u["corp_code"].str.fullmatch(r"\d{8}").all()   # DART 8-digit codes
    assert u["ticker"].is_unique and u["corp_code"].is_unique
    assert set(get_kr_blue_chips()) == set(get_kr_sectors())
    assert u["sector"].str.startswith("KSIC-").all()


def test_price_symbol_suffix_is_stripped_from_returned_columns(monkeypatch, tmp_path):
    """The exchange suffix is a vendor detail: it must go out to Yahoo and
    be stripped on the way back, so the rest of the pipeline only ever sees
    canonical tickers."""
    captured = {}

    def fake_download(symbols, **kwargs):
        captured["symbols"] = list(symbols)
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        cols = pd.MultiIndex.from_product([["Close"], list(symbols)])
        return pd.DataFrame(1.0, index=idx, columns=cols)

    import yfinance

    monkeypatch.setattr(yfinance, "download", fake_download)
    out = get_monthly_prices(
        ["005930", "000660"], start="2024-01-01", end="2024-02-10",
        cache_path=tmp_path / "px.parquet", symbol_suffix=".KS",
    )
    assert captured["symbols"] == ["005930.KS", "000660.KS"]   # suffix applied outbound
    assert list(out.columns) == ["005930", "000660"]           # and stripped inbound


def test_unknown_ticker_still_gets_a_column(monkeypatch, tmp_path):
    """Yahoo omits symbols it doesn't know. Reindexing keeps one column per
    requested ticker (all-NaN) so the frame's shape can't silently shrink."""
    def fake_download(symbols, **kwargs):
        idx = pd.date_range("2024-01-01", periods=40, freq="D")
        known = [s for s in symbols if s != "999999.KS"]
        cols = pd.MultiIndex.from_product([["Close"], known])
        return pd.DataFrame(1.0, index=idx, columns=cols)

    import yfinance

    monkeypatch.setattr(yfinance, "download", fake_download)
    out = get_monthly_prices(
        ["005930", "999999"], start="2024-01-01", end="2024-02-10",
        cache_path=tmp_path / "px2.parquet", symbol_suffix=".KS",
    )
    assert list(out.columns) == ["005930", "999999"]
    assert out["999999"].isna().all()
