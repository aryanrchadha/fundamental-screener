"""India adapter: BSE filing dates + Yahoo financials -> canonical PIT tags.

*** READ THIS BEFORE TRUSTING OUTPUT: this adapter is STRUCTURALLY WEAKER
than the US-GAAP, CVM (Brazil) and DART (Korea) ones, for a reason that is
about India's free data landscape rather than the code. ***

WHY IT IS BUILT DIFFERENTLY. The other three markets each have a regulator
publishing machine-readable statements WITH a filing date attached to every
number: SEC EDGAR's `filed`, CVM's `DT_RECEB`, DART's `rcept_dt`. India has
no free equivalent. What it has, verified by direct request rather than
assumed, is two halves of the problem:

  * BSE's public API (`api.bseindia.com`) serves corporate announcements
    including audited financial results, each with a real dissemination
    TIMESTAMP (`News_submission_dt` / `DissemDT`) — e.g. Reliance's FY2024
    audited results were disseminated 2024-04-22T19:00:20. That is a
    genuine, authoritative filing date. But the numbers themselves are in
    an attached PDF: the XBRL URL patterns all return 404 and the
    structured-results endpoints return BSE's generic HTML error page, so
    the VALUES are not machine-readable from BSE for free.
  * Yahoo Finance serves the VALUES for `.NS` tickers, and unusually
    completely — every canonical tag this project needs is present,
    including a direct `EBIT` and `Ordinary Shares Number`. But Yahoo
    attaches no filing date at all, only the fiscal period end, so on its
    own it cannot support point-in-time gating.

Neither source is PIT-capable alone. This module joins them: values from
Yahoo, keyed to fiscal period end, gated by the real BSE dissemination date
of the results announcement that first reported that period. The join is
the whole contribution.

THE LIMITATION THAT CANNOT BE ENGINEERED AWAY. Yahoo serves the CURRENT
value for each fiscal period — one number per period, as it stands today.
If a company later restated, Yahoo shows the restated figure and the
original is simply gone. So:

  * Look-ahead IS prevented: a period's numbers are invisible before the
    date they were actually announced.
  * Restatement-blindness is NOT: a value that was revised later appears
    as though it had always read that way. `is_restatement` is therefore
    always False here, and the load-bearing restatement test that
    pit_fundamentals runs against EDGAR/CVM/DART data has no equivalent
    for India, because the source physically cannot express it.

That is a real weakening of the point-in-time guarantee and is stated in
FINDINGS.md rather than buried. Yahoo also serves only ~5 annual periods,
which after the year-on-year deltas Piotroski and Ohlson need leaves ~4
scoreable years — enough for a screener, too short for the kind of backtest
the US and Korean universes support.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
import requests_cache

log = logging.getLogger(__name__)

BSE_ANNOUNCEMENTS_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w"
BSE_SCRIP_LIST_URL = "https://api.bseindia.com/BseIndiaAPI/api/ListofScripData/w"

# BSE rejects requests without a browser-shaped User-Agent and Referer.
BSE_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"),
    "Referer": "https://www.bseindia.com/",
    "Accept": "application/json, text/plain, */*",
}

# Yahoo statement-row label -> canonical tag. Confirmed present on real
# Indian filers (Reliance FY2022-FY2026 carries every one of these).
#
# EQUITY MAPPING IS DELIBERATELY THE GROSS (INCLUDING-NCI) ROW. Yahoo
# publishes both "Stockholders Equity" (parent-only) and "Total Equity
# Gross Minority Interest". Using the parent-only row breaks the balance
# sheet by exactly the noncontrolling interest — on Reliance FY2026 that is
# a ₹181,836 crore hole, since Jio and Reliance Retail have large outside
# shareholders. With the gross row, Assets = Liabilities + Equity closes to
# ₹2 crore (rounding). This also matches the Korean adapter, which picks
# `ifrs-full_Equity` (total) over the parent-attributable variant for the
# same reason, so leverage means the same thing in both markets.
YF_BALANCE_SHEET_MAP = {
    "Total Assets": "Assets",
    "Current Assets": "AssetsCurrent",
    "Current Liabilities": "LiabilitiesCurrent",
    "Total Liabilities Net Minority Interest": "Liabilities",
    "Total Equity Gross Minority Interest": "StockholdersEquity",
    "Retained Earnings": "RetainedEarningsAccumulatedDeficit",
    "Long Term Debt": "LongTermDebtNoncurrent",
    "Ordinary Shares Number": "CommonStockSharesOutstanding",
}
# Used only when the gross row is absent (a filer with no subsidiaries has
# no NCI, so parent-only equity IS total equity).
YF_EQUITY_FALLBACK = {"Stockholders Equity": "StockholdersEquity"}
YF_INCOME_MAP = {
    "Total Revenue": "Revenues",
    "Cost Of Revenue": "CostOfRevenue",
    "Gross Profit": "GrossProfit",
    "Net Income": "NetIncomeLoss",
    "EBIT": "EBIT",
}
YF_CASHFLOW_MAP = {
    "Operating Cash Flow": "NetCashProvidedByUsedInOperatingActivities",
}

# Indian issuers must report audited annual results within 60 days of the
# fiscal year end (SEBI LODR Reg. 33). A results announcement further than
# this from the period end is reporting some OTHER period, so the fact is
# dropped rather than gated on a date that does not belong to it.
MAX_DAYS_PERIOD_END_TO_FILING = 180


def _session(cache_path: str, cache_ttl: int) -> requests_cache.CachedSession:
    return requests_cache.CachedSession(cache_path, backend="sqlite", expire_after=cache_ttl)


def get_bse_result_filings(
    scrip_code: str, start_year: int = 2015, end_year: int = 2026,
    cache_path: str = "data/http_cache", cache_ttl: int = 30 * 86400,
) -> pd.DataFrame:
    """Every 'Financial Results' announcement for one BSE scrip, with its
    real dissemination date. Returns columns [filed_date, headline]."""
    session = _session(cache_path, cache_ttl)
    rows: list[dict] = []
    # The endpoint caps each query's span, so walk it a year at a time.
    for yr in range(start_year, end_year + 1):
        page = 1
        while True:
            resp = session.get(
                BSE_ANNOUNCEMENTS_URL,
                params={"pageno": page, "strCat": "Result", "strPrevDate": f"{yr}0101",
                        "strScrip": scrip_code, "strSearch": "P",
                        "strToDate": f"{yr}1231", "strType": "C"},
                headers=BSE_HEADERS, timeout=45,
            )
            if resp.status_code != 200:
                break
            try:
                table = resp.json().get("Table", []) or []
            except ValueError:
                break
            rows += table
            if len(table) < 10:  # endpoint pages at 10 rows
                break
            page += 1
    if not rows:
        return pd.DataFrame(columns=["filed_date", "headline"])
    df = pd.DataFrame(rows)
    stamp = df.get("News_submission_dt", df.get("DissemDT"))
    df["filed_date"] = pd.to_datetime(stamp, errors="coerce").dt.date
    df = df.dropna(subset=["filed_date"])
    out = df[["filed_date"]].copy()
    out["headline"] = df.get("NEWSSUB", "")
    return out.drop_duplicates().sort_values("filed_date").reset_index(drop=True)


def get_yf_annual_financials(ticker: str, symbol_suffix: str = ".NS") -> dict[str, pd.DataFrame]:
    """Annual balance sheet / income statement / cash flow from Yahoo,
    keyed by fiscal period end. No filing dates — those come from BSE."""
    import yfinance as yf

    t = yf.Ticker(f"{ticker}{symbol_suffix}")
    return {"bs": t.balance_sheet, "is": t.income_stmt, "cf": t.cashflow}


def facts_from_sources(
    ticker: str, scrip_code: str, statements: dict[str, pd.DataFrame], filings: pd.DataFrame
) -> pd.DataFrame:
    """Pure transform: join Yahoo values to BSE filing dates.

    Split from the network calls so the join and gating logic is testable
    offline, exactly as the CVM and DART adapters are.
    """
    if filings is None or filings.empty:
        log.warning("%s (%s): no BSE results announcements — cannot establish "
                    "filing dates, so every fact is dropped", ticker, scrip_code)
        return pd.DataFrame()
    filed_dates = sorted(pd.to_datetime(filings["filed_date"]).dt.date.unique())

    def first_filing_after(period_end: date) -> date | None:
        """The announcement that first reported this period: the earliest
        results filing strictly after the period ended. Anything beyond the
        reporting deadline window is reporting a different period."""
        for fd in filed_dates:
            if fd > period_end:
                if (fd - period_end).days <= MAX_DAYS_PERIOD_END_TO_FILING:
                    return fd
                return None
        return None

    bs_map = dict(YF_BALANCE_SHEET_MAP)
    bs = statements.get("bs")
    if bs is not None and not getattr(bs, "empty", True):
        if "Total Equity Gross Minority Interest" not in bs.index:
            bs_map.update(YF_EQUITY_FALLBACK)
    specs = [("bs", bs_map, False),
             ("is", YF_INCOME_MAP, True),
             ("cf", YF_CASHFLOW_MAP, True)]
    rows: list[dict] = []
    for key, mapping, is_flow in specs:
        stmt = statements.get(key)
        if stmt is None or getattr(stmt, "empty", True):
            continue
        for label, canon in mapping.items():
            if label not in stmt.index:
                continue
            for col in stmt.columns:
                value = stmt.loc[label, col]
                if pd.isna(value):
                    continue
                period_end = pd.Timestamp(col).date()
                filed = first_filing_after(period_end)
                if filed is None:
                    continue
                rows.append({
                    "cik": str(scrip_code), "ticker": ticker, "tag": canon,
                    "fiscal_period_end": period_end,
                    "start_date": date(period_end.year - 1, period_end.month, period_end.day)
                                  + timedelta(days=1) if is_flow else None,
                    "filed_date": filed, "value": float(value),
                    "unit": "shares" if canon == "CommonStockSharesOutstanding" else "INR",
                    "form": "BSE-ANNUAL", "fy": period_end.year, "fp": "FY",
                    # Yahoo serves one CURRENT value per period, so an
                    # original-vs-restated distinction cannot exist here.
                    # See the module docstring.
                    "is_restatement": False,
                    "taxonomy": "bse-in",
                })
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    return out.drop_duplicates(subset=["tag", "fiscal_period_end", "filed_date"])


def extract_company_facts(
    ticker: str, scrip_code: str, cache_path: str = "data/http_cache",
) -> pd.DataFrame:
    filings = get_bse_result_filings(scrip_code, cache_path=cache_path)
    statements = get_yf_annual_financials(ticker)
    return facts_from_sources(ticker, scrip_code, statements, filings)


def run_india_ingest(
    tickers_scrips: dict[str, str], db_path: str, cache_path: str = "data/http_cache",
) -> None:
    """Ingest BSE-dated, Yahoo-valued Indian facts into the shared PIT
    database. No API key is required for either source."""
    from pit_fundamentals.schema import connect, init_db

    con = connect(db_path)
    init_db(con)
    total = 0
    for i, (ticker, scrip) in enumerate(tickers_scrips.items(), 1):
        try:
            facts = extract_company_facts(ticker, scrip, cache_path=cache_path)
        except Exception as exc:
            log.warning("%s (%s): fetch failed (%s) — skipped", ticker, scrip, exc)
            continue
        if facts.empty:
            log.warning("%s (%s): no facts extracted", ticker, scrip)
            continue
        con.execute("DELETE FROM pit_facts WHERE cik = ? AND taxonomy = 'bse-in'", [str(scrip)])
        con.register("_staging_in", facts)
        con.execute(
            """INSERT INTO pit_facts
               (cik, ticker, tag, fiscal_period_end, start_date, filed_date,
                value, unit, form, fy, fp, is_restatement, taxonomy)
               SELECT cik, ticker, tag, fiscal_period_end, start_date, filed_date,
                      value, unit, form, fy, fp, is_restatement, taxonomy
               FROM _staging_in"""
        )
        con.unregister("_staging_in")
        total += len(facts)
        log.info("[%d/%d] %s (%s): %d facts", i, len(tickers_scrips), ticker, scrip, len(facts))
    con.close()
    log.info("India ingest complete: %d fact rows across %d tickers", total, len(tickers_scrips))
