"""Classical fundamental scores: Piotroski F, Altman Z, Ohlson O.

Each scorer is a PURE FUNCTION over PIT snapshot DataFrames (one row per
ticker, columns = raw XBRL tags) and returns (score Series, valid mask
Series). Companies missing required inputs get NaN and mask=False — we log
how many were excluded and never impute a plug value.

Sign conventions: F higher=better, Z higher=safer, O higher=WORSE (it is a
bankruptcy-probability logit). The sign flip happens in normalize.py so all
three z-scored inputs read "higher = better" before the composite.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# De minimis threshold for Piotroski criterion 7 (no new equity issuance):
# routine stock-comp drift inflates share counts ~1-2%/yr at almost every
# large-cap; penalizing that would turn the criterion into noise. A 2% cap
# keeps the spirit ("no material equity raises") without that noise.
SHARE_ISSUANCE_TOLERANCE = 0.02


def _coalesce(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    """First non-null across candidate tag columns (tag fallbacks)."""
    out = pd.Series(np.nan, index=df.index, dtype=float)
    for c in cols:
        if c in df.columns:
            out = out.fillna(df[c])
    return out


def revenues(df: pd.DataFrame) -> pd.Series:
    return _coalesce(df, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"])


def gross_profit(df: pd.DataFrame) -> pd.Series:
    """GrossProfit tag if present, else Revenues - CostOfRevenue."""
    gp = _coalesce(df, ["GrossProfit"])
    rev = revenues(df)
    cogs = _coalesce(df, ["CostOfRevenue", "CostOfGoodsAndServicesSold"])
    return gp.fillna(rev - cogs)


def shares_outstanding(df: pd.DataFrame) -> pd.Series:
    return _coalesce(
        df,
        ["EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding",
         "WeightedAverageNumberOfSharesOutstandingBasic"],
    )


def _safe_div(a: pd.Series, b: pd.Series) -> pd.Series:
    return a / b.where(b != 0)


def total_liabilities(df: pd.DataFrame) -> pd.Series:
    """Liabilities tag, falling back to the accounting identity
    Assets - StockholdersEquity. Many filers tag only
    LiabilitiesAndStockholdersEquity, leaving `Liabilities` empty. The
    identity fallback is an exact restatement of the balance sheet — not an
    imputation — with one caveat: StockholdersEquity excludes noncontrolling
    interests, so NCI lands in 'liabilities' for consolidated groups. That
    biases leverage ratios slightly UP (conservative for Z and O)."""
    tl = _coalesce(df, ["Liabilities"])
    if "StockholdersEquity" in df.columns and "Assets" in df.columns:
        tl = tl.fillna(df["Assets"] - df["StockholdersEquity"])
    return tl


def piotroski_f(curr: pd.DataFrame, prior: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Piotroski (2000) F-Score: sum of 9 binary criteria, 0-9.

    `curr` and `prior` are PIT snapshots taken as-of the same date with
    annual_offset 0 and 1 — i.e., this year's and last year's annual
    statements as they were publicly known on the snapshot date.
    """
    prior = prior.reindex(curr.index)
    roa = _safe_div(curr["NetIncomeLoss"], curr["Assets"])
    roa_prior = _safe_div(prior["NetIncomeLoss"], prior["Assets"])
    cfo = curr["NetCashProvidedByUsedInOperatingActivities"]
    lev = _safe_div(curr["LongTermDebtNoncurrent"], curr["Assets"])
    lev_prior = _safe_div(prior["LongTermDebtNoncurrent"], prior["Assets"])
    cr = _safe_div(curr["AssetsCurrent"], curr["LiabilitiesCurrent"])
    cr_prior = _safe_div(prior["AssetsCurrent"], prior["LiabilitiesCurrent"])
    sh = shares_outstanding(curr)
    sh_prior = shares_outstanding(prior)
    gm = _safe_div(gross_profit(curr), revenues(curr))
    gm_prior = _safe_div(gross_profit(prior), revenues(prior))
    at = _safe_div(revenues(curr), curr["Assets"])
    at_prior = _safe_div(revenues(prior), prior["Assets"])

    criteria = pd.DataFrame(
        {
            "roa_pos": roa > 0,
            "cfo_pos": cfo > 0,
            "droa_pos": roa > roa_prior,
            "accruals": cfo > curr["NetIncomeLoss"],
            # Missing LongTermDebtNoncurrent usually means no LT debt is
            # tagged — treat absent-both-years as "no increase" (True) only
            # when Assets exist; absent one year only is indeterminate (NaN).
            "dlev_neg": (lev.fillna(0) <= lev_prior.fillna(0))
                        .where(~(lev.isna() ^ lev_prior.isna())),
            "dcr_pos": cr > cr_prior,
            "no_dilution": sh <= sh_prior * (1 + SHARE_ISSUANCE_TOLERANCE),
            "dgm_pos": gm > gm_prior,
            "dat_pos": at > at_prior,
        }
    )
    # A criterion comparing NaNs evaluates False in pandas; distinguish
    # "failed the test" from "couldn't compute" via the inputs' nullity.
    inputs_ok = pd.DataFrame(
        {
            "roa_pos": roa.notna(),
            "cfo_pos": cfo.notna(),
            "droa_pos": roa.notna() & roa_prior.notna(),
            "accruals": cfo.notna() & curr["NetIncomeLoss"].notna(),
            "dlev_neg": curr["Assets"].notna() & prior["Assets"].notna()
                        & ~(lev.isna() ^ lev_prior.isna()),
            "dcr_pos": cr.notna() & cr_prior.notna(),
            "no_dilution": sh.notna() & sh_prior.notna(),
            "dgm_pos": gm.notna() & gm_prior.notna(),
            "dat_pos": at.notna() & at_prior.notna(),
        }
    )
    valid = inputs_ok.all(axis=1)
    score = criteria.where(inputs_ok).sum(axis=1).where(valid)
    n_dropped = int((~valid).sum())
    if n_dropped:
        log.info("Piotroski: excluded %d/%d names for missing inputs", n_dropped, len(curr))
    return score.astype(float), valid


