"""Tests for the South Korea/DART taxonomy adapter.

Fixtures below are synthetic (no network access during test runs), but the
CODE_MAP/SUM_CODE_MAP mapping choices and the sj_div-filtering logic they
exercise have since been confirmed against a live DART API key — see
dart_kr_client.py's module docstring for the real Samsung Electronics
verification (Assets = Liabilities + Equity exactly; O-Score computed
end-to-end). Two of the tests below (SCE exclusion, long-term-debt
summing) are direct regression tests for real bugs that verification pass
caught. Field names (account_id, rcept_no, rcept_dt, thstrm_amount, ...)
are taken from DART's official developer guide and the real response
structure observed during that live verification.
"""

from datetime import date

import pandas as pd
import pytest

from pit_fundamentals.dart_kr_client import (
    _normalize_account_id,
    _parse_dart_number,
    facts_from_dataframes,
    require_api_key,
)


def test_normalize_strips_all_documented_prefix_variants():
    """DartLab (an independent project built specifically to solve this)
    documents the same concept tagged three different ways across real
    filers: ifrs-full_Revenue (Samsung), dart_Revenue (SK Hynix), bare
    Revenue (LG Energy Solution). All three must normalize identically."""
    assert _normalize_account_id("ifrs-full_Revenue") == "revenue"
    assert _normalize_account_id("dart_Revenue") == "revenue"
    assert _normalize_account_id("Revenue") == "revenue"
    assert _normalize_account_id("ifrs_Revenue") == "revenue"
    assert _normalize_account_id("ifrs-smes_Revenue") == "revenue"


def _fin_row(account_id, sj_div, thstrm, frmtrm, bfefrmtrm, rcept_no="20240101000001"):
    return dict(
        rcept_no=rcept_no, reprt_code="11011", bsns_year="2023", corp_code="00000001",
        sj_div=sj_div, sj_nm="test", account_id=account_id, account_nm="test account",
        thstrm_nm="제 1 기", thstrm_amount=thstrm, frmtrm_nm="제 0 기", frmtrm_amount=frmtrm,
        bfefrmtrm_nm="제 -1 기", bfefrmtrm_amount=bfefrmtrm, currency="KRW",
    )


@pytest.fixture
def fin_df():
    return pd.DataFrame(
        [
            _fin_row("ifrs-full_Assets", "BS", "1000", "900", "800"),
            _fin_row("ifrs-full_CurrentAssets", "BS", "400", "350", "300"),
            _fin_row("dart_Revenue", "IS", "500", "450", "400"),  # non-ifrs-full prefix, must still map
            _fin_row("ProfitLoss", "IS", "50", "40", "30"),  # bare, no prefix at all
        ]
    )


@pytest.fixture
def filings_df():
    return pd.DataFrame(
        [dict(corp_code="00000001", rcept_no="20240101000001",
              rcept_dt=date(2024, 3, 15), report_nm="사업보고서 (2023.12)")]
    )


def test_prefix_variants_all_map_to_canonical_tags(fin_df, filings_df):
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin_df, filings_df)
    tags = set(facts["tag"])
    assert {"Assets", "AssetsCurrent", "Revenues", "NetIncomeLoss"} <= tags
    # dart_Revenue and bare ProfitLoss (no ifrs-full_ prefix) must have mapped.
    rev = facts[(facts["tag"] == "Revenues") & (facts["fiscal_period_end"] == date(2023, 12, 31))]
    assert rev["value"].iloc[0] == 500.0


def test_three_period_expansion_thstrm_frmtrm_bfefrmtrm(fin_df, filings_df):
    """Each DART row reports THREE fiscal years (current, prior,
    two-prior) in one response — must expand to three fiscal_period_end
    rows, all gated by the SAME filed_date (they became public together)."""
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin_df, filings_df)
    assets = facts[facts["tag"] == "Assets"].sort_values("fiscal_period_end")
    assert list(assets["fiscal_period_end"]) == [date(2021, 12, 31), date(2022, 12, 31), date(2023, 12, 31)]
    assert list(assets["value"]) == [800.0, 900.0, 1000.0]
    assert (assets["filed_date"] == date(2024, 3, 15)).all()


