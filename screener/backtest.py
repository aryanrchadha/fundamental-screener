"""Bucket backtest: monthly rebalance on the composite, equal-weight buckets.

Run the whole pipeline with:
    python -m screener.backtest                    # S&P 500 (deciles)
    python -m screener.backtest --universe kospi   # KOSPI 120 (quintiles)

At each month-end rebalance date the pipeline:
  1. Builds current + prior-year PIT snapshots (filing-date gated — a March
     snapshot can only see annual reports already filed by that date).
  2. Computes F/Z/O, sector-neutral z-scores, and the walk-forward LASSO
     composite.
  3. Ranks the cross-section into N buckets (1 = worst composite, N = best),
     optionally restricted to point-in-time index constituents.
  4. Holds each equal-weight bucket for one month; forward returns come from
     Yahoo month-end closes in the listing currency.

The bucket count is a property of the universe, not a constant: 10 for the
~500-name S&P 500, 5 for the 120-name KOSPI set, where deciles would leave
~7 names per bucket and the "decile return" would be dominated by a handful
of stocks' idiosyncratic moves. See screener/universes.py.

Column names stay `D1..DN` and `spread = top - bottom` for both universes,
so validation.py and the dashboard need no per-market special-casing.

Outputs are written to the universe's own paths in data/ (scores panel,
bucket return series, LASSO coefficient history).
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
from screener.universe import was_member
from screener.universes import Universe, get_universe

log = logging.getLogger(__name__)


def filter_universe(on_date, tickers: list[str], membership: pd.DataFrame | None) -> list[str]:
    """Restrict `tickers` to index members on `on_date` when a membership
    table is provided (survivorship-bias-corrected mode); pass-through
    otherwise."""
    if membership is None:
        return tickers
    return [t for t in tickers if was_member(t, on_date, membership)]


def form_buckets(
    composite_scores: pd.Series,
    n_buckets: int = config.N_DECILES,
    min_per_bucket: int = config.MIN_NAMES_PER_BUCKET,
) -> pd.Series:
    """Bucket assignment 1..n (1 = worst score) for one cross-section.

    A cross-section too thin to fill every bucket `min_per_bucket` deep is
    left entirely unassigned, rather than forming buckets of one or two
    names whose "return" is idiosyncratic noise. See MIN_NAMES_PER_BUCKET."""
    valid = composite_scores.dropna()
    if len(valid) < n_buckets * min_per_bucket:
        return pd.Series(np.nan, index=composite_scores.index)
    ranks = valid.rank(method="first")
    buckets = pd.qcut(ranks, n_buckets, labels=range(1, n_buckets + 1)).astype(float)
    return buckets.reindex(composite_scores.index)


# Back-compat alias: the S&P 500 path and its tests call these deciles.
form_deciles = form_buckets


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


def bucket_return_series(panel: pd.DataFrame, n_buckets: int = config.N_DECILES) -> pd.DataFrame:
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
    # `spread` is always top-minus-bottom bucket, whatever N is, so every
    # downstream consumer (validation, dashboard) is universe-agnostic.
    top, bottom = f"D{n_buckets}", "D1"
    if top in out and bottom in out:
        out["spread"] = out[top] - out[bottom]
    return out


decile_return_series = bucket_return_series  # back-compat alias


def run_pipeline(universe: Universe | str = "sp500", db_path=None) -> dict[str, pd.DataFrame]:
    """Run the full scoring + bucket backtest for one universe.

    `db_path` overrides the universe's own PIT database (used by tests);
    everything else — tickers, sectors, price symbols, bucket count, output
    paths — comes from the Universe so no market is special-cased here.
    """
    if isinstance(universe, str):
        universe = get_universe(universe)
    db_path = db_path or universe.db_path

    tickers = universe.tickers()
    sectors = universe.sectors()
    membership = universe.membership()

    prices = get_monthly_prices(
        tickers, start=universe.start, end=universe.end,
        cache_path=universe.prices_cache,
        symbol_suffix=universe.price_symbol_suffix,
    )
    tickers = [t for t in tickers if t in prices.columns and prices[t].notna().any()]
    log.info("%s: %d tickers with price history, %d buckets, %s",
             universe.name, len(tickers), universe.n_buckets, universe.currency)

    rebalance_dates = pd.date_range(universe.start, universe.end, freq=config.REBALANCE_FREQ)
    rebalance_dates = rebalance_dates[rebalance_dates <= prices.index.max()]

    panel = build_scores_panel(rebalance_dates, tickers, sectors, prices,
                               membership=membership, db_path=db_path)
    comp, coefs = composite_mod.compute_composite(panel)
    panel["composite_score"] = comp
    panel["decile"] = panel.groupby(level="as_of_date")["composite_score"].transform(
        lambda s: form_buckets(s, universe.n_buckets)
    )

    dec_rets = bucket_return_series(panel, universe.n_buckets)

    panel.reset_index().to_parquet(universe.panel_path)
    dec_rets.to_parquet(universe.bucket_returns_path)
    coefs.to_parquet(universe.coefs_path)
    log.info("Saved panel (%d rows), bucket returns (%d months), coefs (%d refits)",
             len(panel), len(dec_rets), len(coefs))
    return {"panel": panel, "decile_returns": dec_rets, "coefs": coefs, "universe": universe}


def main() -> None:
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Run the bucket backtest for one universe")
    p.add_argument("--universe", default="sp500", choices=["sp500", "kospi"])
    args = p.parse_args()

    out = run_pipeline(args.universe)
    uni = out["universe"]
    dec = out["decile_returns"].dropna(subset=["spread"])
    full = (1 + dec["spread"]).prod() - 1
    half = len(dec) // 2
    first = (1 + dec["spread"].iloc[:half]).prod() - 1
    second = (1 + dec["spread"].iloc[half:]).prod() - 1
    label = f"D{uni.n_buckets} - D1"
    print(f"\n=== {uni.name} bucket backtest ({label}, equal weight, monthly, {uni.currency}) ===")
    print(f"Months: {len(dec)}   Full-period cumulative spread: {full:+.1%}")
    print(f"First half: {first:+.1%}   Second half: {second:+.1%}")
    print(f"Run `python -m screener.validation --universe {uni.name}` for Newey-West / DSR statistics.")


if __name__ == "__main__":
    main()
