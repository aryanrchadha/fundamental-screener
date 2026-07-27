"""Tests for the India adapter (BSE filing dates + Yahoo values).

Fixtures are synthetic, but every shape they encode was taken from real
responses: BSE's announcement timestamps for Reliance (scrip 500325) and
Yahoo's `.NS` statement row labels. The behaviours guarded here are the
ones that would fail silently in production.
"""

from datetime import date

import pandas as pd
import pytest

from pit_fundamentals.india_client import (
    MAX_DAYS_PERIOD_END_TO_FILING,
    YF_BALANCE_SHEET_MAP,
    facts_from_sources,
)


def _statements(period_ends, *, gross_equity=True, extra_bs=None):
    cols = [pd.Timestamp(p) for p in period_ends]
    bs_rows = {
        "Total Assets": [1000.0] * len(cols),
        "Current Assets": [400.0] * len(cols),
        "Current Liabilities": [200.0] * len(cols),
        "Total Liabilities Net Minority Interest": [600.0] * len(cols),
        "Retained Earnings": [250.0] * len(cols),
        "Ordinary Shares Number": [100.0] * len(cols),
    }
    bs_rows["Total Equity Gross Minority Interest" if gross_equity
            else "Stockholders Equity"] = [400.0] * len(cols)
    if extra_bs:
        bs_rows.update({k: [v] * len(cols) for k, v in extra_bs.items()})
    return {
        "bs": pd.DataFrame(bs_rows, index=cols).T,
        "is": pd.DataFrame({"Total Revenue": [800.0] * len(cols),
                            "Net Income": [90.0] * len(cols),
                            "EBIT": [120.0] * len(cols)}, index=cols).T,
        "cf": pd.DataFrame({"Operating Cash Flow": [150.0] * len(cols)}, index=cols).T,
    }


def _filings(dates):
    return pd.DataFrame({"filed_date": [date.fromisoformat(d) for d in dates],
                         "headline": ["Audited Financial Results"] * len(dates)})


def test_values_are_gated_by_the_real_bse_filing_date():
    """The whole contribution of this adapter: Yahoo supplies the numbers
    but no filing date, BSE supplies the date but not machine-readable
    numbers. Joined, a period's facts carry the date its results were
    actually disseminated — Reliance's FY2024 on 2024-04-22, ~22 days after
    the 31 March year end."""
    st = _statements(["2024-03-31"])
    f = facts_from_sources("RELIANCE", "500325", st, _filings(["2024-04-22"]))
    assert not f.empty
    assert set(f["filed_date"]) == {date(2024, 4, 22)}
    assert set(f["fiscal_period_end"]) == {date(2024, 3, 31)}
    assert (f["filed_date"] > f["fiscal_period_end"]).all()   # never pre-dated


def test_period_with_no_subsequent_filing_is_dropped_not_guessed():
    """A fiscal period Yahoo reports but BSE never announced has no
    knowable publication date, so it cannot be point-in-time gated and is
    excluded — the same 'never fabricate' rule the other adapters follow."""
    st = _statements(["2024-03-31", "2025-03-31"])
    f = facts_from_sources("X", "1", st, _filings(["2024-04-22"]))   # nothing after FY2025
    assert set(f["fiscal_period_end"]) == {date(2024, 3, 31)}


def test_filing_far_beyond_the_reporting_deadline_is_refused():
    """SEBI requires audited annual results within 60 days of year end. An
    announcement much later is reporting some OTHER period; gating on it
    would attach a fabricated date."""
    st = _statements(["2024-03-31"])
    too_late = date(2024, 3, 31).toordinal() + MAX_DAYS_PERIOD_END_TO_FILING + 30
    f = facts_from_sources("X", "1", st, _filings([date.fromordinal(too_late).isoformat()]))
    assert f.empty


def test_earliest_qualifying_filing_wins():
    """A period becomes public at its FIRST announcement, not a later one."""
    st = _statements(["2024-03-31"])
    f = facts_from_sources("X", "1", st, _filings(["2024-04-22", "2024-05-30"]))
    assert set(f["filed_date"]) == {date(2024, 4, 22)}


def test_equity_uses_gross_row_so_balance_sheet_closes():
    """Yahoo's 'Stockholders Equity' is parent-only; using it leaves a hole
    exactly the size of the noncontrolling interest (₹181,836 crore on real
    Reliance FY2026). The gross row closes Assets = Liabilities + Equity,
    and matches the Korean adapter's choice of total over parent equity."""
    assert YF_BALANCE_SHEET_MAP["Total Equity Gross Minority Interest"] == "StockholdersEquity"
    f = facts_from_sources("X", "1", _statements(["2024-03-31"]), _filings(["2024-04-22"]))
    v = f.set_index("tag")["value"]
    assert v["Assets"] == pytest.approx(v["Liabilities"] + v["StockholdersEquity"])


def test_parent_equity_used_only_when_gross_row_absent():
    """A filer with no subsidiaries has no NCI row at all, and there
    parent-only equity IS total equity."""
    st = _statements(["2024-03-31"], gross_equity=False)
    f = facts_from_sources("X", "1", st, _filings(["2024-04-22"]))
    v = f.set_index("tag")["value"]
    assert v["StockholdersEquity"] == 400.0


def test_flow_facts_get_annual_duration_instants_do_not():
    """Income/cash-flow facts need a ~1-year start_date so query.py's
    annual-duration filter accepts them; balance-sheet facts must not have
    one, and instead qualify via the BSE-ANNUAL form."""
    f = facts_from_sources("X", "1", _statements(["2024-03-31"]), _filings(["2024-04-22"]))
    rev = f[f["tag"] == "Revenues"].iloc[0]
    assets = f[f["tag"] == "Assets"].iloc[0]
    assert assets["start_date"] is None
    assert (rev["fiscal_period_end"] - rev["start_date"]).days >= 300
    assert set(f["form"]) == {"BSE-ANNUAL"}


def test_restatement_flag_is_always_false_and_that_is_deliberate():
    """Yahoo serves ONE current value per period, so an original-vs-restated
    distinction cannot exist. Recording False is honest; inventing a
    restatement history would not be. This is the documented respect in
    which India's PIT guarantee is weaker than EDGAR/CVM/DART."""
    f = facts_from_sources("X", "1", _statements(["2024-03-31"]), _filings(["2024-04-22"]))
    assert not f["is_restatement"].any()


def test_no_bse_filings_at_all_yields_nothing(caplog):
    with caplog.at_level("WARNING"):
        f = facts_from_sources("X", "1", _statements(["2024-03-31"]), pd.DataFrame())
    assert f.empty
    assert any("no BSE results announcements" in r.message for r in caplog.records)


def test_bse_annual_form_is_registered_for_instant_facts():
    """Regression test for a real bug: query.py gated instant facts on a
    hardcoded list of forms, so every Indian balance-sheet fact was silently
    dropped and snapshots came back with revenue but no assets — zero
    computable scores, no error."""
    from pit_fundamentals.query import ANNUAL_FORM_EXACT

    assert "BSE-ANNUAL" in ANNUAL_FORM_EXACT


def test_india_universe_csv_is_well_formed():
    from screener.universe_in import get_in_universe, load_universe

    u = load_universe()
    assert len(u) == 100
    assert u["ticker"].is_unique and u["bse_scrip"].is_unique
    assert u["bse_scrip"].str.fullmatch(r"\d{6}").all()   # BSE 6-digit scrip codes
    assert set(get_in_universe()) == set(u["ticker"])
