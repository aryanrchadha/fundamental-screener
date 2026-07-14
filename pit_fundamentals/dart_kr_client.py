"""South Korea fundamentals adapter: DART OpenAPI -> canonical PIT tags.

*** NOT LIVE-VERIFIED — READ BEFORE TRUSTING ANY OUTPUT FROM THIS MODULE ***
Unlike pit_fundamentals/cvm_br_client.py (which was built by downloading and
hand-inspecting real 2022-2024 CVM filings with zero credentials required),
this module was written without a registered DART API key: the user did not
have one available when this was built. Every endpoint URL, parameter name,
and response field below is sourced from DART's official developer guide
(engopendart.fss.or.kr) and cross-checked against a real worked example from
an independent Korean quant-investing tutorial and the open-source DartLab
project's account-normalization documentation — but nothing here has been
exercised against a live API response. Get a free key at
https://opendart.fss.or.kr (registration, no cost, typically instant
approval), set it as the DART_API_KEY environment variable, and run:

    python -m pit_fundamentals.ingest --taxonomy dart-kr --years 2023

...then diff the output against a known company's real financial statements
before relying on this for anything. Treat every mapping below as a
hypothesis, not a fact, until you've done that.

WHY SOUTH KOREA, AS THE NEXT "LEADING EM" AFTER BRAZIL: DART (Data Analysis,
Retrieval and Transfer System), run by Korea's Financial Supervisory
Service, is a free, no-cost, EDGAR-like open-data system — the closest
analogue after Brazil's CVM among major EM exchanges. Its one meaningful
extra requirement is a registered API key (`crtfc_key`), handled here the
same way this project already treats FMP_API_KEY: optional, read from an
environment variable, and the ingest path fails fast with an actionable
message if it's unset rather than silently doing nothing.

WHY THIS TAXONOMY IS HARDER TO MAP THAN BRAZIL'S: CVM's CD_CONTA codes are
centrally fixed and consistent (verified directly from real files). DART's
`account_id` field is a real IFRS-XBRL concept name — e.g. a confirmed real
example: Samsung Electronics' FY2019 annual report tags current assets as
`ifrs-full_CurrentAssets` — but IFRS's taxonomy allows company-specific
extensions, and Korean filers are documented (by the independent DartLab
project, which exists specifically to solve this) to tag the SAME concept
under different names: Samsung uses `ifrs-full_Revenue`, SK Hynix uses
`dart_Revenue`, LG Energy Solution uses a bare `Revenue` with no namespace
prefix at all — all three meaning the same thing. So CODE_MAP here maps each
canonical tag to a LIST of candidate account_id spellings (prefix removed by
_normalize_account_id before comparison), tried in order — the same
"tag fallback" pattern screener/scores.py already uses for US-GAAP's own
tag-naming inconsistency (e.g. Revenues vs. SalesRevenueNet), just extended
to also strip taxonomy namespace prefixes.

WHAT IS DELIBERATELY NOT MAPPED (left as NaN rather than guessed): long-term
debt and shares outstanding both need either a Korea-specific DART
extension concept or a wholly separate DART endpoint (share count comes
from a different API family, DS004, not the financial-statement endpoint
used here) that could not be confirmed without a live call. Guessing a
plausible-looking but wrong tag name is worse than leaving the field empty
— a wrong tag can silently match real (wrong) data; an absent tag just
means that score is excluded and logged, consistent with this project's
"never fabricate" rule. Piotroski's share-dilution criterion and Altman
Z's market-cap term are therefore NOT computable for DART-sourced companies
until someone extends this module with a verified shares-outstanding
source. Ohlson O-Score needs neither, and IS expected to be fully
computable once this module is live-tested (it only needs Assets,
Liabilities, AssetsCurrent, LiabilitiesCurrent, NetIncomeLoss for two years,
and operating cash flow — all covered by the mappings below).
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from datetime import date

import pandas as pd
import requests
import requests_cache

log = logging.getLogger(__name__)

BASE_URL = "https://opendart.fss.or.kr/api"
CORP_CODE_URL = f"{BASE_URL}/corpCode.xml"
FILING_LIST_URL = f"{BASE_URL}/list.json"
FINANCIALS_URL = f"{BASE_URL}/fnlttSinglAcntAll.json"

ANNUAL_REPRT_CODE = "11011"  # 사업보고서 (Annual/Business Report) — confirmed enum value
FS_DIV_PRIORITY = ["CFS", "OFS"]  # Consolidated preferred, Individual/standalone fallback

# canonical tag -> candidate account_id spellings, prefix-stripped and
# lowercased before comparison (see _normalize_account_id). Only concepts
# from the CORE IFRS Accounting Taxonomy are included — these names are
# defined by the IFRS Foundation itself, independent of DART, which is why
# they're trusted further than a DART-specific extension guess would be.
# 'CurrentAssets' is the one entry confirmed against an actual DART API
# response (Samsung Electronics FY2019); the rest follow the same standard
# IFRS concept-naming convention but have not been individually confirmed
# against a live DART response.
CODE_MAP: dict[str, list[str]] = {
    "Assets": ["Assets"],
    "AssetsCurrent": ["CurrentAssets"],  # confirmed real example: ifrs-full_CurrentAssets
    "Liabilities": ["Liabilities"],
    "LiabilitiesCurrent": ["CurrentLiabilities"],
    "StockholdersEquity": ["Equity", "EquityAttributableToOwnersOfParent"],
    "RetainedEarningsAccumulatedDeficit": ["RetainedEarnings"],
    "Revenues": ["Revenue"],
    "CostOfRevenue": ["CostOfSales"],
    "GrossProfit": ["GrossProfit"],
    "NetIncomeLoss": ["ProfitLoss"],
    "NetCashProvidedByUsedInOperatingActivities": [
        "CashFlowsFromUsedInOperatingActivities",
        "CashFlowsFromUsedInOperatingActivitiesBeforeIncomeTaxesAndOtherItemsAffectingConciliation",
    ],
    "EBIT": ["ProfitLossFromOperatingActivities"],  # IFRS "operating profit" — low confidence, see docstring
}

# BS/balance-sheet items are instant facts (like US-GAAP's Assets); IS/CF
# items are duration facts requiring the annual-period check in query.py.
INSTANT_STATEMENT_TYPES = {"BS"}
FLOW_STATEMENT_TYPES = {"IS", "CIS", "CF"}


def _normalize_account_id(raw: str) -> str:
    """Strip the taxonomy namespace prefix DART filers inconsistently use
    (ifrs-full_, dart_, ifrs_, ifrs-smes_, or none at all) and lowercase."""
    s = str(raw)
    for prefix in ("ifrs-full_", "ifrs-smes_", "ifrs_", "dart_"):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break
    return s.lower()


_CANDIDATE_LOOKUP: dict[str, str] = {
    _normalize_account_id(candidate): tag
    for tag, candidates in CODE_MAP.items()
    for candidate in candidates
}


def require_api_key() -> str:
    key = os.environ.get("DART_API_KEY")
    if not key:
        raise RuntimeError(
            "DART_API_KEY is not set. Register a free key at "
            "https://opendart.fss.or.kr, then `export DART_API_KEY=...` "
            "before running --taxonomy dart-kr. Unlike FMP, this taxonomy "
            "has no code path that runs without a key — DART requires it "
            "on every single call, including the free company-code list."
        )
    return key


def _session(cache_path: str, cache_ttl: int) -> requests_cache.CachedSession:
    return requests_cache.CachedSession(cache_path, backend="sqlite", expire_after=cache_ttl)


def download_corp_codes(
    api_key: str, cache_path: str = "data/http_cache", cache_ttl: int = 30 * 86400
) -> pd.DataFrame:
    """Bulk company-code list: corp_code, corp_name, stock_code, modify_date.

    Endpoint and response fields per DART's official guide
    (DS001/corpCode) — a ZIP containing CORPCODE.xml.
    """
    session = _session(cache_path, cache_ttl)
    resp = session.get(CORP_CODE_URL, params={"crtfc_key": api_key}, timeout=60)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_bytes = zf.read("CORPCODE.xml")
    df = pd.read_xml(io.BytesIO(xml_bytes))
    df["corp_code"] = df["corp_code"].astype(str).str.zfill(8)
    return df


def search_annual_filings(
    api_key: str, corp_code: str, bgn_de: str, end_de: str,
    cache_path: str = "data/http_cache", cache_ttl: int = 30 * 86400,
) -> pd.DataFrame:
    """Filing index for one company over a date range: rcept_no + rcept_dt
    (the receipt/filing date — DART's analogue of EDGAR's `filed` and CVM's
    DT_RECEB), filtered to annual reports (report_nm contains '사업보고서',
    the exact term used in DART's own reprt_code documentation).
    """
    session = _session(cache_path, cache_ttl)
    resp = session.get(
        FILING_LIST_URL,
        params={
            "crtfc_key": api_key, "corp_code": corp_code,
            "bgn_de": bgn_de, "end_de": end_de,
            "pblntf_ty": "A",  # periodic disclosures (annual/quarterly reports)
            "page_count": 100,
        },
        timeout=60,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("status") != "000":
        log.warning("DART list.json for %s: status=%s message=%s",
                    corp_code, payload.get("status"), payload.get("message"))
        return pd.DataFrame()
    rows = payload.get("list", [])
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df[df["report_nm"].str.contains("사업보고서", na=False)]
    df["rcept_dt"] = pd.to_datetime(df["rcept_dt"], format="%Y%m%d").dt.date
    return df[["corp_code", "rcept_no", "rcept_dt", "report_nm"]].sort_values("rcept_dt")


def get_financial_statement(
    api_key: str, corp_code: str, bsns_year: str,
    cache_path: str = "data/http_cache", cache_ttl: int = 30 * 86400,
) -> pd.DataFrame:
    """One company-year's full account-level financial statement, trying
    consolidated (CFS) then falling back to individual (OFS) — mirrors the
    CVM adapter's _con/_ind fallback."""
    session = _session(cache_path, cache_ttl)
    for fs_div in FS_DIV_PRIORITY:
        resp = session.get(
            FINANCIALS_URL,
            params={
                "crtfc_key": api_key, "corp_code": corp_code,
                "bsns_year": bsns_year, "reprt_code": ANNUAL_REPRT_CODE,
                "fs_div": fs_div,
            },
            timeout=60,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") == "000" and payload.get("list"):
            df = pd.DataFrame(payload["list"])
            df["fs_div"] = fs_div
            return df
        log.info("DART fnlttSinglAcntAll %s/%s: no %s data (status=%s)",
                 corp_code, bsns_year, fs_div, payload.get("status"))
    return pd.DataFrame()


def extract_company_facts(
    api_key: str, ticker: str, corp_code: str, bsns_year: str,
    cache_path: str = "data/http_cache",
) -> pd.DataFrame:
    """Pull one company-year's canonical facts, gated by the real filing
    date resolved from search_annual_filings. Returns rows in the same
    schema as the US-GAAP and CVM ingesters. Thin network-fetching wrapper
    around facts_from_dataframes (kept separate so the mapping/gating logic
    is testable without hitting the live API)."""
    fin = get_financial_statement(api_key, corp_code, bsns_year, cache_path=cache_path)
    if fin.empty:
        return pd.DataFrame()

    year_start = f"{int(bsns_year) + 1}0101"
    year_end = f"{int(bsns_year) + 1}0630"  # annual reports file within ~90 days of FYE
    filings = search_annual_filings(api_key, corp_code, year_start, year_end, cache_path=cache_path)
    if filings.empty:
        log.warning("%s: no annual filing found in list.json for FY%s — cannot resolve filed_date", ticker, bsns_year)
        return pd.DataFrame()

    return facts_from_dataframes(ticker, corp_code, bsns_year, fin, filings)


def facts_from_dataframes(
    ticker: str, corp_code: str, bsns_year: str, fin: pd.DataFrame, filings: pd.DataFrame
) -> pd.DataFrame:
    """Pure transformation: account_id mapping + rcept_dt gating, given
    already-fetched fnlttSinglAcntAll (`fin`) and list.json (`filings`)
    DataFrames. Split out from extract_company_facts so tests can exercise
    the real mapping/gating logic with synthetic DataFrames — no network,
    no API key required."""
    rows: list[dict] = []
    for _, r in fin.iterrows():
        canon = _CANDIDATE_LOOKUP.get(_normalize_account_id(r["account_id"]))
        if canon is None:
            continue
        rcept_no = r["rcept_no"]
        filed_row = filings[filings["rcept_no"] == rcept_no]
        if filed_row.empty:
            # This account row's own rcept_no isn't in our annual-filing
            # index (e.g. amendment filed under a different rcept_no than
            # what fnlttSinglAcntAll returned) — skip rather than guess a
            # filed_date, consistent with never fabricating PIT gating data.
            continue
        filed_date = filed_row["rcept_dt"].iloc[0]
        sj_div = r.get("sj_div")
        is_flow = sj_div in FLOW_STATEMENT_TYPES
        for period_key, amount_key in [
            ("thstrm", "thstrm_amount"), ("frmtrm", "frmtrm_amount"), ("bfefrmtrm", "bfefrmtrm_amount"),
        ]:
            amount = r.get(amount_key)
            if amount in (None, "", "-") or pd.isna(amount):
                continue
            fiscal_year_offset = {"thstrm": 0, "frmtrm": 1, "bfefrmtrm": 2}[period_key]
            fiscal_period_end = date(int(bsns_year) - fiscal_year_offset, 12, 31)
            rows.append(
                {
                    "cik": corp_code,
                    "ticker": ticker,
                    "tag": canon,
                    "fiscal_period_end": fiscal_period_end,
                    "start_date": date(fiscal_period_end.year, 1, 1) if is_flow else None,
                    "filed_date": filed_date,
                    "value": float(str(amount).replace(",", "")),
                    "unit": "KRW",
                    "form": "DART-ANNUAL",
                    "fy": fiscal_period_end.year,
                    "fp": "FY",
                    "taxonomy": "dart-kr",
                }
            )

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out = out.drop_duplicates(subset=["tag", "fiscal_period_end", "filed_date"])
    out = out.sort_values(["tag", "fiscal_period_end", "filed_date"])
    first_filing = out.groupby(["tag", "fiscal_period_end"], dropna=False)["filed_date"].transform("min")
    out["is_restatement"] = out["filed_date"] > first_filing
    return out


def run_dart_ingest(
    tickers_corp_codes: dict[str, str],
    years: list[str],
    db_path: str,
    cache_path: str = "data/http_cache",
) -> None:
    """Ingest DART data for a ticker->corp_code crosswalk into the shared
    PIT database. Requires DART_API_KEY. NOT LIVE-VERIFIED — see module
    docstring."""
    api_key = require_api_key()
    from pit_fundamentals.schema import connect, init_db

    con = connect(db_path)
    init_db(con)
    total = 0
    for year in years:
        for ticker, corp_code in tickers_corp_codes.items():
            facts = extract_company_facts(api_key, ticker, corp_code, year, cache_path=cache_path)
            if facts.empty:
                log.warning("%s (%s): no facts extracted for %s", ticker, corp_code, year)
                continue
            con.execute(
                "DELETE FROM pit_facts WHERE cik = ? AND fy = ? AND taxonomy = 'dart-kr'",
                [corp_code, int(year)],
            )
            con.register("_staging_kr", facts)
            con.execute(
                """INSERT INTO pit_facts
                   (cik, ticker, tag, fiscal_period_end, start_date, filed_date,
                    value, unit, form, fy, fp, is_restatement, taxonomy)
                   SELECT cik, ticker, tag, fiscal_period_end, start_date, filed_date,
                          value, unit, form, fy, fp, is_restatement, taxonomy
                   FROM _staging_kr"""
            )
            con.unregister("_staging_kr")
            total += len(facts)
            log.info("%s (%s): %d facts loaded for %s", ticker, corp_code, len(facts), year)
    con.close()
    log.info("DART ingest complete: %d fact rows across %d tickers, %d years — "
             "NOT LIVE-VERIFIED, sanity-check these numbers against a real filing.",
             total, len(tickers_corp_codes), len(years))
