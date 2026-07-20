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
