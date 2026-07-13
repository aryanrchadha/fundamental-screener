"""Tests for the LASSO composite — most importantly, that alpha selection
uses TimeSeriesSplit (the easy-to-silently-regress leakage risk)."""

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, TimeSeriesSplit

from screener import composite


def test_cv_splitter_is_time_series_split():
    """Inspect the splitter object type directly: KFold here would leak
    future cross-sections into past training folds."""
    cv = composite.make_cv()
    assert isinstance(cv, TimeSeriesSplit)
    assert not isinstance(cv, KFold)


def _synthetic_panel(n_months=40, n_tickers=30, seed=1):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2015-01-31", periods=n_months, freq="ME")
    tickers = [f"T{i}" for i in range(n_tickers)]
    idx = pd.MultiIndex.from_product([dates, tickers], names=["as_of_date", "ticker"])
    df = pd.DataFrame(index=idx)
    df["f_score_z"] = rng.normal(size=len(df))
    df["z_score_z"] = rng.normal(size=len(df))
    df["o_score_z"] = rng.normal(size=len(df))
    # Label driven mostly by f_score_z so the LASSO has signal to find.
    df["fwd_ret_demeaned"] = 0.02 * df["f_score_z"] + rng.normal(0, 0.01, len(df))
    # Last 7 months' labels unknown (forward window not finished).
    last = dates[-7:]
    df.loc[pd.IndexSlice[last, :], "fwd_ret_demeaned"] = np.nan
    return df


def test_composite_walk_forward_produces_scores_and_coefs():
    panel = _synthetic_panel()
    scores, coefs = composite.compute_composite(panel)
    assert scores.index.equals(panel.index)
    # Later cross-sections must be scored by a fitted model.
    last_date = panel.index.get_level_values("as_of_date").max()
    assert scores.loc[last_date].notna().all()
    assert len(coefs) >= 1
    # The dominant synthetic driver should carry the largest weight.
    assert coefs["f_score_z"].iloc[-1] > abs(coefs["z_score_z"].iloc[-1])
    assert coefs["f_score_z"].iloc[-1] > abs(coefs["o_score_z"].iloc[-1])


def test_early_dates_use_equal_weight_fallback():
    panel = _synthetic_panel(n_months=10)  # < MIN_TRAIN_MONTHS of labels
    scores, coefs = composite.compute_composite(panel)
    assert len(coefs) == 0
    first_date = panel.index.get_level_values("as_of_date").min()
    xsec = panel.loc[first_date]
    expected = xsec[["f_score_z", "z_score_z", "o_score_z"]].mean(axis=1)
    pd.testing.assert_series_equal(
        scores.loc[first_date], expected, check_names=False
    )


def test_missing_features_not_scored():
    panel = _synthetic_panel()
    first_date = panel.index.get_level_values("as_of_date").min()
    panel.loc[(first_date, "T0"), "f_score_z"] = np.nan
    scores, _ = composite.compute_composite(panel)
    assert np.isnan(scores.loc[(first_date, "T0")])