def test_flow_tags_get_start_date_instant_tags_dont(fin_df, filings_df):
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin_df, filings_df)
    assets_row = facts[(facts["tag"] == "Assets") & (facts["fiscal_period_end"] == date(2023, 12, 31))].iloc[0]
    revenue_row = facts[(facts["tag"] == "Revenues") & (facts["fiscal_period_end"] == date(2023, 12, 31))].iloc[0]
    assert assets_row["start_date"] is None
    assert revenue_row["start_date"] == date(2023, 1, 1)


def test_row_with_unresolvable_rcept_no_is_dropped_not_guessed():
    """If a fact's rcept_no isn't in the filing index, its filed_date is
    genuinely unknown — must be dropped, never defaulted to some other
    filing's date."""
    fin = pd.DataFrame([_fin_row("ifrs-full_Assets", "BS", "1000", "900", "800", rcept_no="99999999999999")])
    filings = pd.DataFrame(
        [dict(corp_code="00000001", rcept_no="20240101000001",
              rcept_dt=date(2024, 3, 15), report_nm="사업보고서 (2023.12)")]
    )
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin, filings)
    assert facts.empty


def test_synthetic_restatement_pit_gating():
    """Two filings for the same fiscal year with different rcept_no,
    rcept_dt, and value — the later one is a restatement, analogous to the
    real Agilent (EDGAR) and Banco do Brasil (CVM) cases."""
    fin = pd.DataFrame(
        [
            _fin_row("ifrs-full_Assets", "BS", "1000", "900", "800", rcept_no="20240101000001"),
            _fin_row("ifrs-full_Assets", "BS", "1050", "900", "800", rcept_no="20240101000002"),
        ]
    )
    filings = pd.DataFrame(
        [
            dict(corp_code="00000001", rcept_no="20240101000001",
                 rcept_dt=date(2024, 3, 15), report_nm="사업보고서 (2023.12)"),
            dict(corp_code="00000001", rcept_no="20240101000002",
                 rcept_dt=date(2024, 6, 1), report_nm="[정정]사업보고서 (2023.12)"),
        ]
    )
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin, filings)
    curr = facts[(facts["tag"] == "Assets") & (facts["fiscal_period_end"] == date(2023, 12, 31))]
    assert set(curr["value"]) == {1_000.0, 1_050.0}
    original = curr[curr["filed_date"] == date(2024, 3, 15)]
    restated = curr[curr["filed_date"] == date(2024, 6, 1)]
    assert not original["is_restatement"].iloc[0]
    assert restated["is_restatement"].iloc[0]


def test_require_api_key_raises_actionable_error_when_unset(monkeypatch):
    monkeypatch.delenv("DART_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DART_API_KEY"):
        require_api_key()


def test_require_api_key_returns_key_when_set(monkeypatch):
    monkeypatch.setenv("DART_API_KEY", "test_key_value")
    assert require_api_key() == "test_key_value"


def test_sce_rows_excluded_even_though_account_id_matches(filings_df):
    """Regression test for a real bug caught against Samsung Electronics'
    live FY2023 filing: the Statement of Changes in Equity (sj_div='SCE')
    tags SEVEN different real values under the identical account_id
    'ifrs-full_Equity' — total equity, per-component balances, and
    NCI-attributable vs. parent-attributable subtotals. Including SCE rows
    produced silently conflicting StockholdersEquity facts for the same
    (tag, fiscal_period_end). Only BS/IS/CF may ever be mapped."""
    fin = pd.DataFrame(
        [
            _fin_row("ifrs-full_Equity", "BS", "1000", "900", "800"),  # the one authoritative total
            _fin_row("ifrs-full_Equity", "SCE", "300", "270", "240"),  # e.g. a capital-surplus sub-component
            _fin_row("ifrs-full_Equity", "SCE", "700", "630", "560"),  # e.g. NCI-attributable sub-component
        ]
    )
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin, filings_df)
    equity = facts[facts["tag"] == "StockholdersEquity"]
    # 3 rows expected (one per fiscal year from thstrm/frmtrm/bfefrmtrm
    # expansion of the single BS row) — NOT 9 (which would include the two
    # excluded SCE rows' own 3-period expansions), and the values must be
    # exactly the BS figures, never the SCE sub-component figures.
    assert len(equity) == 3
    assert set(equity["value"]) == {800.0, 900.0, 1000.0}


