"""Statistical validation: Newey-West t-stats and the Deflated Sharpe Ratio.

Run with:  python -m screener.validation   (after screener.backtest)

Two corrections applied to the decile-spread return series:

1. Newey-West HAC t-stat — monthly long-short returns are autocorrelated
   (overlapping information, momentum in the underlying names), so plain
   OLS standard errors overstate significance. Lag chosen by the standard
   rule floor(4*(T/100)^(2/9)), implemented explicitly.

2. Deflated Sharpe Ratio (Bailey & López de Prado 2014) — we effectively
   tried FOUR related strategies on the same data (F alone, Z alone, O
   alone, the composite), so the best observed Sharpe must clear a higher
   bar than a single pre-registered test. N_TRIALS = 4 is the honest count:
   not 1, because the three sub-scores were genuinely examined; not some
   arbitrary larger number, because nothing else was tried. Skewness and
   kurtosis enter from the EMPIRICAL return distribution — no normality
   assumption.
"""

from __future__ import annotations

import logging
import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats as sps

import config
from screener import normalize
from screener.backtest import decile_return_series, form_deciles

log = logging.getLogger(__name__)


def newey_west_lag(T: int) -> int:
    """Standard Newey-West lag rule: floor(4 * (T/100)^(2/9))."""
    return int(math.floor(4 * (T / 100.0) ** (2.0 / 9.0)))


