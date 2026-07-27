"""Ingestion CLI: pull XBRL companyfacts from EDGAR into the PIT database.

Usage:
    python -m pit_fundamentals.ingest --universe sp500 [--limit 50] [--refresh]

The ingest is resumable: CIKs already recorded in `ingest_log` are skipped
unless --refresh is passed. Every filed value is stored — the `filed` date on
each XBRL fact is the point-in-time availability gate (NOT the fiscal period
`end` date), and repeat filings for the same period are flagged as
restatements rather than overwritten.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime

import pandas as pd

from pit_fundamentals.edgar_client import EdgarClient
from pit_fundamentals.schema import DEFAULT_DB_PATH, connect, init_db

log = logging.getLogger(__name__)

# us-gaap tags tracked, including common fallbacks. Missing tags are simply
# absent for that company — downstream scoring excludes company-quarters
# lacking required inputs (never imputes a plug value).
TRACKED_TAGS: dict[str, list[str]] = {
    "us-gaap": [
        "NetIncomeLoss",
        "Assets",
        "Liabilities",
        "AssetsCurrent",
        "LiabilitiesCurrent",
        "NetCashProvidedByUsedInOperatingActivities",
        "CommonStockSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerExcludingAssessedTax",  # post-ASC-606 tag
        "GrossProfit",
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "RetainedEarningsAccumulatedDeficit",
        "StockholdersEquity",
        "LongTermDebtNoncurrent",
        "IncomeTaxExpenseBenefit",   # for the Altman EBIT add-back
        "InterestExpense",           # for the Altman EBIT add-back
    ],
    # dei shares outstanding is often better-populated than the us-gaap tag
    "dei": ["EntityCommonStockSharesOutstanding"],
}

INSERT_SQL = """
INSERT INTO pit_facts
(cik, ticker, tag, fiscal_period_end, start_date, filed_date, value, unit, form, fy, fp, is_restatement)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def extract_facts(cik: str, ticker: str, facts_json: dict) -> pd.DataFrame:
    """Flatten one companyfacts JSON into rows of the pit_facts schema.

    The `filed` field on each value is what gates point-in-time visibility.
    `is_restatement` is set per (tag, fiscal_period_end, start_date) group:
    the earliest filing is the original; any later filing for the same period
    is a restatement (or a re-report in a subsequent filing — either way, it
    only becomes visible from its own filed_date, which is the correct PIT
    behavior for both cases).
    """
    rows: list[dict] = []
    facts = facts_json.get("facts", {})
    for taxonomy, tags in TRACKED_TAGS.items():
        taxo = facts.get(taxonomy, {})
        for tag in tags:
            node = taxo.get(tag)
            if node is None:
                continue
            for unit, values in node.get("units", {}).items():
                for v in values:
                    end = _parse_date(v.get("end"))
                    filed = _parse_date(v.get("filed"))
                    if end is None or filed is None or v.get("val") is None:
                        continue
                    rows.append(
                        {
                            "cik": cik,
                            "ticker": ticker,
                            "tag": tag,
                            "fiscal_period_end": end,
                            "start_date": _parse_date(v.get("start")),
                            "filed_date": filed,
                            "value": float(v["val"]),
                            "unit": unit,
                            "form": v.get("form"),
                            "fy": v.get("fy"),
                            "fp": v.get("fp"),
                        }
                    )
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Same value re-reported in multiple filings (e.g. comparative columns of
    # later 10-Ks) — keep one row per distinct (tag, period, filed, value).
    df = df.drop_duplicates(subset=["tag", "fiscal_period_end", "start_date", "filed_date", "value"])
    df = df.sort_values(["tag", "fiscal_period_end", "filed_date"])
    first_filing = df.groupby(["tag", "fiscal_period_end"], dropna=False)["filed_date"].transform("min")
    df["is_restatement"] = df["filed_date"] > first_filing
    return df


def ingest_company(con, client: EdgarClient, cik: str, ticker: str) -> int:
    """Pull and load one company's facts. Returns number of rows inserted."""
    facts_json = client.get_companyfacts(cik)
    if facts_json is None:
        log.warning("No companyfacts for %s (CIK %s) — skipped", ticker, cik)
        n = 0
    else:
        df = extract_facts(cik, ticker, facts_json)
        n = len(df)
        if n:
            con.execute("DELETE FROM pit_facts WHERE cik = ?", [cik])
            con.register("_staging", df)
            con.execute(
                """INSERT INTO pit_facts
                   SELECT cik, ticker, tag, fiscal_period_end, start_date, filed_date,
                          value, unit, form, fy, fp, is_restatement
                   FROM _staging"""
            )
            con.unregister("_staging")
    con.execute(
        "INSERT OR REPLACE INTO ingest_log VALUES (?, ?, ?, now())", [cik, ticker, n]
    )
    return n


def already_ingested(con, cik: str) -> bool:
    return con.execute("SELECT 1 FROM ingest_log WHERE cik = ?", [cik]).fetchone() is not None


def run_ingest(
    tickers: list[str],
    db_path: str = DEFAULT_DB_PATH,
    refresh: bool = False,
    cache_path: str = "data/http_cache",
) -> None:
    client = EdgarClient(cache_path=cache_path)
    cik_map = client.get_ticker_cik_map()
    con = connect(db_path)
    init_db(con)
    total = 0
    for i, ticker in enumerate(tickers, 1):
        # EDGAR uses '-' where exchanges use '.' (BRK.B -> BRK-B and vice versa)
        cik = cik_map.get(ticker.upper()) or cik_map.get(ticker.upper().replace("-", ""))
        if cik is None:
            log.warning("No CIK for ticker %s — skipped", ticker)
            continue
        if not refresh and already_ingested(con, cik):
            continue
        n = ingest_company(con, client, cik, ticker.upper())
        total += n
        log.info("[%d/%d] %s: %d facts", i, len(tickers), ticker, n)
    con.close()
    log.info("Ingest complete: %d new fact rows", total)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Ingest fundamentals facts into the PIT DB")
    p.add_argument("--universe", default="sp500", choices=["sp500"])
    p.add_argument(
        "--taxonomy", default="us-gaap", choices=["us-gaap", "cvm-br", "dart-kr", "bse-in"],
        help=(
            "us-gaap: SEC EDGAR XBRL (default). cvm-br: Brazil/B3 blue chips via "
            "CVM Dados Abertos. dart-kr: South Korea/KOSPI via DART OpenAPI "
            "(requires DART_API_KEY env var; NOT live-verified, see "
            "dart_kr_client.py's module docstring before trusting output)."
        ),
    )
    p.add_argument("--limit", type=int, default=None, help="ingest only the first N tickers (us-gaap only)")
    p.add_argument("--years", type=int, nargs="+", default=[2023], help="DFP/DART years to pull (cvm-br/dart-kr only)")
    p.add_argument("--refresh", action="store_true", help="re-ingest already-loaded CIKs")
    p.add_argument("--db", default=DEFAULT_DB_PATH)
    args = p.parse_args(argv)

    if args.taxonomy == "cvm-br":
        from pit_fundamentals.cvm_br_client import run_cvm_ingest
        from screener.universe_br import get_br_blue_chips

        run_cvm_ingest(get_br_blue_chips(), years=args.years, db_path=args.db)
        return

    if args.taxonomy == "bse-in":
        from pit_fundamentals.india_client import run_india_ingest
        from screener.universe_in import get_in_universe

        run_india_ingest(get_in_universe(), db_path=args.db)
        return

    if args.taxonomy == "dart-kr":
        from pit_fundamentals.dart_kr_client import run_dart_ingest
        from screener.universe_kr import get_kr_blue_chips

        run_dart_ingest(get_kr_blue_chips(), years=[str(y) for y in args.years], db_path=args.db)
        return

    # The universe list lives in the screener package; imported lazily so
    # pit_fundamentals itself stays importable without the screener installed.
    try:
        from screener.universe import get_sp500_constituents

        tickers = get_sp500_constituents()["ticker"].tolist()
    except ImportError:
        sys.exit("screener package not found — pass tickers programmatically via run_ingest()")

    if args.limit:
        tickers = tickers[: args.limit]
    run_ingest(tickers, db_path=args.db, refresh=args.refresh)


if __name__ == "__main__":
    main()
