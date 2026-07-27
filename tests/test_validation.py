"""Tests for the statistical layer, focused on the rolling decay chart.

The project spec asks for the rolling out-of-sample chart's band to be
"derived from the Deflated Sharpe Ratio calculation". An earlier revision
shipped a plain ±1.96 SE band instead, which answers a strictly weaker
question, so these tests pin the DSR-derived band in place.
"""

import numpy as np
import pandas as pd
import pytest

import config
from screener.validation import (
    _dsr_critical_return,
    _sr0_benchmark,
    deflated_sharpe_ratio,
    newey_west_lag,
    rolling_spread,
)


def _series(n=60, mean=0.0, sd=0.02, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-31", periods=n, freq="ME")
    return pd.Series(rng.normal(mean, sd, n), index=idx)


def test_newey_west_lag_matches_the_stated_rule():
    """floor(4*(T/100)^(2/9)) — implemented explicitly, not hardcoded."""
    for T in (26, 105, 167):
        assert newey_west_lag(T) == int(np.floor(4 * (T / 100.0) ** (2 / 9)))


def test_rolling_spread_emits_both_bands():
    r = rolling_spread(_series(), window=24)
    assert {"ann_spread", "lo", "hi", "dsr_lo", "dsr_hi"} <= set(r.columns)
    v = r.dropna()
    assert len(v) == 60 - 24 + 1


def test_dsr_band_is_symmetric_and_stricter_than_the_se_band():
    """The DSR band adds the multiple-testing benchmark SR0 on top of a
    confidence term, so it must sit OUTSIDE the plain SE band.

    An earlier revision plotted SR0 alone and called it stricter, which was
    backwards — the expected max of four draws sits near the 1.05σ level,
    below a 1.96σ interval. This test is what caught that."""
    v = rolling_spread(_series(n=80, seed=3), window=24).dropna()
    assert np.allclose(v["dsr_hi"], -v["dsr_lo"])          # symmetric about zero
    se_halfwidth = (v["hi"] - v["lo"]) / 2
    assert (v["dsr_hi"] > se_halfwidth).all()


def test_band_edge_is_exactly_where_the_windows_own_dsr_reaches_95pct():
    """The band is the DSR inverted, so 'outside the band' and 'this
    window's DSR >= 0.95' must be the same statement — not merely
    correlated with it."""
    rng = np.random.default_rng(5)
    s = pd.Series(rng.normal(0.004, 0.02, 160),
                  index=pd.date_range("2010-01-31", periods=160, freq="ME"))
    v = rolling_spread(s, window=24).dropna()
    for d in v.index:
        w = s.loc[:d].iloc[-24:]
        outside = v.loc[d, "ann_spread"] > v.loc[d, "dsr_hi"]
        assert outside == (deflated_sharpe_ratio(w)["dsr"] >= 0.95)


def test_more_trials_raise_the_hurdle():
    """Testing more strategies must make the bar harder to clear."""
    s = _series(n=60, seed=11)
    lo = rolling_spread(s, window=24, n_trials=2).dropna()["dsr_hi"]
    hi = rolling_spread(s, window=24, n_trials=20).dropna()["dsr_hi"]
    assert (hi > lo).all()


def test_single_trial_means_no_deflation_not_nan():
    """N=1 is the no-multiple-testing case. Phi^-1(1 - 1/1) is -inf, so the
    expected-maximum formula degenerates; the limit is zero deflation, and
    returning NaN would silently blank the whole band."""
    w = _series(n=24, seed=2).to_numpy()
    assert _sr0_benchmark(w, 1) == 0.0
    assert np.isfinite(_dsr_critical_return(w, 1))
    # and with no deflation the band collapses toward the pure confidence term
    assert _dsr_critical_return(w, 1) < _dsr_critical_return(w, 4)


def test_degenerate_window_yields_nan_not_a_fake_hurdle():
    """A zero-variance window has no meaningful Sharpe; the hurdle must be
    NaN rather than 0, which would read as 'any return clears the bar'."""
    flat = pd.Series(0.0, index=pd.date_range("2015-01-31", periods=30, freq="ME"))
    v = rolling_spread(flat, window=24)
    assert v["dsr_hi"].dropna().empty or v["dsr_hi"].dropna().isna().all()
    assert np.isnan(_sr0_benchmark(np.zeros(24), 4))
    assert np.isnan(_dsr_critical_return(np.zeros(24), 4))


def test_committed_korean_rolling_artifact_has_the_dsr_band():
    """Guards the artifact the dashboard actually reads."""
    from pathlib import Path

    p = Path(config.KR_ROLLING_SPREAD_PATH)
    if not p.exists():
        pytest.skip("Korean rolling artifact not built")
    r = pd.read_parquet(p).dropna()
    assert {"ann_spread", "dsr_lo", "dsr_hi"} <= set(r.columns)
    assert len(r) > 50
    assert (r["dsr_hi"] > 0).all()
