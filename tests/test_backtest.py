"""Backtest mechanics: PIT-universe exclusion (survivorship correction) and
decile formation."""

from datetime import date

import numpy as np
import pandas as pd

from screener.backtest import filter_universe, form_deciles
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


def test_form_deciles_assignment():
    scores = pd.Series(np.arange(100, dtype=float), index=[f"T{i}" for i in range(100)])
    dec = form_deciles(scores, n_deciles=10)
    assert dec["T0"] == 1          # worst score -> decile 1
    assert dec["T99"] == 10        # best score -> decile 10
    assert dec.value_counts().eq(10).all()


def test_form_deciles_handles_nans_and_small_sections():
    scores = pd.Series([1.0, 2.0, np.nan], index=list("ABC"))
    dec = form_deciles(scores, n_deciles=10)  # too few valid names
    assert dec.isna().all()
