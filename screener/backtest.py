"""Decile backtest: monthly rebalance on the composite, equal-weight deciles.

Run the whole pipeline with:  python -m screener.backtest

At each month-end rebalance date the pipeline:
  1. Builds current + prior-year PIT snapshots (filing-date gated — a March
     snapshot can only see 10-Ks already filed by that date).
  2. Computes F/Z/O, sector-neutral z-scores, and the walk-forward LASSO
     composite.
  3. Ranks the cross-section into deciles (1 = worst composite, 10 = best),
     optionally restricted to point-in-time index constituents.
  4. Holds each equal-weight decile for one month; forward returns come from
     Yahoo month-end closes.

Outputs are written to data/ (scores panel, decile return series, LASSO
coefficient history) for validation.py and the dashboard to consume.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config
from pit_fundamentals.query import build_pit_snapshot
from screener import composite as composite_mod
from screener import normalize, scores as scores_mod
from screener.prices import get_monthly_prices, monthly_returns
from screener.universe import build_membership, get_sp500_constituents, get_sectors, was_member

log = logging.getLogger(__name__)


def filter_universe(on_date, tickers: list[str], membership: pd.DataFrame | None) -> list[str]:
    """Restrict `tickers` to index members on `on_date` when a membership
    table is provided (survivorship-bias-corrected mode); pass-through
    otherwise."""
    if membership is None:
        return tickers
    return [t for t in tickers if was_member(t, on_date, membership)]


def form_deciles(composite_scores: pd.Series, n_deciles: int = config.N_DECILES) -> pd.Series:
    """Decile assignment 1..n (1 = worst score) for one cross-section."""
    valid = composite_scores.dropna()
    if len(valid) < n_deciles:
        return pd.Series(np.nan, index=composite_scores.index)
    ranks = valid.rank(method="first")
    deciles = pd.qcut(ranks, n_deciles, labels=range(1, n_deciles + 1)).astype(float)
    return deciles.reindex(composite_scores.index)


def build_scores_panel(
    rebalance_dates: pd.DatetimeIndex,
    tickers: list[str],
    sectors: pd.Series,
    prices: pd.DataFrame,
    membership: pd.DataFrame | None = None,
    db_path=config.DB_PATH,
) -> pd.DataFrame:
    """One row per (as_of_date, ticker): raw scores, z-scores, labels."""
    rets = monthly_returns(prices)
    fwd_h = config.FORWARD_RETURN_MONTHS
    frames = []
    for d in rebalance_dates:
        active = filter_universe(d.date(), tickers, membership)
        if not active:
            continue
        curr = build_pit_snapshot(d.date(), active, annual_offset=0, db_path=db_path)
        prior = build_pit_snapshot(d.date(), active, annual_offset=1, db_path=db_path)

        # PIT market cap: shares known as of d × latest month-end price <= d.
        # (Positional lookup, not DataFrame.asof — asof drops any row that
        # has a NaN in ANY column, so one delisted ticker would nuke all.)
        ploc = prices.index.searchsorted(d, side="right") - 1
        px = prices.iloc[ploc].reindex(active) if ploc >= 0 else pd.Series(np.nan, index=active)
        shares = scores_mod.shares_outstanding(curr)
        mktcap = shares * pd.Series(px, index=curr.index)

        f, _ = scores_mod.piotroski_f(curr, prior)
        z, _ = scores_mod.altman_z(curr, mktcap)
        o, _ = scores_mod.ohlson_o(curr, prior)
        raw = pd.DataFrame({"f_score": f, "z_score": z, "o_score": o})
        zs = normalize.sector_zscore(raw, sectors)

        # Forward returns: next-month (backtest holding return) and the
        # 6-month demeaned label used only for LASSO training.
        loc = rets.index.searchsorted(d)
        fwd_1m = rets.iloc[loc + 1].reindex(active) if loc + 1 < len(rets) else pd.Series(np.nan, index=active)
        if loc + fwd_h < len(prices):
            p0 = prices.iloc[loc].reindex(active)
            p1 = prices.iloc[loc + fwd_h].reindex(active)
            fwd_6m = p1 / p0 - 1
            fwd_demeaned = fwd_6m - fwd_6m.mean()
        else:
            fwd_demeaned = pd.Series(np.nan, index=active)

        block = pd.concat([raw, zs], axis=1)
        block["sector"] = sectors.reindex(block.index)
        block["fwd_ret_1m"] = fwd_1m.reindex(block.index)
        block["fwd_ret_demeaned"] = fwd_demeaned.reindex(block.index)
        block["as_of_date"] = d
        frames.append(block.reset_index().rename(columns={"index": "ticker"}))
        n_scored = int(raw.notna().all(axis=1).sum())
        log.info("%s: %d/%d names fully scored", d.date(), n_scored, len(active))
    panel = pd.concat(frames, ignore_index=True)
    return panel.set_index(["as_of_date", "ticker"]).sort_index()


def decile_return_series(panel: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight next-month return per decile per rebalance date, plus the
    decile-10-minus-decile-1 long-short spread."""
    rows = []
    for d, xsec in panel.groupby(level="as_of_date"):
        xsec = xsec.droplevel("as_of_date")
        row = {"date": d}
        for dec, members in xsec.groupby("decile"):
            row[f"D{int(dec)}"] = members["fwd_ret_1m"].mean()
        rows.append(row)
    out = pd.DataFrame(rows).set_index("date").sort_index()
    if "D10" in out and "D1" in out:
        out["spread"] = out["D10"] - out["D1"]
    return out