def newey_west_tstat(returns: pd.Series) -> tuple[float, float, int]:
    """t-stat of the mean of `returns` with HAC (Newey-West) standard errors.

    Returns (t_stat, mean_monthly_return, lag_used).
    """
    r = returns.dropna()
    T = len(r)
    lag = newey_west_lag(T)
    X = np.ones((T, 1))
    model = sm.OLS(r.to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
    return float(model.tvalues[0]), float(model.params[0]), lag


def deflated_sharpe_ratio(
    returns: pd.Series,
    n_trials: int = config.N_DSR_TRIALS,
    variance_across_trials: float | None = None,
) -> dict:
    """Bailey & López de Prado (2014) Deflated Sharpe Ratio.

    DSR = P[true SR > 0] after deflating the observed (per-period) Sharpe by
    the expected maximum Sharpe of `n_trials` unskilled strategies:

        SR0 = sqrt(V[SR]) * ((1-g)*Z^{-1}(1-1/N) + g*Z^{-1}(1-1/(N*e)))
        DSR = Z( (SR_hat - SR0) * sqrt(T-1) / sqrt(1 - g3*SR_hat + (g4-1)/4*SR_hat^2) )

    where g is the Euler-Mascheroni constant, g3/g4 the EMPIRICAL skewness
    and (non-excess) kurtosis of the returns, and V[SR] the variance of the
    Sharpe estimates across the trials (estimated from the trials themselves
    when supplied, else via the asymptotic SR-estimator variance ~1/T).
    """
    r = returns.dropna().to_numpy()
    T = len(r)
    sr = r.mean() / r.std(ddof=1)  # per-period (monthly) Sharpe
    g3 = float(sps.skew(r))
    g4 = float(sps.kurtosis(r, fisher=False))  # non-excess kurtosis (normal = 3)

    if variance_across_trials is None:
        # Asymptotic variance of a Sharpe estimator (Lo 2002) as the spread
        # of the unskilled-trial Sharpes; a conservative default when the
        # cross-trial variance isn't measured directly.
        variance_across_trials = (1 - g3 * sr + (g4 - 1) / 4 * sr**2) / (T - 1)
    emc = 0.5772156649015329  # Euler-Mascheroni
    sd_trials = math.sqrt(max(variance_across_trials, 1e-12))
    z1 = sps.norm.ppf(1 - 1.0 / n_trials)
    z2 = sps.norm.ppf(1 - 1.0 / (n_trials * math.e))
    sr0 = sd_trials * ((1 - emc) * z1 + emc * z2)  # expected max SR under H0

    denom = math.sqrt(max(1 - g3 * sr + (g4 - 1) / 4 * sr**2, 1e-12))
    psr_stat = (sr - sr0) * math.sqrt(T - 1) / denom
    dsr = float(sps.norm.cdf(psr_stat))
    return {
        "sharpe_monthly": sr,
        "sharpe_annual": sr * math.sqrt(12),
        "skew": g3,
        "kurtosis": g4,
        "sr0_benchmark": sr0,
        "dsr": dsr,
        "p_value": 1 - dsr,
        "n_trials": n_trials,
        "T": T,
    }


def single_score_spreads(panel: pd.DataFrame) -> dict[str, pd.Series]:
    """D10-D1 spread series for each single sector-neutral score, built the
    same way as the composite's deciles (same universe, same months)."""
    out = {}
    for col, label in [("f_score_z", "F-Score"), ("z_score_z", "Z-Score"), ("o_score_z", "O-Score")]:
        p = panel.copy()
        p["decile"] = p.groupby(level="as_of_date")[col].transform(form_deciles)
        rets = decile_return_series(p)
        if "spread" in rets:
            out[label] = rets["spread"]
    return out


def rolling_spread(spread: pd.Series, window: int = config.ROLLING_WINDOW_MONTHS) -> pd.DataFrame:
    """Rolling annualized mean spread with a +/-1.96 SE band (per-window,
    HAC-free — the band is descriptive; formal inference is the NW/DSR
    table)."""
    mu = spread.rolling(window).mean() * 12
    se = spread.rolling(window).std(ddof=1) / np.sqrt(window) * 12
    return pd.DataFrame({"ann_spread": mu, "lo": mu - 1.96 * se, "hi": mu + 1.96 * se})


def build_summary(panel: pd.DataFrame, decile_rets: pd.DataFrame) -> pd.DataFrame:
    """One row per strategy (F, Z, O, composite): NW t-stat, Sharpe, DSR."""
    series = single_score_spreads(panel)
    series["Composite (LASSO)"] = decile_rets["spread"]
    rows = []
    for name, s in series.items():
        s = s.dropna()
        if len(s) < 24:
            log.warning("Skipping %s: only %d months of spread returns", name, len(s))
            continue
        t, mean_r, lag = newey_west_tstat(s)
        d = deflated_sharpe_ratio(s)
        rows.append(
            {
                "strategy": name,
                "months": len(s),
                "ann_return": (1 + mean_r) ** 12 - 1,
                "ann_sharpe": d["sharpe_annual"],
                "nw_tstat": t,
                "nw_lag": lag,
                "skew": d["skew"],
                "kurtosis": d["kurtosis"],
                "dsr": d["dsr"],
                "dsr_pvalue": d["p_value"],
                "survives_95": d["dsr"] > 0.95,
            }
        )
    return pd.DataFrame(rows).set_index("strategy")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    panel = pd.read_parquet(config.SCORES_PANEL_PATH).set_index(["as_of_date", "ticker"])
    dec = pd.read_parquet(config.DECILE_RETURNS_PATH)

    summary = build_summary(panel, dec)
    summary.to_csv(config.VALIDATION_SUMMARY_PATH)
    roll = rolling_spread(dec["spread"].dropna())
    roll.to_parquet(config.ROLLING_SPREAD_PATH)

    pd.set_option("display.width", 140)
    print("\n=== Validation summary (D10 - D1 monthly spreads) ===\n")
    print(summary.round(3).to_string())
    comp = summary.loc[["Composite (LASSO)"]] if "Composite (LASSO)" in summary.index else summary
    verdict = bool(comp["survives_95"].iloc[0]) if len(comp) else False
    print(
        "\nDeflated Sharpe verdict (N_trials=4, empirical skew/kurtosis): "
        + ("the composite's edge SURVIVES the multiple-testing correction at 95% confidence."
           if verdict else
           "the composite's edge DOES NOT survive the multiple-testing correction at 95% confidence.")
    )


if __name__ == "__main__":
    main()