def altman_z(curr: pd.DataFrame, market_cap: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Altman (1968) Z-Score with the original public-company coefficients.

    Z = 1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*MktCap/TL + 1.0*Sales/TA

    EBIT: uses a directly-tagged 'EBIT' canonical fact when the source
    taxonomy provides one (e.g. Brazil's CVM DRE code 3.05, "Resultado Antes
    do Resultado Financeiro e dos Tributos" — a real EBIT line, not an
    approximation). US-GAAP filers have no such tag, so for them EBIT falls
    back to NetIncomeLoss plus tax and interest add-backs where those tags
    are filed (adding back only what IS available when one is missing).
    CAVEAT: the fallback understates EBIT for taxpaying levered firms — a
    documented approximation, deliberately preferred over fabricating a tax
    rate, and only used when no direct EBIT fact exists.
    """
    ta = curr["Assets"]
    wc = curr["AssetsCurrent"] - curr["LiabilitiesCurrent"]
    re_ = curr["RetainedEarningsAccumulatedDeficit"]
    ebit_approx = (
        curr["NetIncomeLoss"]
        + _coalesce(curr, ["IncomeTaxExpenseBenefit"]).fillna(0)
        + _coalesce(curr, ["InterestExpense"]).fillna(0)
    )
    ebit = _coalesce(curr, ["EBIT"]).fillna(ebit_approx) if "EBIT" in curr.columns else ebit_approx
    tl = total_liabilities(curr)
    sales = revenues(curr)
    mc = market_cap.reindex(curr.index)

    z = (
        1.2 * _safe_div(wc, ta)
        + 1.4 * _safe_div(re_, ta)
        + 3.3 * _safe_div(ebit, ta)
        + 0.6 * _safe_div(mc, tl)
        + 1.0 * _safe_div(sales, ta)
    )
    valid = z.notna()
    n_dropped = int((~valid).sum())
    if n_dropped:
        log.info("Altman: excluded %d/%d names for missing inputs", n_dropped, len(curr))
    return z.astype(float), valid


def ohlson_o(curr: pd.DataFrame, prior: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Ohlson (1980, J. Accounting Research) O-Score, Model 1 coefficients.

    This is the textbook published coefficient set, NOT a refit — refitting
    properly requires an actual default-event training sample, which is out
    of scope here (that refit is Project 21 in the broader portfolio).

    SIZE is log(total assets); Ohlson deflated by the GNP price-level index,
    which we omit (documented simplification — it is a monotone cross-
    sectional shift at each date and we only use O cross-sectionally).
    FFO is proxied by cash flow from operations (funds-from-operations is a
    pre-FASB-95 concept with no XBRL tag). Higher O = higher distress odds.
    """
    prior = prior.reindex(curr.index)
    ta = curr["Assets"]
    tl = total_liabilities(curr)
    wc = curr["AssetsCurrent"] - curr["LiabilitiesCurrent"]
    ni = curr["NetIncomeLoss"]
    ni_prior = prior["NetIncomeLoss"]
    ffo = curr["NetCashProvidedByUsedInOperatingActivities"]

    size = np.log(ta.where(ta > 0))
    tlta = _safe_div(tl, ta)
    wcta = _safe_div(wc, ta)
    clca = _safe_div(curr["LiabilitiesCurrent"], curr["AssetsCurrent"])
    oeneg = (tl > ta).astype(float)
    nita = _safe_div(ni, ta)
    futl = _safe_div(ffo, tl)
    intwo = ((ni < 0) & (ni_prior < 0)).astype(float)
    denom = ni.abs() + ni_prior.abs()
    chin = _safe_div(ni - ni_prior, denom)

    o = (
        -1.32
        - 0.407 * size
        + 6.03 * tlta
        - 1.43 * wcta
        + 0.0757 * clca
        - 1.72 * oeneg
        - 2.37 * nita
        - 1.83 * futl
        + 0.285 * intwo
        - 0.521 * chin
    )
    valid = o.notna()
    n_dropped = int((~valid).sum())
    if n_dropped:
        log.info("Ohlson: excluded %d/%d names for missing inputs", n_dropped, len(curr))
    return o.astype(float), valid
