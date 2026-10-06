"""Dashboard diagnostics: month explorer, robustness checks, run overview.

The load-bearing property is that these rebuild the backtest's own numbers
exactly when nothing is perturbed — otherwise a "robustness" result would
differ from the validation table because of a second implementation, not
because of the perturbation."""

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from dashboard import analysis
from screener.backtest import bucket_return_series
from screener.universes import SP500


def _panel(n_months=36, n_names=50, n_buckets=5, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.date_range("2020-01-31", periods=n_months, freq="ME"):
        for i in range(n_names):
            rows.append(dict(as_of_date=d, ticker=f"T{i}", sector="Energy" if i % 2 else "Tech",
                             decile=float(i % n_buckets + 1), fwd_ret_1m=rng.normal(0.01, 0.08)))
    return pd.DataFrame(rows)


def test_spread_excluding_nothing_reproduces_the_backtest_spread():
    p = _panel()
    expected = bucket_return_series(p.set_index(["as_of_date", "ticker"]), n_buckets=5)["spread"]
    got = analysis.spread_excluding(p, [], 5)
    pd.testing.assert_series_equal(got, expected, check_names=False, check_freq=False,
                                   check_index_type=False)


def test_excluding_a_name_removes_only_that_name():
    p = _panel()
    p.loc[(p["ticker"] == "T4") & (p["as_of_date"] == "2020-03-31"), "fwd_ret_1m"] = 20.0  # a GME month
    with_it = analysis.spread_excluding(p, [], 5)
    without = analysis.spread_excluding(p, [" t4 "], 5)        # case/whitespace-insensitive
    jump = (with_it - without).abs()
    assert jump.idxmax() == pd.Timestamp("2020-03-31") and jump.max() > 1.5
    assert (jump.drop(pd.Timestamp("2020-03-31")) < 0.05).all()


def test_month_contributions_sum_to_the_spread_and_rank_by_size():
    p = _panel()
    p.loc[(p["ticker"] == "T4") & (p["as_of_date"] == "2020-03-31"), "fwd_ret_1m"] = 20.0
    m = analysis.month_buckets(p, "2020-03-31", 5)
    c = m["contributors"]
    assert c["contribution"].sum() == pytest.approx(m["spread"])
    assert c.iloc[0]["ticker"] == "T4" and c.iloc[0]["bucket"] == "D5"
    assert m["buckets"]["top"]["mean"] > m["buckets"]["top"]["median"]   # carried by one name
    assert set(c["bucket"]) == {"D1", "D5"}


def test_robustness_rows_change_one_thing_each():
    s = pd.Series(np.r_[np.full(40, 0.002), [0.9, 0.8], np.full(20, -0.001)],
                  index=pd.date_range("2015-01-31", periods=62, freq="ME"))
    t = analysis.robustness_table(s, winsor_pct=1, drop_top=2, drop_bottom=1)
    assert list(t["scenario"].str.split().str[0]) == ["Baseline", "Winsorized", "Drop", "Drop"]
    assert t.loc[0, "months"] == 62 and t.loc[2, "months"] == 60 and t.loc[3, "months"] == 61
    assert "2018-05" in t.loc[2, "scenario"] and "2018-06" in t.loc[2, "scenario"]
    assert t.loc[2, "ann_return"] < t.loc[0, "ann_return"]       # dropping the outliers hurts


def test_robustness_refuses_to_score_too_short_a_series():
    s = pd.Series(np.full(12, 0.01), index=pd.date_range("2020-01-31", periods=12, freq="ME"))
    row = analysis.robustness_table(s, winsor_pct=0).iloc[0]
    assert np.isnan(row["dsr"]) and not row["survives_95"]


def test_overview_reads_composite_rows_and_flags_stale(tmp_path):
    import os
    import time

    val, ret = tmp_path / "v.csv", tmp_path / "r.parquet"
    pd.DataFrame({"months": [100], "ann_return": [0.01], "nw_tstat": [0.5], "dsr": [0.3],
                  "survives_95": [False]}, index=pd.Index(["Composite (LASSO)"], name="strategy")).to_csv(val)
    ret.write_text("x")
    old = time.time() - 100
    os.utime(val, (old, old))
    uni = replace(SP500, validation_path=val, bucket_returns_path=ret)
    df = analysis.run_overview({"sp500": uni}, survivorship_supported=lambda n: False)
    assert len(df) == 1 and df.iloc[0]["stale"] and df.iloc[0]["dsr"] == 0.3
    assert analysis.run_overview({"sp500": replace(uni, validation_path=tmp_path / "none.csv")},
                                 survivorship_supported=lambda n: False).empty


def test_sector_contributions_sum_to_the_arithmetic_spread():
    p = _panel()
    a = analysis.sector_attribution(p, 5)
    spread = analysis.spread_excluding(p, [], 5)
    assert a["ann_contribution"].sum() == pytest.approx(spread.mean() * 12)
    assert set(a["sector"]) == {"Energy", "Tech"}
    assert (a["avg_top_names"] + a["avg_bottom_names"]).sum() == pytest.approx(20)  # 10 + 10 per month


def test_excluding_a_sector_drops_all_its_names():
    p = _panel()
    only_tech = analysis.spread_excluding(p, [], 5, sectors=["Energy"])
    manual = analysis.spread_excluding(p[p["sector"] == "Tech"], [], 5)
    pd.testing.assert_series_equal(only_tech, manual)


def test_threshold_screens_use_published_cutoffs_and_fail_missing_scores():
    from dashboard.app import apply_screens, latest_cross_section

    d = pd.Timestamp("2025-12-31")
    p = pd.DataFrame({
        "as_of_date": d, "ticker": ["A", "B", "C", "D"], "sector": "X",
        "f_score": [9.0, 8.0, 3.0, np.nan], "z_score": [3.5, 2.0, 1.0, 5.0],
        "o_score": [-5.0, 0.0, 1.0, -3.0], "composite_score": [1.0, 0.5, -1.0, 0.2], "decile": 1.0,
    })
    x = latest_cross_section(p)
    assert x.set_index("ticker").loc["B", "o_default_prob"] == pytest.approx(0.5)
    assert list(apply_screens(x, ["f_high"])["ticker"]) == ["A", "B"]          # D has no F: fails
    assert list(apply_screens(x, ["f_high", "z_safe"])["ticker"]) == ["A"]      # AND, not OR
    assert list(apply_screens(x, ["z_grey"])["ticker"]) == ["B"]
    assert list(apply_screens(x, ["o_risk"])["ticker"]) == ["C"]                # O > 0 strictly
    assert len(apply_screens(x, [])) == 4


def _book(members_by_month):
    rows = []
    for d, (top, bottom) in members_by_month.items():
        rows += [dict(as_of_date=pd.Timestamp(d), ticker=t, sector="X", decile=2.0, fwd_ret_1m=0.0) for t in top]
        rows += [dict(as_of_date=pd.Timestamp(d), ticker=t, sector="X", decile=1.0, fwd_ret_1m=0.0) for t in bottom]
    return pd.DataFrame(rows)


def test_turnover_is_the_fraction_of_each_leg_replaced():
    p = _book({"2020-01-31": (["A", "B", "C", "D"], ["W", "X"]),
               "2020-02-29": (["A", "B", "C", "E"], ["W", "X"]),     # top swaps 1 of 4
               "2020-03-31": (["F", "G", "H", "I"], ["Y", "Z"])})    # both legs fully replaced
    t = analysis.bucket_turnover(p, 2)
    assert np.isnan(t["top"].iloc[0])
    assert t["top"].tolist()[1:] == pytest.approx([0.25, 1.0])
    assert t["bottom"].tolist()[1:] == pytest.approx([0.0, 1.0])


def test_costs_charge_both_legs_round_trip():
    idx = pd.to_datetime(["2020-01-31", "2020-02-29"])
    spread = pd.Series([0.01, 0.01], index=idx)
    turn = pd.DataFrame({"top": [np.nan, 0.25], "bottom": [np.nan, 0.5]}, index=idx)
    net = analysis.net_of_costs(spread, turn, 100)                   # 1% one-way
    # month 2: traded 2*(0.25+0.5) = 1.5 of capital -> 1.5% drag
    assert net.tolist() == pytest.approx([0.01, 0.01 - 0.015])
    assert analysis.net_of_costs(spread, turn, 0).equals(spread.rename("spread"))


def test_breakeven_and_dsr_failure_costs():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2010-01-31", periods=120, freq="ME")
    spread = pd.Series(0.02 + rng.normal(0, 0.01, 120), index=idx)
    turn = pd.DataFrame({"top": 0.1, "bottom": 0.1}, index=idx)
    be = analysis.breakeven_cost_bps(spread, turn)
    assert analysis.net_of_costs(spread, turn, be).mean() == pytest.approx(0, abs=1e-12)
    fail = analysis.dsr_fail_cost_bps(spread, turn)
    assert 0 < fail < be
    assert analysis._stats(analysis.net_of_costs(spread, turn, fail))["survives_95"] is False
    assert analysis._stats(analysis.net_of_costs(spread, turn, fail - 1))["survives_95"] is True
    assert np.isnan(analysis.breakeven_cost_bps(-spread, turn))


def test_legs_sum_to_spread_and_beta_is_recovered():
    rng = np.random.default_rng(3)
    dates = pd.date_range("2015-01-31", periods=60, freq="ME")
    mkt = rng.normal(0.01, 0.04, len(dates))
    rows = []
    for d, m in zip(dates, mkt):
        for i in range(50):
            b = i % 5 + 1
            # top bucket has beta 1.5 to the market, everything else beta 1
            r = (1.5 if b == 5 else 1.0) * m + rng.normal(0, 0.002)
            rows.append(dict(as_of_date=d, ticker=f"T{i}", decile=float(b), fwd_ret_1m=r))
    legs = analysis.leg_decomposition(pd.DataFrame(rows), 5)
    assert np.allclose(legs["long_excess"] + legs["short_excess"], legs["spread"])
    ex = analysis.market_exposure(legs)
    assert ex["beta"] == pytest.approx(0.5 / 1.1, abs=0.05)   # (1.5 - 1) / market beta 1.1
    assert ex["up_mean"] > 0 > ex["down_mean"]
    t = analysis.leg_table(legs).set_index("scenario")
    assert np.isnan(t.loc["Top bucket, raw", "dsr"]) and t.loc["Top bucket, raw", "survives_95"] is None


def test_one_month_horizon_reproduces_the_backtest_forward_return():
    dates = pd.date_range("2020-01-31", periods=30, freq="ME")
    rng = np.random.default_rng(5)
    prices = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0.01, 0.05, (30, 10)), axis=0),
                          index=dates, columns=[f"T{i}" for i in range(10)])
    prices.iloc[:4, 0] = np.nan                                      # a late listing
    rets = prices.pct_change(fill_method=None)
    rows = [dict(as_of_date=d, ticker=t, decile=float(i % 2 + 1),
                 fwd_ret_1m=rets[t].iloc[j + 1] if j + 1 < len(dates) else np.nan)
            for j, d in enumerate(dates) for i, t in enumerate(prices.columns)]
    panel = pd.DataFrame(rows)
    hs = analysis.horizon_spreads(panel, prices, 2, horizons=(1, 3))
    expected = analysis.spread_excluding(panel, [], 2)
    pd.testing.assert_series_equal(hs[1], expected.dropna(), check_names=False, check_freq=False)
    # 3-month return is the compounded product of three monthly returns
    f3 = analysis.forward_returns(prices, 3)
    manual = (1 + rets.shift(-1)) * (1 + rets.shift(-2)) * (1 + rets.shift(-3)) - 1
    pd.testing.assert_frame_equal(f3, manual, check_freq=False)
    assert len(hs[3]) == len(hs[1]) - 2


def test_horizon_table_uses_at_least_k_minus_one_lags():
    idx = pd.date_range("2010-01-31", periods=60, freq="ME")
    rng = np.random.default_rng(2)
    t = analysis.horizon_table({1: pd.Series(rng.normal(0, 0.02, 60), index=idx),
                                12: pd.Series(rng.normal(0, 0.05, 60), index=idx)}).set_index("horizon_months")
    assert t.loc[12, "nw_lag"] == 11 and t.loc[1, "nw_lag"] < 11
