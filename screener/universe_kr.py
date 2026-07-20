"""KOSPI blue-chip crosswalk: ticker -> DART corp_code, sector.

Every corp_code below was resolved from DART's OWN corpCode registry
(pit_fundamentals.dart_kr_client.download_corp_codes — 118,508 entities,
3,977 listed) by matching the 6-digit KRX stock code, with the registry's
Korean and English company names confirming each match. None are from
memory or guesswork. Every non-financial entry was then LIVE-VERIFIED by
pulling its real FY2022-2023 fnlttSinglAcntAll statements and asserting
the accounting identity Assets = Liabilities + StockholdersEquity holds
exactly (37/40 company-years pass; see the FY2022-financials note below
for the other three).

Two facts about financial institutions (KB, Shinhan, Samsung Life),
learned from the live sweep rather than assumed:

  * DART's fnlttSinglAcntAll returns status 013 ("no data") for all three
    in FY2022, consolidated and standalone alike — the endpoint's
    documented historical exclusion of financial institutions; their
    coverage begins with FY2023.
  * From FY2023 onward they DO return data, but as liquidity-order IFRS
    balance sheets with no current/non-current split — no
    AssetsCurrent/LiabilitiesCurrent, so Ohlson O-Score (which needs
    working capital and CL/CA) excludes them automatically via missing
    tags. Same principled financial-institution exclusion as the US and
    Brazil pipelines, arrived at through a third distinct mechanism.

They are kept in the crosswalk deliberately: they exercise that exclusion
path, and their Assets/Liabilities/Equity/NetIncomeLoss/CFO facts are
still valid PIT data for anything that doesn't need a classified balance
sheet.

Sector labels are GICS-style approximations for sector-neutral z-scoring
(the demo grouping), not licensed GICS assignments.
"""

from __future__ import annotations

# ticker (KRX 6-digit stock code) -> corp_code / name / sector.
KR_BLUE_CHIPS: dict[str, dict[str, str]] = {
    "005930": {"corp_code": "00126380", "name": "Samsung Electronics", "sector": "Information Technology"},
    "000660": {"corp_code": "00164779", "name": "SK Hynix", "sector": "Information Technology"},
    "373220": {"corp_code": "01515323", "name": "LG Energy Solution", "sector": "Industrials"},
    "005380": {"corp_code": "00164742", "name": "Hyundai Motor", "sector": "Consumer Discretionary"},
    "005490": {"corp_code": "00155319", "name": "POSCO Holdings", "sector": "Materials"},
    "035420": {"corp_code": "00266961", "name": "NAVER", "sector": "Communication Services"},
    "000270": {"corp_code": "00106641", "name": "Kia", "sector": "Consumer Discretionary"},
    "051910": {"corp_code": "00356361", "name": "LG Chem", "sector": "Materials"},
    "006400": {"corp_code": "00126362", "name": "Samsung SDI", "sector": "Information Technology"},
    "035720": {"corp_code": "00258801", "name": "Kakao", "sector": "Communication Services"},
    "105560": {"corp_code": "00688996", "name": "KB Financial Group", "sector": "Financials"},
    "055550": {"corp_code": "00382199", "name": "Shinhan Financial Group", "sector": "Financials"},
    "012330": {"corp_code": "00164788", "name": "Hyundai Mobis", "sector": "Consumer Discretionary"},
    "068270": {"corp_code": "00413046", "name": "Celltrion", "sector": "Health Care"},
    "096770": {"corp_code": "00631518", "name": "SK Innovation", "sector": "Energy"},
    "017670": {"corp_code": "00159023", "name": "SK Telecom", "sector": "Communication Services"},
    "015760": {"corp_code": "00159193", "name": "KEPCO", "sector": "Utilities"},
    "032830": {"corp_code": "00126256", "name": "Samsung Life Insurance", "sector": "Financials"},
    "066570": {"corp_code": "00401731", "name": "LG Electronics", "sector": "Consumer Discretionary"},
    "003550": {"corp_code": "00120021", "name": "LG Corp", "sector": "Industrials"},
    "090430": {"corp_code": "00583424", "name": "Amorepacific", "sector": "Consumer Staples"},
}

# Liquidity-order balance sheets (no current/non-current split), so scores
# needing working capital exclude them automatically via missing tags.
EXPECTED_FINANCIAL_FILERS = {"105560", "055550", "032830"}


def get_kr_blue_chips() -> dict[str, str]:
    """Return {ticker: corp_code} for run_dart_ingest()."""
    return {t: v["corp_code"] for t, v in KR_BLUE_CHIPS.items()}


def get_kr_sectors() -> dict[str, str]:
    return {t: v["sector"] for t, v in KR_BLUE_CHIPS.items()}
