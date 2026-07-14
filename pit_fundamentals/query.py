"""Point-in-time query API — the reusable contract other projects call.

The invariant every function here enforces: a value is only visible on dates
on or after its `filed_date`. Restatements ARE visible once filed (an analyst
on that date would have seen them), but never before.

Flow facts (income/cash-flow items) are reported for durations; a fiscal-year
value has a ~365-day duration while a quarterly value has ~90. The snapshot
API works on ANNUAL data (Piotroski/Altman/Ohlson are annual-statement
models), so flow tags are filtered to durations >= MIN_ANNUAL_DAYS.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pit_fundamentals.schema import DEFAULT_DB_PATH, connect

# Tags measured over a period (require annual duration) vs. point-in-time
# balance-sheet/share-count tags (instant; no duration filter).
FLOW_TAGS = {
    "NetIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "GrossProfit",
    "CostOfRevenue",
    "CostOfGoodsAndServicesSold",
    "IncomeTaxExpenseBenefit",
    "InterestExpense",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "EBIT",  # only populated by taxonomies with a direct EBIT line (e.g. cvm-br); NaN for us-gaap
}
MIN_ANNUAL_DAYS = 300  # a fiscal year is ~365d; 300 excludes quarterly/semiannual frames

DEFAULT_TAGS = sorted(
    FLOW_TAGS
    | {
        "Assets",
        "Liabilities",
        "AssetsCurrent",
        "LiabilitiesCurrent",
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstanding",
        "RetainedEarningsAccumulatedDeficit",
        "StockholdersEquity",
        "LongTermDebtNoncurrent",
    }
)


def get_fact_as_of(
    ticker: str,
    tag: str,
    as_of_date: date,
    fiscal_period_end: date | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> float | None:
    """Return the value of `tag` for `ticker` that was PUBLICLY KNOWN as of
    `as_of_date`.

    Must only consider facts where filed_date <= as_of_date. If multiple
    filings exist for the same fiscal period, return the most recent one
    filed on or before as_of_date (i.e., restatements ARE visible once
    filed, but only after their own filing date — this correctly reflects
    that an analyst on that date would have seen the restatement).
    Returns None if nothing was known yet, rather than silently returning a
    future value.
    """
    con = connect(db_path, read_only=True)
    try:
        params: list = [ticker.upper(), tag, as_of_date]
        sql = """
            SELECT value FROM pit_facts
            WHERE ticker = ? AND tag = ? AND filed_date <= ?
        """
        if fiscal_period_end is not None:
            sql += " AND fiscal_period_end = ?"
            params.append(fiscal_period_end)
        # Latest fiscal period first, then latest filing for that period —
        # so a restatement supersedes the original from its filed_date onward.
        sql += " ORDER BY fiscal_period_end DESC, filed_date DESC LIMIT 1"
        row = con.execute(sql, params).fetchone()
        return None if row is None else float(row[0])
    finally:
        con.close()


def build_pit_snapshot(
    as_of_date: date,
    tickers: list[str],
    tags: list[str] | None = None,
    annual_offset: int = 0,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> pd.DataFrame:
    """Vectorized get_fact_as_of across all tracked tags for a ticker list.

    Returns one row per ticker with all facts as they stood on `as_of_date`.
    `annual_offset=0` gives each tag's most recent annual value known on that
    date; `annual_offset=1` gives the value one fiscal year earlier (also
    gated by filed_date <= as_of_date), which is what Piotroski's YoY deltas
    need. Missing facts are NaN — callers decide exclusion, we never impute.
    """
    tags = tags or DEFAULT_TAGS
    tickers_u = [t.upper() for t in tickers]
    con = connect(db_path, read_only=True)
    try:
        con.register("_tickers", pd.DataFrame({"ticker": tickers_u}))
        con.register("_tags", pd.DataFrame({"tag": list(tags)}))
        con.register("_flow_tags", pd.DataFrame({"tag": sorted(FLOW_TAGS)}))
        df = con.execute(
            f"""
            WITH visible AS (
                SELECT f.ticker, f.tag, f.fiscal_period_end, f.filed_date, f.value,
                       row_number() OVER (
                           PARTITION BY f.ticker, f.tag, f.fiscal_period_end
                           ORDER BY f.filed_date DESC
                       ) AS rn_filing
                FROM pit_facts f
                JOIN _tickers t USING (ticker)
                JOIN _tags g USING (tag)
                WHERE f.filed_date <= ?
                  AND (
                        -- flow tags: annual durations only
                        (f.tag IN (SELECT tag FROM _flow_tags)
                         AND f.start_date IS NOT NULL
                         AND date_diff('day', f.start_date, f.fiscal_period_end) >= {MIN_ANNUAL_DAYS})
                        -- instant (balance-sheet/share) tags: fiscal-YEAR-END
                        -- values only, so YoY deltas compare annual balance
                        -- sheets, not a 10-Q/quarterly filing against an
                        -- annual one. 'DFP' (Brazil/CVM) and 'DART-ANNUAL'
                        -- (South Korea) are each unambiguously annual by
                        -- construction — their respective quarterly forms
                        -- ('ITR', DART reprt_code 11012-11014) are separate
                        -- datasets this project's cvm_br_client.py and
                        -- dart_kr_client.py do not ingest.
                        OR (f.tag NOT IN (SELECT tag FROM _flow_tags)
                            AND (f.form LIKE '10-K%' OR f.form IN ('DFP', 'DART-ANNUAL')))
                      )
            ),
            latest_filing AS (
                SELECT * FROM visible WHERE rn_filing = 1
            ),
            ranked_periods AS (
                SELECT *, dense_rank() OVER (
                           PARTITION BY ticker, tag
                           ORDER BY fiscal_period_end DESC
                       ) AS rn_period
                FROM latest_filing
            )
            SELECT ticker, tag, value, fiscal_period_end
            FROM ranked_periods
            WHERE rn_period = ?
            """,
            [as_of_date, annual_offset + 1],
        ).df()
    finally:
        con.close()
    if df.empty:
        out = pd.DataFrame(index=pd.Index(tickers_u, name="ticker"), columns=list(tags), dtype=float)
        out["_fiscal_period_end"] = pd.NaT
        return out
    wide = df.pivot_table(index="ticker", columns="tag", values="value", aggfunc="first")
    wide = wide.reindex(index=tickers_u, columns=list(tags))
    # Reference fiscal period end (max across tags) kept for diagnostics.
    fpe = df.groupby("ticker")["fiscal_period_end"].max()
    wide["_fiscal_period_end"] = pd.to_datetime(wide.index.map(fpe))
    wide.index.name = "ticker"
    return wide
