"""Backtest mechanics: PIT-universe exclusion (survivorship correction) and
decile formation."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from screener.backtest import bucket_return_series, filter_universe, form_buckets
from screener.universe import was_member


def _membership_fixture() -> pd.DataFrame:
    """Synthetic constituent history:
    - OLDCO: member until removed 2015-06-01
    - NEWCO: added 2018-03-01, still a member
    - EVERCO: member the whole time
    """
    return pd.DataFrame(
        [
            {"ticker": "OLDCO", "start": pd.NaT, "end": pd.Timestamp("2015-06-01")},
            {"ticker": "NEWCO", "start": pd.Timestamp("2018-03-01"), "end": pd.NaT},
            {"ticker": "EVERCO", "start": pd.NaT, "end": pd.NaT},
        ]
    )


def test_non_constituent_excluded_at_rebalance():
    membership = _membership_fixture()
    tickers = ["OLDCO", "NEWCO", "EVERCO"]
    # 2016: OLDCO already removed, NEWCO not yet added.
    active_2016 = filter_universe(date(2016, 1, 31), tickers, membership)
    assert active_2016 == ["EVERCO"]
    # 2014: OLDCO still in, NEWCO not yet.
    active_2014 = filter_universe(date(2014, 1, 31), tickers, membership)
    assert set(active_2014) == {"OLDCO", "EVERCO"}
    # 2019: NEWCO in, OLDCO out.
    active_2019 = filter_universe(date(2019, 1, 31), tickers, membership)
    assert set(active_2019) == {"NEWCO", "EVERCO"}


def test_was_member_boundaries():
    membership = _membership_fixture()
    assert was_member("OLDCO", date(2015, 5, 31), membership)
    assert not was_member("OLDCO", date(2015, 6, 1), membership)  # removal date exclusive
    assert was_member("NEWCO", date(2018, 3, 1), membership)      # addition date inclusive
    assert not was_member("UNKNOWN", date(2018, 3, 1), membership)


def test_filter_universe_passthrough_without_membership():
    tickers = ["A", "B"]
    assert filter_universe(date(2020, 1, 31), tickers, None) == tickers


def test_form_buckets_assignment():
    scores = pd.Series(np.arange(100, dtype=float), index=[f"T{i}" for i in range(100)])
    dec = form_buckets(scores, n_buckets=10)
    assert dec["T0"] == 1          # worst score -> bucket 1
    assert dec["T99"] == 10        # best score -> bucket 10
    assert dec.value_counts().eq(10).all()


def test_form_buckets_handles_nans_and_small_sections():
    scores = pd.Series([1.0, 2.0, np.nan], index=list("ABC"))
    dec = form_buckets(scores, n_buckets=10)  # too few valid names
    assert dec.isna().all()


def test_form_buckets_supports_non_decile_counts():
    """The KOSPI universe uses quintiles because a 120-name cross-section
    split into deciles leaves ~7 names per bucket. Bucket count must be a
    parameter, not the hardcoded 10 the S&P 500 path assumed."""
    scores = pd.Series(np.arange(100, dtype=float), index=[f"T{i}" for i in range(100)])
    q = form_buckets(scores, n_buckets=5)
    assert set(q.dropna().unique()) == {1.0, 2.0, 3.0, 4.0, 5.0}
    assert q.value_counts().eq(20).all()
    assert q["T0"] == 1 and q["T99"] == 5


def test_spread_is_top_minus_bottom_bucket_for_any_n():
    """`spread` must mean top-minus-bottom whatever N is, so validation and
    the dashboard stay universe-agnostic. With 5 buckets that is D5-D1;
    looking for a hardcoded 'D10' would silently yield no spread column."""
    dates = pd.to_datetime(["2020-01-31", "2020-02-29"])
    idx = pd.MultiIndex.from_product([dates, [f"T{i}" for i in range(10)]],
                                     names=["as_of_date", "ticker"])
    panel = pd.DataFrame(index=idx)
    panel["decile"] = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5] * 2
    panel["fwd_ret_1m"] = [0.0, 0.0, 0, 0, 0, 0, 0, 0, 0.10, 0.10] * 2
    out = bucket_return_series(panel, n_buckets=5)
    assert "spread" in out.columns
    assert out["spread"].iloc[0] == pytest.approx(0.10)   # D5 (0.10) - D1 (0.0)


def test_thin_cross_section_forms_no_buckets():
    """A cross-section that cannot fill every bucket MIN_NAMES_PER_BUCKET
    deep is left unranked. The KOSPI panel averages ~29 scoreable names in
    2017, which across quintiles is ~6 per bucket — a 'bucket return' there
    is a few stocks' idiosyncratic noise, not a cross-sectional signal."""
    scores = pd.Series(np.arange(20, dtype=float), index=[f"T{i}" for i in range(20)])
    assert form_buckets(scores, n_buckets=5, min_per_bucket=5).isna().all()   # 20 < 25
    assert form_buckets(scores, n_buckets=5, min_per_bucket=4).notna().all()  # 20 >= 20


def test_min_per_bucket_rule_is_universe_agnostic():
    """The same rule gates both universes: 10 buckets need 50 names, 5 need
    25. It is a stated uniform threshold, not a per-market start date."""
    n = 60
    scores = pd.Series(np.arange(n, dtype=float), index=[f"T{i}" for i in range(n)])
    assert form_buckets(scores, n_buckets=10, min_per_bucket=5).notna().all()   # 60 >= 50
    assert form_buckets(scores, n_buckets=10, min_per_bucket=7).isna().all()    # 60 < 70
