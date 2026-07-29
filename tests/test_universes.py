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


def test_india_is_registered_but_not_backtestable():
    """India's source yields ~3 usable annual cross-sections — enough to
    rank a screen, nowhere near enough for return-series inference. The
    flag is what stops the pipeline producing a validation table that would
    look like evidence."""
    from screener.universes import INDIA

    assert INDIA.backtestable is False
    assert SP500.backtestable is True and KOSPI.backtestable is True
    assert INDIA.price_symbol_suffix == ".NS"
    assert INDIA.currency == "INR"
    assert get_universe("india") is INDIA


def test_all_three_universes_have_distinct_paths():
    from screener.universes import INDIA

    for attr in ("db_path", "prices_cache", "panel_path", "bucket_returns_path",
                 "validation_path", "rolling_path"):
        paths = {getattr(u, attr) for u in (SP500, KOSPI, INDIA)}
        assert len(paths) == 3, f"{attr} collides across universes"


def test_dashboard_renders_without_backtest_artifacts(tmp_path, monkeypatch):
    """The dashboard must degrade honestly: with no bucket returns,
    validation table or rolling spread on disk, it still builds, and the
    dependent tabs show an explanation instead of an empty chart."""
    import pandas as pd
    from dataclasses import replace

    import dashboard.app as appmod
    from screener.universes import INDIA

    dates = pd.to_datetime(["2025-01-31", "2025-02-28"])
    rows = []
    for d in dates:
        for i in range(30):
            rows.append(dict(as_of_date=d, ticker=f"T{i}", sector="Technology" if i % 2 else "Energy",
                             f_score=float(i % 10), z_score=1.0 + i / 10, o_score=-5.0 - i / 10,
                             f_score_z=0.0, z_score_z=0.0, o_score_z=0.0,
                             composite_score=float(i), decile=float(i % 5 + 1),
                             fwd_ret_1m=0.01 * (i % 7 - 3), fwd_ret_demeaned=0.0))
    panel_path = tmp_path / "panel.parquet"
    pd.DataFrame(rows).to_parquet(panel_path)

    uni = replace(INDIA, panel_path=panel_path,
                  bucket_returns_path=tmp_path / "absent_returns.parquet",
                  validation_path=tmp_path / "absent_validation.csv",
                  rolling_path=tmp_path / "absent_rolling.parquet")
    panel, dec, summary, roll = appmod.load_data(uni)
    assert dec is None and summary is None and roll is None   # absent, not fabricated
    assert len(panel) == 60

    app = appmod.build_app(uni)          # must not raise
    rendered = str(app.layout)
    assert "not available for india" in rendered
    assert "Screener table" in rendered and "Sector heatmap" in rendered


def _run_screen_fixture(tmp_path, monkeypatch, n_months=6, n_tickers=40):
    """Shared fixture: a fake scores panel wide/long enough to exercise
    run_screen's bucket-return and rolling-spread computation, with
    randomized (not constant) forward returns so a spread series with real
    variance comes out the other end."""
    from dataclasses import replace

    import numpy as np
    import pandas as pd

    import screener.backtest as bt
    from screener.universes import INDIA

    dates = pd.date_range("2025-01-31", periods=n_months, freq="ME")
    tickers = [f"T{i}" for i in range(n_tickers)]
    rng = np.random.default_rng(0)

    def fake_panel(rebalance_dates, tks, sectors, prices, membership=None, db_path=None):
        idx = pd.MultiIndex.from_product([dates, tickers], names=["as_of_date", "ticker"])
        df = pd.DataFrame(index=idx)
        for c in ["f_score_z", "z_score_z", "o_score_z"]:
            df[c] = rng.normal(size=len(df))
        for c in ["f_score", "z_score", "o_score"]:
            df[c] = 0.5
        df["fwd_ret_1m"] = rng.normal(0, 0.02, len(df))
        df["fwd_ret_demeaned"] = 0.0
        df["sector"] = "Technology"
        return df

    monkeypatch.setattr(bt, "build_scores_panel", fake_panel)
    monkeypatch.setattr(bt, "get_monthly_prices",
                        lambda *a, **k: pd.DataFrame(1.0, index=dates, columns=tickers))
    monkeypatch.setattr(type(INDIA), "tickers", lambda self: tickers)
    monkeypatch.setattr(type(INDIA), "sectors", lambda self: pd.Series("Technology", index=tickers))

    return replace(
        INDIA, start="2025-01-01", end=(dates[-1] + pd.DateOffset(days=1)).strftime("%Y-%m-%d"),
        n_buckets=5,
        panel_path=tmp_path / "panel.parquet",
        bucket_returns_path=tmp_path / "returns.parquet",
        coefs_path=tmp_path / "coefs.parquet",
        validation_path=tmp_path / "validation.csv",
        rolling_path=tmp_path / "rolling.parquet",
    )