def test_equity_candidate_priority_beats_response_order(filings_df):
    """Regression test for a real bug caught in the 20-company live sweep:
    SK Hynix's FY2022 and FY2023 balance sheets both carry
    ifrs-full_Equity (total, incl NCI) AND
    ifrs-full_EquityAttributableToOwnersOfParent as separate rows, and the
    template's ROW ORDER flipped between years. Resolving the collision by
    response order kept parent-only equity for FY2022 (breaking
    Assets = Liabilities + Equity by exactly the NCI amount). The
    higher-priority candidate (total Equity, first in CODE_MAP's list)
    must win regardless of which row the filing emits first."""
    # Parent-attributable row FIRST — the FY2022-style ordering that broke.
    fin = pd.DataFrame(
        [
            _fin_row("ifrs-full_EquityAttributableToOwnersOfParent", "BS", "63266", "60000", "58000"),
            _fin_row("ifrs-full_Equity", "BS", "63290", "60020", "58015"),
        ]
    )
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin, filings_df)
    eq = facts[(facts["tag"] == "StockholdersEquity") & (facts["fiscal_period_end"] == date(2023, 12, 31))]
    assert len(eq) == 1
    assert eq["value"].iloc[0] == 63290.0  # the TOTAL, not the parent-only row

    # And the reverse ordering (FY2023-style) must give the same answer.
    fin_rev = pd.DataFrame(
        [
            _fin_row("ifrs-full_Equity", "BS", "63290", "60020", "58015"),
            _fin_row("ifrs-full_EquityAttributableToOwnersOfParent", "BS", "63266", "60000", "58000"),
        ]
    )
    facts_rev = facts_from_dataframes("TEST", "00000001", "2023", fin_rev, filings_df)
    eq_rev = facts_rev[(facts_rev["tag"] == "StockholdersEquity") & (facts_rev["fiscal_period_end"] == date(2023, 12, 31))]
    assert eq_rev["value"].iloc[0] == 63290.0


def test_single_statement_filers_income_statement_lives_in_cis(filings_df):
    """Regression test for a real bug caught in the live sweep: SK Hynix,
    NAVER, Kakao, and Amorepacific present a SINGLE combined statement of
    comprehensive income — their entire income statement (Revenue,
    ProfitLoss, ...) is under sj_div='CIS' with no 'IS' section at all. An
    earlier revision excluded CIS entirely (correct for Samsung's
    two-statement format, fatal for these filers)."""
    fin = pd.DataFrame(
        [
            _fin_row("ifrs-full_Assets", "BS", "1000", "900", "800"),
            _fin_row("ifrs-full_Revenue", "CIS", "500", "450", "400"),
            _fin_row("ifrs-full_ProfitLoss", "CIS", "50", "40", "30"),
        ]
    )
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin, filings_df)
    rev = facts[(facts["tag"] == "Revenues") & (facts["fiscal_period_end"] == date(2023, 12, 31))]
    ni = facts[(facts["tag"] == "NetIncomeLoss") & (facts["fiscal_period_end"] == date(2023, 12, 31))]
    assert rev["value"].iloc[0] == 500.0
    assert ni["value"].iloc[0] == 50.0
    # CIS rows are flow facts — they must carry a start_date for the
    # annual-duration filter in query.py.
    assert rev["start_date"].iloc[0] == date(2023, 1, 1)


