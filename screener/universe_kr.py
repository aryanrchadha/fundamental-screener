"""KOSPI universe: ticker -> DART corp_code, industry group.

The universe lives in `screener/kospi_universe.csv` (tracked in git, not in
gitignored `data/`, so a clean clone reproduces the exact backtest universe
without needing an API key). It was built entirely from primary sources —
no ticker list was typed from memory:

  1. DART `list.json` with corp_cls='Y' over the FY2023 annual-report
     season returned the 784 KOSPI companies that actually file annual
     reports.
  2. Those were ranked by median daily traded value (close x volume) from
     Yahoo `.KS` daily history, 2014-2025; 726 had >=1500 trading days.
  3. The top 120 by liquidity form the universe. Liquidity — not index
     membership — is the selection rule because there is no free
     historical KOSPI-200 constituent table, and a liquidity screen is at
     least a stated, reproducible rule rather than an implicit one.
  4. Each company's `induty_code` came from DART `company.json`.

SECTOR GROUPING: `sector` is the 2-digit division of the Korean Standard
Industrial Classification (KSIC) — Korea's official statistical industry
classification, taken straight from DART. It is NOT GICS: GICS is licensed
and unavailable free, and inventing a KSIC->GICS crosswalk would be
fabricating a mapping. KSIC divisions serve the same purpose here, which
is a defensible peer group for sector-neutral z-scoring (e.g. KSIC-26 =
electronic components/computers/communications equipment holds Samsung
Electronics and SK Hynix together; KSIC-64 = financial services holds the
banks). Groups thinner than config.MIN_SECTOR_SIZE fall back to
universe-level z-scoring exactly as in the US path.

SURVIVORSHIP BIAS: like the S&P 500 default, this is a CURRENT list applied
backwards — companies that delisted or lost liquidity before 2024 are
absent, and the liquidity ranking itself is measured over the full sample.
The bias is real and is stated in FINDINGS.md rather than papered over.

The 21 hand-verified blue chips from the earlier build are a subset of this
list; their corp_codes were each confirmed against real filings, and the
remaining 99 were resolved by the same registry lookup and are held to the
same automated acceptance test (Assets = Liabilities + Equity, exactly).
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

UNIVERSE_CSV = Path(__file__).resolve().parent / "kospi_universe.csv"

# Companies whose corp_code and full tag mapping were verified by hand
# against real DART filings during the initial build (see FINDINGS.md).
HAND_VERIFIED = {
    "005930", "000660", "373220", "005380", "005490", "035420", "000270",
    "051910", "006400", "035720", "105560", "055550", "012330", "068270",
    "096770", "017670", "015760", "032830", "066570", "003550", "090430",
}

# Financial institutions file liquidity-order balance sheets with no
# current/non-current split, so every working-capital-dependent score
# excludes them automatically via missing tags — the same principled
# exclusion as the US and Brazil paths, reached by a third mechanism.
FINANCIAL_KSIC_DIVISIONS = {"64", "65", "66"}


@functools.lru_cache(maxsize=1)
def load_universe() -> pd.DataFrame:
    df = pd.read_csv(UNIVERSE_CSV, dtype={"ticker": str, "corp_code": str,
                                          "induty_code": str, "sector": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    df["corp_code"] = df["corp_code"].str.zfill(8)
    return df


def get_kr_blue_chips() -> dict[str, str]:
    """{ticker: corp_code} for run_dart_ingest()."""
    return dict(zip(load_universe()["ticker"], load_universe()["corp_code"]))


def get_kr_sectors() -> dict[str, str]:
    return dict(zip(load_universe()["ticker"], load_universe()["sector"]))


def get_kr_names() -> dict[str, str]:
    return dict(zip(load_universe()["ticker"], load_universe()["name"]))


def is_financial(ticker: str) -> bool:
    row = load_universe().set_index("ticker")
    if ticker not in row.index:
        return False
    return str(row.loc[ticker, "sector"]).removeprefix("KSIC-") in FINANCIAL_KSIC_DIVISIONS


LISTING_DATES_CSV = Path(__file__).resolve().parent / "kospi_listing_dates.csv"


@functools.lru_cache(maxsize=1)
def build_kr_membership() -> pd.DataFrame:
    """Point-in-time listing history, in the [ticker, start, end] shape
    `screener.universe.was_member` expects.

    `start` is the date of each company's FIRST KOSPI annual report (pulled
    per-company from DART's own filing index). Thirteen of the 120 names
    were not yet KOSPI filers in 2016 — Samsung Biologics, Woori Financial
    Group, the HD Hyundai spin-offs, Netmarble and others — so a static
    universe silently assumes they existed years before they did.

    `end` is NaT for every name: all 120 are still filing, by construction
    of how the universe was selected.

    *** THIS CORRECTS LOOK-AHEAD, NOT DELISTING SURVIVORSHIP. *** The
    distinction is load-bearing and was established empirically, not
    assumed:

      * DART's `corp_cls` is a CURRENT attribute, not a historical one.
        Querying the filing index with corp_cls='Y' returns 684 KOSPI
        filers for 2016 and reports ZERO of them missing by 2025 — an
        impossible delisting rate that is purely an artefact of the filter
        excluding anything since reclassified. Dropping the filter shows
        2,097 companies filed annual reports in that window, of which 406
        now carry class 'E'.
      * Those reclassified names cannot be priced anyway: Yahoo returned
        usable `.KS` history for only 4 of a 40-name sample (10%), because
        it drops delisted KRX tickers.

    So the surviving bias is stated and quantified in FINDINGS.md rather
    than silently corrected with data that does not exist.
    """
    df = pd.read_csv(LISTING_DATES_CSV, dtype={"ticker": str})
    df["ticker"] = df["ticker"].str.zfill(6)
    return pd.DataFrame({
        "ticker": df["ticker"],
        "start": pd.to_datetime(df["first_annual_filing"]),
        "end": pd.NaT,
    })