def run_pipeline(db_path=config.DB_PATH) -> dict[str, pd.DataFrame]:
    constituents = get_sp500_constituents()
    tickers = constituents["ticker"].tolist()
    sectors = get_sectors(tickers)
    membership = build_membership(constituents) if config.USE_PIT_UNIVERSE else None

    prices = get_monthly_prices(tickers)
    tickers = [t for t in tickers if t in prices.columns and prices[t].notna().any()]
    rebalance_dates = pd.date_range(config.BACKTEST_START, config.BACKTEST_END,
                                    freq=config.REBALANCE_FREQ)
    rebalance_dates = rebalance_dates[rebalance_dates <= prices.index.max()]

    panel = build_scores_panel(rebalance_dates, tickers, sectors, prices,
                               membership=membership, db_path=db_path)
    comp, coefs = composite_mod.compute_composite(panel)
    panel["composite_score"] = comp
    panel["decile"] = panel.groupby(level="as_of_date")["composite_score"].transform(form_deciles)

    dec_rets = decile_return_series(panel)

    panel.reset_index().to_parquet(config.SCORES_PANEL_PATH)
    dec_rets.to_parquet(config.DECILE_RETURNS_PATH)
    coefs.to_parquet(config.COEFS_PATH)
    log.info("Saved panel (%d rows), decile returns (%d months), coefs (%d refits)",
             len(panel), len(dec_rets), len(coefs))
    return {"panel": panel, "decile_returns": dec_rets, "coefs": coefs}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    out = run_pipeline()
    dec = out["decile_returns"].dropna(subset=["spread"])
    full = (1 + dec["spread"]).prod() - 1
    half = len(dec) // 2
    first = (1 + dec["spread"].iloc[:half]).prod() - 1
    second = (1 + dec["spread"].iloc[half:]).prod() - 1
    print("\n=== Decile backtest (D10 - D1, equal weight, monthly) ===")
    print(f"Months: {len(dec)}   Full-period cumulative spread: {full:+.1%}")
    print(f"First half: {first:+.1%}   Second half: {second:+.1%}")
    print("Run `python -m screener.validation` for Newey-West / DSR statistics.")


if __name__ == "__main__":
    main()