def test_filed_date_falls_back_to_rcept_no_date_prefix():
    """Regression test for a real bug caught in the live sweep: for FY2022,
    DART served Hyundai Motor's and Kakao's figures from documents received
    in March 2024 (year+2), outside the original Jan-Jun year+1 filing
    search window — those rows were silently dropped. The first 8 digits of
    rcept_no ARE the receipt date (empirically confirmed on four real
    filings), so an index miss now falls back to the validated prefix."""
    fin = pd.DataFrame(
        [_fin_row("ifrs-full_Assets", "BS", "1000", "900", "800", rcept_no="20240314001531")]
    )
    empty_filings = pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm"])
    facts = facts_from_dataframes("TEST", "00000001", "2022", fin, empty_filings)
    assert not facts.empty
    assert (facts["filed_date"] == date(2024, 3, 14)).all()


def test_implausible_rcept_no_prefix_still_dropped():
    """The prefix fallback is guarded: a date outside [bsns_year,
    bsns_year+4] means the rcept_no is malformed — drop, don't gate on it."""
    fin = pd.DataFrame(
        [_fin_row("ifrs-full_Assets", "BS", "1000", "900", "800", rcept_no="20500101000001")]
    )
    empty_filings = pd.DataFrame(columns=["corp_code", "rcept_no", "rcept_dt", "report_nm"])
    facts = facts_from_dataframes("TEST", "00000001", "2022", fin, empty_filings)
    assert facts.empty


def test_long_term_debt_summed_from_bonds_and_loans(filings_df):
    """Regression test mirroring the real Samsung structure: IFRS has no
    single 'long-term debt' line — non-current bonds and non-current loans
    are separate BS rows (confirmed real tags:
    NoncurrentPortionOfNoncurrentBondsIssued +
    NoncurrentPortionOfNoncurrentLoansReceived). LongTermDebtNoncurrent
    must be their SUM, not one component silently dropped by dedup."""
    fin = pd.DataFrame(
        [
            _fin_row("ifrs-full_NoncurrentPortionOfNoncurrentBondsIssued", "BS", "537", "536", "508"),
            _fin_row("ifrs-full_NoncurrentPortionOfNoncurrentLoansReceived", "BS", "3724", "3560", "2866"),
        ]
    )
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin, filings_df)
    debt = facts[facts["tag"] == "LongTermDebtNoncurrent"].sort_values("fiscal_period_end")
    assert list(debt["value"]) == [pytest.approx(508 + 2866), pytest.approx(536 + 3560), pytest.approx(537 + 3724)]


# ---------------------------------------------------------------------------
# Share counts (stockTotqySttus). Fixture labels below are the REAL `se`
# spellings observed across the 21-name KOSPI sweep — see COMMON_STOCK_LABEL's
# comment in dart_kr_client.py.
# ---------------------------------------------------------------------------

def _share_row(se, istc, tes, distb, rcept_no="20240101000001", stlm="2023-12-31"):
    return dict(
        rcept_no=rcept_no, corp_cls="Y", corp_code="00000001", corp_name="TESTCO",
        se=se, isu_stock_totqy="20,000,000,000", now_to_isu_stock_totqy="-",
        now_to_dcrs_stock_totqy="-", redc="-", profit_incnr="-", rdmstk_repy="-",
        etc="-", istc_totqy=istc, tesstk_co=tes, distb_stock_co=distb, stlm_dt=stlm,
    )


def _shares_only(shares_df, filings_df, bsns_year="2023"):
    """Run the transform with no financial-statement rows at all."""
    return facts_from_dataframes(
        "TEST", "00000001", bsns_year, pd.DataFrame(), filings_df, shares=shares_df
    )


def test_parse_dart_number_handles_commas_and_dashes():
    assert _parse_dart_number("5,969,782,550") == 5_969_782_550.0
    assert _parse_dart_number("-") is None      # absent, NOT zero
    assert _parse_dart_number("") is None
    assert _parse_dart_number(None) is None
    assert _parse_dart_number("주9)") is None   # a 비고 footnote marker


