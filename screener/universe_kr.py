"""KOSPI blue-chip crosswalk: ticker -> DART corp_code, sector.

*** INCOMPLETE BY DESIGN — see pit_fundamentals/dart_kr_client.py's module
docstring for why. *** Unlike screener/universe_br.py's 16-name crosswalk
(every CNPJ verified against real, freely-downloaded CVM filings before
being committed), DART requires a registered API key for even its free
company-code list, and none was available while this was built — so this
file contains exactly ONE entry whose corp_code is independently sourced
(quoted from a worked example in a Korean quant-investing tutorial, not
invented), and a documented procedure for populating the rest once you have
a key. Committing plausible-looking but unverified 8-digit corp_codes would
be worse than leaving them out: a wrong ID doesn't error, it just silently
returns another company's data or nothing at all.

To extend this list yourself once you have a DART_API_KEY:

    from pit_fundamentals.dart_kr_client import download_corp_codes, require_api_key
    codes = download_corp_codes(require_api_key())
    codes[codes["corp_name"].str.contains("SK하이닉스")]   # find the row you want
    # then add {"ticker": "000660", "corp_code": "<verified 8-digit code>", ...}
    # below, and confirm get_financial_statement() returns sane numbers
    # before trusting it in any score.
"""

from __future__ import annotations

# ticker (KRX 6-digit stock code) -> corp_code / name / sector.
# Samsung Electronics' corp_code (00126380) is quoted directly from a
# worked example in a published Korean quant-investing tutorial
# (hyunyulhenry.github.io/quant_cookbook), not invented — but it has not
# been re-verified against a live DART response in this session either.
# Confirm it yourself before trusting any score derived from it.
KR_BLUE_CHIPS: dict[str, dict[str, str]] = {
    "005930": {"corp_code": "00126380", "name": "Samsung Electronics", "sector": "Information Technology"},
}


def get_kr_blue_chips() -> dict[str, str]:
    """Return {ticker: corp_code} for run_dart_ingest()."""
    return {t: v["corp_code"] for t, v in KR_BLUE_CHIPS.items()}


def get_kr_sectors() -> dict[str, str]:
    return {t: v["sector"] for t, v in KR_BLUE_CHIPS.items()}
