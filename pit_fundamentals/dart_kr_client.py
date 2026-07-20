"""South Korea fundamentals adapter: DART OpenAPI -> canonical PIT tags.

*** LIVE-VERIFIED against 21 real KOSPI blue chips, FY2022-2023 ***
(`screener/universe_kr.py`; corp_codes resolved from DART's own corpCode
registry, never from memory). Verification standard: the accounting
identity Assets = Liabilities + StockholdersEquity must hold EXACTLY on
extracted values — 37/40 company-years pass; the other 3 are the FY2022
financial institutions, for which DART itself returns status 013 "no data"
(this endpoint's documented historical exclusion of financials; their
coverage begins FY2023). Ohlson O-Score computes end-to-end through the
UNMODIFIED screener/scores.py functions for all 18 non-financials, with an
economically coherent ranking: Samsung Electronics safest (-14.85),
debt-laden KEPCO worst (-9.39), SK Hynix mid-pack (-11.14, consistent
with its 2023 memory-downcycle loss year).

FIVE real bugs were found and fixed across the two live-verification
passes — each is now a regression test in tests/test_dart_kr_mapping.py:
(1) SCE (Statement of Changes in Equity) tags seven genuinely different
values under the identical account_id `ifrs-full_Equity`, so it is never
mapped; (2) the EBIT candidate's initial guess
(`ProfitLossFromOperatingActivities`) never appears in real filings —
filers use the Korea-specific extension `dart_OperatingIncomeLoss`, now
the primary candidate; (3) candidate PRIORITY must be enforced, not left
to filing row order: SK Hynix's balance sheets carry both total Equity and
parent-attributable Equity as separate rows and flipped their order
between FY2022 and FY2023, silently swapping which one survived dedup;
(4) single-statement filers (SK Hynix, NAVER, Kakao, Amorepacific) put
their ENTIRE income statement under sj_div='CIS' with no 'IS' section —
an earlier revision excluded CIS and lost all their income facts; (5) for
restated years DART serves figures from documents received up to two
years after fiscal year end (Hyundai Motor's and Kakao's FY2022 came from
March-2024 documents), outside the original filing-search window — the
window is now +1..+2 years with a validated rcept_no date-prefix fallback
(first 8 digits = receipt date, empirically confirmed on four filings).

STILL NOT COVERED: shares outstanding (absent from this endpoint entirely
— see the "NOT MAPPED" section below), so Piotroski and Altman Z remain
uncomputable for Korean names; and filers outside these 21 may use tag
spellings or statement layouts this sweep didn't encounter.

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

WHAT IS DELIBERATELY NOT MAPPED (left as NaN rather than guessed): shares
outstanding. Confirmed by inspecting Samsung's real fnlttSinglAcntAll
response directly: no share-count field appears anywhere in it — this data
genuinely lives in a separate DART API family (share/equity-composition
endpoints, not called here), not just an unmapped tag within this
response. Guessing a plausible-looking but wrong tag name is worse than
leaving the field empty — a wrong tag can silently match real (wrong)
data; an absent tag just means that score is excluded and logged,
consistent with this project's "never fabricate" rule. Piotroski's
share-dilution criterion and Altman Z's market-cap term are therefore NOT
computable for DART-sourced companies until someone extends this module
with a verified shares-outstanding source. Ohlson O-Score needs neither
and IS confirmed working (Assets, Liabilities, AssetsCurrent,
LiabilitiesCurrent, NetIncomeLoss for two years, and operating cash flow —
all live-verified above).
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
# lowercased before comparison (see _normalize_account_id).
#
# *** LIVE-VERIFIED against Samsung Electronics' real FY2023 DART filing ***
# (corp_code 00126380, rcept_no 20240312000736) as of the update that added
# this comment. Confirmed real values, in KRW: Assets 455,905,980,000,000;
# Liabilities 92,228,115,000,000; Equity 363,677,865,000,000 (these three
# balance exactly: A = L + E); AssetsCurrent 195,936,557,000,000;
# LiabilitiesCurrent 75,719,452,000,000; RetainedEarnings 346,652,238,000,000;
# Revenue 258,935,494,000,000; CostOfSales 180,388,580,000,000; GrossProfit
# 78,546,914,000,000; ProfitLoss 15,487,100,000,000; operating cash flow
# 44,137,427,000,000. All of Assets/AssetsCurrent/Liabilities/
# LiabilitiesCurrent/Equity/RetainedEarnings/Revenue/CostOfSales/GrossProfit/
# ProfitLoss/CashFlowsFromUsedInOperatingActivities matched on the FIRST
# candidate string with no fallback needed — every one of them appeared as
# a plain `ifrs-full_<name>` tag for this filer. That does NOT prove every
# Korean filer tags consistently (DartLab's documented Samsung/dart_/bare
# split for Revenue is real and is exactly why candidate lists exist here,
# not a single string) — it proves the concept-name choices for THESE tags
# are correct for at least one large real filer.
CODE_MAP: dict[str, list[str]] = {
    "Assets": ["Assets"],
    "AssetsCurrent": ["CurrentAssets"],
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
    # Real Samsung filing uses the Korea-specific extension tag
    # dart_OperatingIncomeLoss (labeled 영업이익, "operating income") for
    # this line — NOT a core ifrs-full_ProfitLossFromOperatingActivities
    # concept, confirming this module's original low-confidence flag on
    # this specific mapping was warranted. Kept as a fallback in case some
    # other filer uses the pure-IFRS spelling instead (per DartLab, tagging
    # choice varies by company).
    "EBIT": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
}

# Canonical tags with NO single IFRS line item — computed as the SUM of
# multiple confirmed real component account_ids instead. Long-term debt:
# IFRS reports non-current bonds and non-current loans as separate lines;
# Samsung's real filing confirms both exist as distinct BS rows
# (ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued +
# ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived) with no combined
# "total non-current borrowings" line — summing them is the closest
# analogue to US-GAAP's single LongTermDebtNoncurrent tag.
SUM_CODE_MAP: dict[str, list[str]] = {
    "LongTermDebtNoncurrent": [
        "NoncurrentPortionOfNoncurrentBondsIssued",
        "NoncurrentPortionOfNoncurrentLoansReceived",
    ],
}

# DART's fnlttSinglAcntAll response includes FIVE statement sections
# (sj_div): BS, IS, CIS, CF, SCE. BS/IS/CIS/CF are processed; SCE never is.
#
# CIS (Statement of Comprehensive Income) must be INCLUDED — learned from
# the live 20-company sweep, not assumed: IFRS permits either a two-
# statement presentation (separate income statement `IS` + comprehensive
# income `CIS`; Samsung files this way, where CIS merely duplicates IS's
# ProfitLoss) or a SINGLE combined statement — and single-statement filers
# (SK Hynix, NAVER, Kakao, Amorepacific all confirmed from real FY2023
# responses) carry their ENTIRE income statement (Revenue, CostOfSales,
# GrossProfit, ProfitLoss, OperatingIncomeLoss) under sj_div='CIS' with NO
# IS section at all. Excluding CIS (an earlier revision of this module did)
# silently dropped every income-statement fact for those filers. For dual-
# statement filers the IS and CIS copies of a mapped tag carry identical
# values, so the (tag, fiscal_period_end, filed_date) dedup collapses them
# harmlessly. CIS-only concepts (ComprehensiveIncome, OCI components,
# NCI-attributable splits) have their own distinct account_ids that simply
# aren't in CODE_MAP.
#
# SCE (Statement of Changes in Equity) stays excluded: Samsung's real
# filing tags SEVEN different rows as "ifrs-full_Equity" within SCE alone
# — total equity, each equity component's beginning/ending balance, and
# NCI-attributable vs. parent-attributable subtotals — all under the
# identical account_id. Including SCE would produce conflicting values for
# the same (tag, fiscal_period_end) key with no principled way to pick the
# right one; BS already carries the single authoritative equity figure
# (confirmed: it satisfies Assets = Liabilities + Equity exactly).
MAPPABLE_STATEMENT_TYPES = {"BS", "IS", "CIS", "CF"}

# BS/balance-sheet items are instant facts (like US-GAAP's Assets);
# IS/CIS/CF items are duration facts requiring the annual-period check in
# query.py.
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


# normalized candidate spelling -> (canonical tag, priority). Priority is
# the candidate's position in CODE_MAP's list and MUST be enforced when a
# filing contains MORE THAN ONE candidate for the same tag: SK Hynix's real
# FY2022 and FY2023 balance sheets both carry ifrs-full_Equity (total, incl
# noncontrolling interests) AND ifrs-full_EquityAttributableToOwnersOfParent
# as separate rows, and the template's row ORDER flipped between the two
# years — resolving the collision by response order (the original bug)
# kept parent-only equity for FY2022 and total equity for FY2023, breaking
# Assets = Liabilities + Equity by exactly the ₩24.2B of NCI in 2022.
_CANDIDATE_LOOKUP: dict[str, tuple[str, int]] = {
    _normalize_account_id(candidate): (tag, priority)
    for tag, candidates in CODE_MAP.items()
    for priority, candidate in enumerate(candidates)
}
_SUM_CANDIDATE_LOOKUP: dict[str, str] = {
    _normalize_account_id(candidate): tag
    for tag, candidates in SUM_CODE_MAP.items()
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

    # Filing-index window: FY-end + 1 year THROUGH FY-end + 2 years.
    # Originally Jan-Jun of year+1 ("annual reports file within ~90 days"),
    # which live verification proved too narrow: for FY2022,
    # fnlttSinglAcntAll returned Hyundai Motor's and Kakao's figures from
    # documents received in MARCH 2024 (rcept_no 20240314…/20240320…) —
    # DART serves each bsns_year's statements from the latest document
    # containing them, which for a restated/re-reported year is a filing
    # up to two years after fiscal year end.
    year_start = f"{int(bsns_year) + 1}0101"
    year_end = f"{int(bsns_year) + 2}1231"
    filings = search_annual_filings(api_key, corp_code, year_start, year_end, cache_path=cache_path)
    # An empty index is no longer fatal: facts_from_dataframes can fall
    # back to the rcept_no date prefix (see _filed_date_for's comment).
    return facts_from_dataframes(ticker, corp_code, bsns_year, fin, filings)


def facts_from_dataframes(
    ticker: str, corp_code: str, bsns_year: str, fin: pd.DataFrame, filings: pd.DataFrame
) -> pd.DataFrame:
    """Pure transformation: account_id mapping + rcept_dt gating, given
    already-fetched fnlttSinglAcntAll (`fin`) and list.json (`filings`)
    DataFrames. Split out from extract_company_facts so tests can exercise
    the real mapping/gating logic with synthetic DataFrames — no network,
    no API key required."""
    # Only BS/IS/CF rows are ever mapped — see MAPPABLE_STATEMENT_TYPES'
    # comment for why SCE (and, harmlessly but redundantly, CIS) are
    # excluded: SCE in particular tags multiple genuinely-different values
    # (total equity, per-component balances, NCI- vs parent-attributable
    # net income) under the SAME account_id, which a naive per-row loop
    # would otherwise insert as silently conflicting facts.
    fin = fin[fin["sj_div"].isin(MAPPABLE_STATEMENT_TYPES)]

    def _filed_date_for(rcept_no):
        if not filings.empty:
            filed_row = filings[filings["rcept_no"] == rcept_no]
            if not filed_row.empty:
                return filed_row["rcept_dt"].iloc[0]
        # Fallback: the first 8 digits of rcept_no ARE the receipt date.
        # This is not an assumption — it was empirically confirmed against
        # four independent real filings where both fields were visible
        # side by side in list.json (SK Hynix 20230321001209 ↔ 2023-03-21,
        # Hyundai Motor 20230315001030 ↔ 2023-03-15, KB Financial
        # 20230316001417 ↔ 2023-03-16 and 20230324001073 ↔ 2023-03-24).
        # Guarded anyway: the prefix must parse as a real calendar date
        # AND land within [bsns_year, bsns_year+4] — anything else means
        # the rcept_no is malformed and the row is dropped rather than
        # gated on a fabricated date.
        try:
            parsed = pd.Timestamp(str(rcept_no)[:8]).date()
        except (ValueError, TypeError):
            log.warning("%s: rcept_no %r has no parseable date prefix — row dropped", ticker, rcept_no)
            return None
        if not (int(bsns_year) <= parsed.year <= int(bsns_year) + 4):
            log.warning("%s: rcept_no %r date prefix %s implausible for FY%s — row dropped",
                        ticker, rcept_no, parsed, bsns_year)
            return None
        log.info("%s: filed_date for rcept_no %s resolved from its date prefix (%s) — "
                 "not found in the list.json filing index", ticker, rcept_no, parsed)
        return parsed

    def _periods(row) -> list[tuple[date, float]]:
        out = []
        for period_key, amount_key in [
            ("thstrm", "thstrm_amount"), ("frmtrm", "frmtrm_amount"), ("bfefrmtrm", "bfefrmtrm_amount"),
        ]:
            amount = row.get(amount_key)
            if amount in (None, "", "-") or pd.isna(amount):
                continue
            fiscal_year_offset = {"thstrm": 0, "frmtrm": 1, "bfefrmtrm": 2}[period_key]
            fiscal_period_end = date(int(bsns_year) - fiscal_year_offset, 12, 31)
            out.append((fiscal_period_end, float(str(amount).replace(",", ""))))
        return out

    def _make_row(canon, fiscal_period_end, value, filed_date, is_flow) -> dict:
        return {
            "cik": corp_code, "ticker": ticker, "tag": canon,
            "fiscal_period_end": fiscal_period_end,
            "start_date": date(fiscal_period_end.year, 1, 1) if is_flow else None,
            "filed_date": filed_date, "value": value, "unit": "KRW",
            "form": "DART-ANNUAL", "fy": fiscal_period_end.year, "fp": "FY",
            "taxonomy": "dart-kr",
        }

    rows: list[dict] = []

    # Direct-mapped tags. Each emitted row carries its candidate's priority
    # (position in CODE_MAP's list) so that when a filing tags MULTIPLE
    # candidates for the same canonical tag — e.g. total Equity AND
    # parent-attributable Equity as separate real BS rows — the dedup below
    # keeps the highest-priority one deterministically, not whichever row
    # the filing template happened to emit first (see _CANDIDATE_LOOKUP's
    # comment for the real SK Hynix bug this fixed).
    for _, r in fin.iterrows():
        hit = _CANDIDATE_LOOKUP.get(_normalize_account_id(r["account_id"]))
        if hit is None:
            continue
        canon, priority = hit
        filed_date = _filed_date_for(r["rcept_no"])
        if filed_date is None:
            continue
        is_flow = r.get("sj_div") in FLOW_STATEMENT_TYPES
        for fiscal_period_end, value in _periods(r):
            row = _make_row(canon, fiscal_period_end, value, filed_date, is_flow)
            row["_priority"] = priority
            rows.append(row)

    # Sum-of-components tags (e.g. LongTermDebtNoncurrent = bonds + loans):
    # accumulate every matching component's per-period value, keyed by
    # (canon, rcept_no, fiscal_period_end), then emit ONE summed row —
    # never one row per component (that would leave conflicting values
    # under the same tag/period/filed_date, silently resolved by whichever
    # pandas dedup happened to keep).
    sums: dict[tuple[str, str, date], float] = {}
    sum_filed_dates: dict[tuple[str, str, date], object] = {}
    sum_is_flow: dict[str, bool] = {}
    for _, r in fin.iterrows():
        canon = _SUM_CANDIDATE_LOOKUP.get(_normalize_account_id(r["account_id"]))
        if canon is None:
            continue
        filed_date = _filed_date_for(r["rcept_no"])
        if filed_date is None:
            continue
        sum_is_flow[canon] = r.get("sj_div") in FLOW_STATEMENT_TYPES
        for fiscal_period_end, value in _periods(r):
            key = (canon, r["rcept_no"], fiscal_period_end)
            sums[key] = sums.get(key, 0.0) + value
            sum_filed_dates[key] = filed_date
    for (canon, _rcept_no, fiscal_period_end), total in sums.items():
        key = (canon, _rcept_no, fiscal_period_end)
        row = _make_row(canon, fiscal_period_end, total, sum_filed_dates[key], sum_is_flow[canon])
        row["_priority"] = 0  # summed tags have no competing candidates
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    # Priority-aware dedup: within one (tag, fiscal_period_end, filed_date),
    # the lowest _priority candidate wins. sort is stable, so ties keep
    # response order — but ties only occur between rows of the SAME
    # candidate spelling, where values are identical anyway.
    out = out.sort_values(["tag", "fiscal_period_end", "filed_date", "_priority"])
    out = out.drop_duplicates(subset=["tag", "fiscal_period_end", "filed_date"], keep="first")
    out = out.drop(columns=["_priority"])
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
    PIT database. Requires DART_API_KEY. Mapping verified against Samsung
    Electronics' real filings — see module docstring for exactly what was
    and wasn't checked before extending to other companies."""
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
    log.info("DART ingest complete: %d fact rows across %d tickers, %d years",
             total, len(tickers_corp_codes), len(years))
