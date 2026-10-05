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
