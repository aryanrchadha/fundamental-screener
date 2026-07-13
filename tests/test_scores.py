"""Known-input/known-output tests for the three score implementations.

Fixtures are hand-constructed synthetic company-years with expected values
computed by hand — proving the formulas independent of real-data quirks.
"""

import numpy as np
import pandas as pd
import pytest

from screener import scores


def make_snapshot(rows: dict[str, dict]) -> pd.DataFrame:
    return pd.DataFrame.from_dict(rows, orient="index")


# --- Fixture 1: "GOODCO" — improves on every Piotroski dimension -----------
GOODCO_CURR = dict(
    NetIncomeLoss=120.0, Assets=1000.0, Liabilities=400.0,
    AssetsCurrent=300.0, LiabilitiesCurrent=100.0,
    NetCashProvidedByUsedInOperatingActivities=150.0,
    CommonStockSharesOutstanding=100.0,
    Revenues=800.0, GrossProfit=400.0,
    RetainedEarningsAccumulatedDeficit=500.0, StockholdersEquity=600.0,
    LongTermDebtNoncurrent=100.0,
    IncomeTaxExpenseBenefit=30.0, InterestExpense=10.0,
)
GOODCO_PRIOR = dict(
    NetIncomeLoss=80.0, Assets=950.0, Liabilities=450.0,
    AssetsCurrent=250.0, LiabilitiesCurrent=110.0,
    NetCashProvidedByUsedInOperatingActivities=90.0,
    CommonStockSharesOutstanding=100.0,
    Revenues=700.0, GrossProfit=320.0,
    RetainedEarningsAccumulatedDeficit=420.0, StockholdersEquity=520.0,
    LongTermDebtNoncurrent=150.0,
)
# Hand check: ROA .12>0 ✓, CFO 150>0 ✓, ΔROA .12>.0842 ✓, CFO>NI ✓,
# lev .10<.1579 ✓, CR 3.0>2.2727 ✓, shares flat ✓, GM .5>.4571 ✓,
# AT .8>.7368 ✓  →  F = 9

# --- Fixture 2: "BADCO" — fails everything it can fail ----------------------
BADCO_CURR = dict(
    NetIncomeLoss=-50.0, Assets=1000.0, Liabilities=1100.0,
    AssetsCurrent=100.0, LiabilitiesCurrent=200.0,
    NetCashProvidedByUsedInOperatingActivities=-60.0,
    CommonStockSharesOutstanding=150.0,
    Revenues=400.0, GrossProfit=80.0,
    RetainedEarningsAccumulatedDeficit=-300.0, StockholdersEquity=-100.0,
    LongTermDebtNoncurrent=500.0,
    IncomeTaxExpenseBenefit=0.0, InterestExpense=40.0,
)
BADCO_PRIOR = dict(
    NetIncomeLoss=-10.0, Assets=1100.0, Liabilities=1000.0,
    AssetsCurrent=150.0, LiabilitiesCurrent=180.0,
    NetCashProvidedByUsedInOperatingActivities=-5.0,
    CommonStockSharesOutstanding=100.0,
    Revenues=500.0, GrossProfit=120.0,
    RetainedEarningsAccumulatedDeficit=-250.0, StockholdersEquity=100.0,
    LongTermDebtNoncurrent=400.0,
)
# Hand check: ROA -0.05<0 ✗, CFO<0 ✗, ΔROA -.05 < -.00909 ✗, CFO(-60)<NI(-50) ✗,
# lev .5 > .3636 ✗, CR .5 < .8333 ✗, shares +50% ✗, GM .2<.24 ✗,
# AT .4 < .4545 ✗  →  F = 0


def test_piotroski_known_values():
    curr = make_snapshot({"GOODCO": GOODCO_CURR, "BADCO": BADCO_CURR})
    prior = make_snapshot({"GOODCO": GOODCO_PRIOR, "BADCO": BADCO_PRIOR})
    f, valid = scores.piotroski_f(curr, prior)
    assert valid.all()
    assert f["GOODCO"] == 9.0
    assert f["BADCO"] == 0.0


