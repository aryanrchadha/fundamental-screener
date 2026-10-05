"""Diagnostics the dashboard computes on top of the pipeline's artifacts.

Everything else in the dashboard only reads files. These functions are the
exception, and they are deliberately thin: bucket returns are rebuilt the
same way screener.backtest.bucket_return_series builds them (equal-weight
mean of fwd_ret_1m per bucket), and every statistic comes from
screener.validation's own newey_west_tstat / deflated_sharpe_ratio, so a
robustness number here and a number in the validation table cannot drift
apart through a second implementation.

What they answer are the questions FINDINGS.md had to answer by hand for
the Russell 3000 result: which names drove a given month's spread, and
whether a verdict survives winsorizing, dropping the largest months, or
excluding specific names.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from screener.universes import UNIVERSES, Universe
from screener.validation import deflated_sharpe_ratio, newey_west_tstat

COMPOSITE = "Composite (LASSO)"


# ---------------------------------------------------------------------------
# All runs at a glance
# ---------------------------------------------------------------------------

def run_overview(universes: dict[str, Universe] | None = None,
                 survivorship_supported=lambda name: name in ("sp500", "kospi")) -> pd.DataFrame:
    """One row per (universe, mode) that has a validation table on disk:
    the composite's verdict, plus whether that table is older than the
    backtest it summarizes."""
    universes = universes or UNIVERSES
    rows = []
    for name, base in universes.items():
        variants = [base] + ([base.corrected()] if survivorship_supported(name) else [])
        for uni in variants:
            path = Path(uni.validation_path)
            if not path.exists():
                continue
            v = pd.read_csv(path, index_col=0)
            if COMPOSITE not in v.index:
                continue
            c = v.loc[COMPOSITE]
            bt = Path(uni.bucket_returns_path)
            stale = bt.exists() and path.stat().st_mtime < bt.stat().st_mtime
            rows.append({
                "universe": name,
                "mode": "survivorship-corrected" if uni.survivorship_corrected else "static",
                "currency": uni.currency,
                "months": int(c["months"]),
                "ann_return": float(c["ann_return"]),
                "nw_tstat": float(c["nw_tstat"]),
                "dsr": float(c["dsr"]),
                "survives_95": bool(c["survives_95"]),
                "stale": bool(stale),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Month explorer
# ---------------------------------------------------------------------------

def month_buckets(panel: pd.DataFrame, date, n_buckets: int) -> dict:
    """Top and bottom bucket members for one rebalance date, each name's
    contribution to that month's spread, and mean-vs-median per bucket.

    A name's contribution is its forward return divided by its bucket's
    size (that is what equal weighting means), positive for the top bucket
    and negative for the bottom one, so the contributions sum to the
    spread exactly. A bucket whose mean sits far from its median is being
    carried by a few names.
    """
    date = pd.Timestamp(date)
    x = panel[(panel["as_of_date"] == date) & panel["decile"].notna() & panel["fwd_ret_1m"].notna()]
    out = {"date": date, "buckets": {}, "contributors": pd.DataFrame()}
    parts = []
    for label, b, sign in (("top", n_buckets, 1.0), ("bottom", 1, -1.0)):
        m = x[x["decile"] == b]
        if m.empty:
            continue
        out["buckets"][label] = {
            "bucket": f"D{b}", "names": len(m),
            "mean": float(m["fwd_ret_1m"].mean()), "median": float(m["fwd_ret_1m"].median()),
        }
        parts.append(pd.DataFrame({
            "ticker": m["ticker"].values, "sector": m["sector"].values,
            "bucket": f"D{b}", "fwd_ret_1m": m["fwd_ret_1m"].values,
            "contribution": sign * m["fwd_ret_1m"].values / len(m),
        }))
    if parts:
        c = pd.concat(parts, ignore_index=True)
        out["contributors"] = c.reindex(c["contribution"].abs().sort_values(ascending=False).index)
    b = out["buckets"]
    out["spread"] = b["top"]["mean"] - b["bottom"]["mean"] if {"top", "bottom"} <= set(b) else np.nan
    return out


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------

def spread_excluding(panel: pd.DataFrame, tickers, n_buckets: int, sectors=()) -> pd.Series:
    """Top-minus-bottom spread with `tickers` (and any names in `sectors`)
    removed from every bucket.

    Bucket assignments are kept as the backtest made them — removing a name
    does not re-rank the others — which is the question being asked: how
    much of the realized spread did these names account for?
    """
    drop = {t.strip().upper() for t in tickers if t and t.strip()}
    x = panel[panel["decile"].isin([1, n_buckets]) & panel["fwd_ret_1m"].notna()]
    if drop:
        x = x[~x["ticker"].str.upper().isin(drop)]
    if sectors:
        x = x[~x["sector"].isin(set(sectors))]
    means = x.groupby(["as_of_date", "decile"])["fwd_ret_1m"].mean().unstack()
    if n_buckets not in means or 1 not in means:
        return pd.Series(dtype=float)
    return (means[n_buckets] - means[1]).rename("spread")


def _stats(s: pd.Series) -> dict:
    s = s.dropna()
    if len(s) < 24:
        return {"months": len(s), "ann_return": np.nan, "nw_tstat": np.nan, "dsr": np.nan, "survives_95": False}
    t, mean_r, _ = newey_west_tstat(s)
    d = deflated_sharpe_ratio(s)
    return {"months": len(s), "ann_return": (1 + mean_r) ** 12 - 1, "nw_tstat": t,
            "dsr": d["dsr"], "survives_95": bool(d["dsr"] > 0.95)}


def robustness_table(spread: pd.Series, winsor_pct: float = 1.0, drop_top: int = 0,
                     drop_bottom: int = 0, excluded: pd.Series | None = None,
                     excluded_label: str = "") -> pd.DataFrame:
    """The composite spread's verdict under each perturbation, one per row,
    next to the baseline. Each row changes exactly one thing."""
    s = spread.dropna()
    rows = [("Baseline", _stats(s))]
    if winsor_pct > 0:
        lo, hi = s.quantile(winsor_pct / 100), s.quantile(1 - winsor_pct / 100)
        rows.append((f"Winsorized at {winsor_pct:g}/{100 - winsor_pct:g} pct", _stats(s.clip(lo, hi))))
    if drop_top > 0:
        top = s.nlargest(drop_top)
        months = ", ".join(f"{d:%Y-%m}" for d in sorted(top.index))
        rows.append((f"Drop {drop_top} largest month(s): {months}", _stats(s.drop(top.index))))
    if drop_bottom > 0:
        bot = s.nsmallest(drop_bottom)
        months = ", ".join(f"{d:%Y-%m}" for d in sorted(bot.index))
        rows.append((f"Drop {drop_bottom} smallest month(s): {months}", _stats(s.drop(bot.index))))
    if excluded is not None:
        rows.append((excluded_label or "Excluding names", _stats(excluded)))
    out = pd.DataFrame([{"scenario": k, **v} for k, v in rows])
    return out


def sector_attribution(panel: pd.DataFrame, n_buckets: int) -> pd.DataFrame:
    """Each sector's share of the composite spread over the whole sample.

    Per month, a sector contributes the sum of its top-bucket names'
    returns over the top bucket's size, minus the same for the bottom
    bucket — so sector contributions add up exactly to that month's
    spread. Reported as mean monthly contribution x 12 (arithmetic, so the
    column sums to the spread's arithmetic mean x 12, not to the
    compounded annual return in the validation table).
    """
    x = panel[panel["decile"].isin([1, n_buckets]) & panel["fwd_ret_1m"].notna()].copy()
    if x.empty:
        return pd.DataFrame(columns=["sector", "ann_contribution", "avg_top_names", "avg_bottom_names"])
    x["sector"] = x["sector"].fillna("Unknown")
    size = x.groupby(["as_of_date", "decile"])["ticker"].transform("size")
    x["contribution"] = np.where(x["decile"] == n_buckets, 1.0, -1.0) * x["fwd_ret_1m"] / size
    months = x["as_of_date"].nunique()
    per_month = x.groupby(["as_of_date", "sector"])["contribution"].sum().unstack(fill_value=0.0)
    out = pd.DataFrame({
        "ann_contribution": per_month.sum() / months * 12,
        "avg_top_names": x[x["decile"] == n_buckets].groupby("sector").size() / months,
        "avg_bottom_names": x[x["decile"] == 1].groupby("sector").size() / months,
    }).fillna(0.0)
    out.index.name = "sector"
    return out.sort_values("ann_contribution").reset_index()


# ---------------------------------------------------------------------------
# Run comparison
# ---------------------------------------------------------------------------

def available_runs(universes: dict[str, Universe] | None = None,
                   survivorship_supported=lambda name: name in ("sp500", "kospi")) -> list[dict]:
    """Every (universe, mode) with a bucket-return series on disk."""
    universes = universes or UNIVERSES
    runs = []
    for name, base in universes.items():
        for uni in [base] + ([base.corrected()] if survivorship_supported(name) else []):
            if not Path(uni.bucket_returns_path).exists():
                continue
            mode = "corrected" if uni.survivorship_corrected else "static"
            label = f"{name} ({mode}, {uni.currency})" + ("" if uni.backtestable else " — descriptive")
            runs.append({"key": f"{name}|{mode}", "label": label, "universe": uni})
    return runs


def cumulative_spreads(runs: list[dict]) -> dict[str, pd.Series]:
    """Compounded composite spread per run, each from its own first month.
    Local-currency returns: compare shapes and timing across markets, not
    levels (see FINDINGS.md on currency)."""
    out = {}
    for r in runs:
        d = pd.read_parquet(r["universe"].bucket_returns_path)
        if "spread" in d:
            s = d["spread"].dropna()
            out[r["label"]] = (1 + s).cumprod() - 1
    return out
