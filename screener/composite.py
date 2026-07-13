"""LASSO composite: blend the three sector-neutral scores into one ranking.

Training label: forward 6-month cross-sectionally-demeaned return. This is
the coefficient-FITTING label only — it tells the blend how much weight each
input deserved historically; it is not itself a tradable signal. Leakage
discipline:

  * At each annual refit date t, the training set contains only cross-
    sections whose ENTIRE forward-return window ended before t (as_of_date
    <= t - 7 months for a 6-month label). Coefficients are then applied
    forward until the next refit. Never fit once on the full sample.
  * Alpha selection uses TimeSeriesSplit — ordinary KFold would put future
    cross-sections in the training folds of past ones. make_cv() is the
    single place the splitter is constructed, and tests assert its type.

Before enough labeled history exists (MIN_TRAIN_MONTHS), the composite falls
back to an equal-weight average of the three z-scores — a sensible prior
that uses no forward information at all.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.linear_model import LassoCV
from sklearn.model_selection import TimeSeriesSplit

import config

log = logging.getLogger(__name__)

FEATURES = ["f_score_z", "z_score_z", "o_score_z"]


def make_cv(n_splits: int = config.LASSO_CV_SPLITS) -> TimeSeriesSplit:
    """The one and only CV splitter used for alpha selection.

    Must be TimeSeriesSplit (never KFold): rows are ordered by as_of_date, so
    expanding-window splits keep every validation fold strictly after its
    training fold.
    """
    return TimeSeriesSplit(n_splits=n_splits)


def fit_lasso(train: pd.DataFrame) -> LassoCV:
    """Fit LassoCV on time-ordered training rows (features -> demeaned fwd ret)."""
    train = train.sort_index(level="as_of_date")
    X = train[FEATURES].to_numpy()
    y = train["fwd_ret_demeaned"].to_numpy()
    model = LassoCV(alphas=config.LASSO_ALPHAS, cv=make_cv(), max_iter=50_000)
    model.fit(X, y)
    return model


def compute_composite(panel: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Walk-forward composite scores for a labeled panel.

    `panel` is indexed by (as_of_date, ticker) with columns FEATURES and
    `fwd_ret_demeaned` (NaN where the forward window hasn't finished — those
    rows still get SCORED, they just can't be trained on yet).

    Returns (composite_score Series aligned to panel.index, coefficient
    history DataFrame indexed by refit date).
    """
    original_index = panel.index
    panel = panel.sort_index(level="as_of_date")
    dates = panel.index.get_level_values("as_of_date").unique().sort_values()
    label_lag = pd.DateOffset(months=config.FORWARD_RETURN_MONTHS + 1)

    # Annual refit dates: first date, then every 12 months.
    refit_dates = list(dates[:: 12]) if len(dates) else []
    scores = pd.Series(np.nan, index=panel.index, name="composite_score")
    coef_rows = []

    current_model: LassoCV | None = None
    next_refit_idx = 0
    for d in dates:
        while next_refit_idx < len(refit_dates) and d >= refit_dates[next_refit_idx]:
            cutoff = pd.Timestamp(d) - label_lag
            train = panel[
                (panel.index.get_level_values("as_of_date") <= cutoff)
                & panel["fwd_ret_demeaned"].notna()
                & panel[FEATURES].notna().all(axis=1)
            ]
            n_months = train.index.get_level_values("as_of_date").nunique()
            if n_months >= config.MIN_TRAIN_MONTHS:
                current_model = fit_lasso(train)
                coef_rows.append(
                    {"refit_date": d, "alpha": current_model.alpha_,
                     **dict(zip(FEATURES, current_model.coef_))}
                )
                log.info("Refit LASSO at %s on %d months: coefs=%s alpha=%.4g",
                         d, n_months, np.round(current_model.coef_, 4), current_model.alpha_)
            else:
                log.info("Refit at %s skipped: only %d labeled months (< %d) — "
                         "equal-weight fallback in effect", d, n_months, config.MIN_TRAIN_MONTHS)
            next_refit_idx += 1

        xsec = panel.loc[d]
        feats = xsec[FEATURES]
        # If the LASSO shrank every coefficient to zero, its prediction is a
        # constant and decile ranks would be arbitrary tie-breaking noise.
        # Fall back to the equal-weight prior instead: "no evidence on
        # weights" should mean the neutral blend, not a random portfolio.
        if current_model is not None and not np.any(current_model.coef_):
            current_model = None
        if current_model is not None:
            s = pd.Series(current_model.predict(feats.fillna(0).to_numpy()), index=feats.index)
            s[feats.isna().any(axis=1)] = np.nan  # never score on imputed inputs
        else:
            # Equal-weight prior: mean of the three z-scores (all "higher =
            # better" after normalize.py's sign flip). Requires all three.
            s = feats.mean(axis=1).where(feats.notna().all(axis=1))
        scores.loc[pd.IndexSlice[d, :]] = s.to_numpy()

    coefs = pd.DataFrame(coef_rows).set_index("refit_date") if coef_rows else pd.DataFrame(
        columns=["alpha", *FEATURES]
    )
    return scores.reindex(original_index), coefs