def test_piotroski_missing_input_excluded():
    curr_missing = dict(GOODCO_CURR)
    curr_missing["NetCashProvidedByUsedInOperatingActivities"] = np.nan
    curr = make_snapshot({"GOODCO": GOODCO_CURR, "MISSCO": curr_missing})
    prior = make_snapshot({"GOODCO": GOODCO_PRIOR, "MISSCO": GOODCO_PRIOR})
    f, valid = scores.piotroski_f(curr, prior)
    assert not valid["MISSCO"]
    assert np.isnan(f["MISSCO"])       # excluded, never imputed
    assert f["GOODCO"] == 9.0          # others unaffected


def test_altman_known_value():
    curr = make_snapshot({"GOODCO": GOODCO_CURR})
    mktcap = pd.Series({"GOODCO": 2000.0})
    z, valid = scores.altman_z(curr, mktcap)
    # WC/TA=200/1000=.2, RE/TA=.5, EBIT=(120+30+10)/1000=.16,
    # MC/TL=2000/400=5, S/TA=.8
    expected = 1.2 * 0.2 + 1.4 * 0.5 + 3.3 * 0.16 + 0.6 * 5.0 + 1.0 * 0.8
    assert valid["GOODCO"]
    assert z["GOODCO"] == pytest.approx(expected)  # = 5.268


def test_altman_ebit_fallback_without_tax_interest_tags():
    curr_row = {k: v for k, v in GOODCO_CURR.items()
                if k not in ("IncomeTaxExpenseBenefit", "InterestExpense")}
    curr = make_snapshot({"GOODCO": curr_row})
    z, valid = scores.altman_z(curr, pd.Series({"GOODCO": 2000.0}))
    expected = 1.2 * 0.2 + 1.4 * 0.5 + 3.3 * 0.12 + 0.6 * 5.0 + 1.0 * 0.8
    assert z["GOODCO"] == pytest.approx(expected)


def test_altman_prefers_direct_ebit_tag_over_approximation():
    """Non-US taxonomies (e.g. CVM Brazil) can supply a directly-tagged EBIT
    fact; it must be used in place of the NI+tax+interest approximation,
    even when tax/interest tags are ALSO present (the direct tag is more
    accurate, so it should win, not just fill a gap)."""
    curr_row = dict(GOODCO_CURR)
    curr_row["EBIT"] = 200.0  # deliberately different from the 160.0 approximation
    curr = make_snapshot({"GOODCO": curr_row})
    z, valid = scores.altman_z(curr, pd.Series({"GOODCO": 2000.0}))
    expected = 1.2 * 0.2 + 1.4 * 0.5 + 3.3 * (200.0 / 1000.0) + 0.6 * 5.0 + 1.0 * 0.8
    assert z["GOODCO"] == pytest.approx(expected)


def test_ohlson_known_value():
    curr = make_snapshot({"BADCO": BADCO_CURR})
    prior = make_snapshot({"BADCO": BADCO_PRIOR})
    o, valid = scores.ohlson_o(curr, prior)
    ta, tl = 1000.0, 1100.0
    size = np.log(ta)
    expected = (
        -1.32
        - 0.407 * size
        + 6.03 * (tl / ta)
        - 1.43 * ((100.0 - 200.0) / ta)
        + 0.0757 * (200.0 / 100.0)
        - 1.72 * 1.0                                  # TL > TA
        - 2.37 * (-50.0 / ta)
        - 1.83 * (-60.0 / tl)
        + 0.285 * 1.0                                 # losses both years
        - 0.521 * ((-50.0 - -10.0) / (50.0 + 10.0))
    )
    assert valid["BADCO"]
    assert o["BADCO"] == pytest.approx(expected)


def test_gross_profit_fallback_from_cogs():
    df = make_snapshot({"X": dict(Revenues=100.0, CostOfRevenue=60.0)})
    assert scores.gross_profit(df)["X"] == pytest.approx(40.0)