@pytest.mark.parametrize(
    "label",
    [
        "보통주",                    # Samsung, Celltrion, most filers
        "의결권 있는 보통주",          # voting common
        "의결권 있는\n보통주",         # Shinhan — embedded newline
        "의결권 있는 주식\n(보통주)",   # LG Electronics — parenthesised
    ],
)
def test_all_real_common_stock_label_variants_map(label, filings_df):
    """Every `se` spelling for common stock seen in the live 21-name sweep
    must resolve. Exact-equality matching (the first implementation) silently
    produced NO share count for Shinhan and LG Electronics."""
    shares = pd.DataFrame(
        [
            _share_row(label, "163,647,814", "763,176", "162,884,638"),
            _share_row("합계", "180,833,806", "767,869", "180,065,937"),
            _share_row("비고", "-", "-", "-"),
        ]
    )
    facts = _shares_only(shares, filings_df)
    got = facts[facts["tag"] == "CommonStockSharesOutstanding"]
    assert len(got) == 1
    assert got["value"].iloc[0] == 162_884_638.0   # common, already net of treasury
    assert got["unit"].iloc[0] == "shares"


def test_preferred_and_class_shares_never_mapped(filings_df):
    """'우선주' (preferred) and Amorepacific's '종류주' (class share) must not
    be mistaken for common — and the 합계 total (which BUNDLES preferred) must
    not win either: Hyundai Motor's real common 202.3M vs total 261.3M is a
    23% difference that would badly distort dilution and market cap."""
    shares = pd.DataFrame(
        [
            _share_row("보통주", "203,830,910", "-", "202,259,505"),
            _share_row("의결권 없는 우선주", "59,048,998", "-", "59,048,998"),
            _share_row("종류주", "10,557,830", "6,217", "10,551,613"),
            _share_row("합계", "262,879,908", "-", "261,308,503"),
            _share_row("비고", "-", "-", "-"),
        ]
    )
    facts = _shares_only(shares, filings_df)
    got = facts[facts["tag"] == "CommonStockSharesOutstanding"]
    assert len(got) == 1
    assert got["value"].iloc[0] == 202_259_505.0


def test_share_count_is_instant_fact_dated_from_stlm_dt(filings_df):
    """A share count is a point-in-time balance, not a flow: no start_date,
    and its fiscal_period_end comes from the response's own stlm_dt."""
    shares = pd.DataFrame([_share_row("보통주", "100", "0", "100", stlm="2023-12-31")])
    facts = _shares_only(shares, filings_df)
    row = facts[facts["tag"] == "CommonStockSharesOutstanding"].iloc[0]
    assert row["start_date"] is None
    assert row["fiscal_period_end"] == date(2023, 12, 31)
    assert row["filed_date"] == date(2024, 3, 15)   # gated like every other fact


def test_missing_common_share_count_excluded_not_zeroed(filings_df, caplog):
    """A '-' outstanding count means 'not reported', never 'zero shares'."""
    shares = pd.DataFrame([_share_row("보통주", "-", "-", "-")])
    with caplog.at_level("WARNING"):
        facts = _shares_only(shares, filings_df)
    assert facts.empty
    assert any("distb_stock_co" in r.message for r in caplog.records)


def test_no_common_class_at_all_warns_and_excludes(filings_df, caplog):
    shares = pd.DataFrame(
        [_share_row("우선주", "100", "0", "100"), _share_row("비고", "-", "-", "-")]
    )
    with caplog.at_level("WARNING"):
        facts = _shares_only(shares, filings_df)
    assert facts.empty
    assert any("no share class matching" in r.message for r in caplog.records)


def test_shares_merge_with_financial_statement_facts(filings_df, fin_df):
    """Share facts and statement facts land in one frame under the shared
    schema — the whole point of routing a second endpoint through the same
    canonical-tag contract."""
    shares = pd.DataFrame([_share_row("보통주", "100", "0", "100")])
    facts = facts_from_dataframes("TEST", "00000001", "2023", fin_df, filings_df, shares=shares)
    tags = set(facts["tag"])
    assert {"Assets", "Revenues", "CommonStockSharesOutstanding"} <= tags
    assert facts["taxonomy"].eq("dart-kr").all()