def test_screen_writes_panel_and_bucket_returns_but_no_lasso_or_validation(tmp_path, monkeypatch):
    """run_screen produces the scores panel AND a bucket-return series (the
    rolling chart is built from it), but never LASSO coefficients or a
    Newey-West/Deflated-Sharpe validation table — a single point estimate
    over a handful of independent fundamental updates is not a test, and a
    table of t-stats sitting next to the US/Korea ones would misrepresent
    that. This is the contract FINDINGS.md documents for India."""
    import screener.backtest as bt

    uni = _run_screen_fixture(tmp_path, monkeypatch, n_months=6)
    bt.run_screen(uni)

    assert uni.panel_path.exists()
    assert uni.bucket_returns_path.exists()
    for should_not_exist in (uni.coefs_path, uni.validation_path):
        assert not should_not_exist.exists(), f"{should_not_exist.name} must not be written"


def test_screen_rolling_spread_written_when_enough_months_exist(tmp_path, monkeypatch, caplog):
    """With more months than the rolling window, run_screen also writes the
    rolling-spread parquet the dashboard reads, carrying the DSR-derived
    band exactly like the US/Korea artifacts — and logs a warning that this
    is a shape diagnostic, not a statistical test."""
    import logging

    import screener.backtest as bt

    uni = _run_screen_fixture(tmp_path, monkeypatch, n_months=30)
    with caplog.at_level(logging.WARNING):
        bt.run_screen(uni)

    assert uni.rolling_path.exists()
    roll = pd.read_parquet(uni.rolling_path)
    assert {"ann_spread", "dsr_lo", "dsr_hi"} <= set(roll.columns)
    assert any("shape diagnostic, not a statistical test" in r.message for r in caplog.records)


def test_screen_rolling_spread_skipped_when_too_few_months(tmp_path, monkeypatch):
    """A 2-month spread series can't feed rolling() at all (nothing to
    roll) — no rolling artifact should be written rather than an
    all-NaN one."""
    import screener.backtest as bt

    uni = _run_screen_fixture(tmp_path, monkeypatch, n_months=2)
    bt.run_screen(uni)

    assert not uni.rolling_path.exists()


def test_screen_composite_is_equal_weight_not_fitted(tmp_path, monkeypatch):
    """A LASSO fit on ~3 independent cross-sections would be fitting noise,
    so screener-only universes use the documented equal-weight prior. The
    composite must be exactly the mean of the three z-scores."""
    from dataclasses import replace

    import pandas as pd

    import screener.backtest as bt
    from screener.universes import INDIA

    dates = pd.to_datetime(["2025-01-31"])
    tickers = [f"T{i}" for i in range(30)]

    def fake_panel(*a, **k):
        idx = pd.MultiIndex.from_product([dates, tickers], names=["as_of_date", "ticker"])
        df = pd.DataFrame(index=idx)
        df["f_score_z"] = 1.0
        df["z_score_z"] = 2.0
        df["o_score_z"] = 3.0
        df["fwd_ret_1m"] = 0.0
        return df

    monkeypatch.setattr(bt, "build_scores_panel", fake_panel)
    monkeypatch.setattr(bt, "get_monthly_prices",
                        lambda *a, **k: pd.DataFrame(1.0, index=dates, columns=tickers))
    monkeypatch.setattr(type(INDIA), "tickers", lambda self: tickers)
    monkeypatch.setattr(type(INDIA), "sectors", lambda self: pd.Series("Tech", index=tickers))

    uni = replace(INDIA, start="2025-01-01", end="2025-02-28",
                  panel_path=tmp_path / "p.parquet")
    panel = bt.run_screen(uni)
    assert (panel["composite_score"] == 2.0).all()   # mean(1, 2, 3), no fitted weights


def test_fig_rolling_labels_non_backtestable_charts_as_descriptive():
    """The India rolling chart must be visually distinguishable from the
    US/Korea ones — a viewer skimming tabs should not mistake 3 points for
    a validated result. backtestable=False must add the warning label,
    the annotation, and markers on the sparse points; the US/Korea charts
    (backtestable=True, the default) must be unaffected."""
    import pandas as pd

    from dashboard.app import fig_rolling

    idx = pd.date_range("2025-01-31", periods=3, freq="ME")
    roll = pd.DataFrame({
        "ann_spread": [0.01, 0.03, 0.02], "lo": [-0.1, -0.09, -0.1], "hi": [0.12, 0.15, 0.14],
        "dsr_lo": [-0.18, -0.19, -0.18], "dsr_hi": [0.18, 0.19, 0.18],
    }, index=idx)

    sparse = fig_rolling(roll, "india", backtestable=False)
    assert "descriptive only" in sparse.layout.title.text
    assert "not a test" in sparse.layout.title.text
    assert len(sparse.layout.annotations) == 1
    assert "3" in sparse.layout.annotations[0].text
    assert sparse.data[-1].mode == "lines+markers"   # sparse points must be visible, not just a line

    normal = fig_rolling(roll, "sp500")   # backtestable defaults to True
    assert "descriptive only" not in normal.layout.title.text
    assert len(normal.layout.annotations) == 0
    assert normal.data[-1].mode == "lines"
