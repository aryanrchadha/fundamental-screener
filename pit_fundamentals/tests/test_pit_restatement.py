"""The load-bearing test: proves point-in-time gating actually works.

A restatement must be invisible the day before it was filed and visible the
day after. We first look for a REAL restatement in the ingested EDGAR data
(data/pit.duckdb); if the database hasn't been built yet (e.g. CI on a clean
clone), we fall back to a clearly-labeled SYNTHETIC restatement fixture that
exercises exactly the same query path.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from pit_fundamentals.query import get_fact_as_of
from pit_fundamentals.schema import connect, init_db

REAL_DB = Path(__file__).resolve().parents[2] / "data" / "pit.duckdb"


def _find_real_restatement():
    """Search the ingested data for a (ticker, tag, period) whose restated
    value actually differs from the original filing."""
    con = connect(REAL_DB, read_only=True)
    try:
        rows = con.execute(
            """
            WITH grp AS (
                SELECT ticker, tag, fiscal_period_end,
                       count(*) AS n,
                       count(DISTINCT value) AS n_values,
                       min(filed_date) AS first_filed,
                       max(filed_date) AS last_filed
                FROM pit_facts
                GROUP BY 1, 2, 3
            )
            SELECT ticker, tag, fiscal_period_end, first_filed, last_filed
            FROM grp
            WHERE n_values > 1 AND first_filed < last_filed
            ORDER BY ticker, tag, fiscal_period_end
            LIMIT 20
            """
        ).fetchall()
        for ticker, tag, fpe, first_filed, last_filed in rows:
            orig = con.execute(
                """SELECT value FROM pit_facts
                   WHERE ticker=? AND tag=? AND fiscal_period_end=?
                   ORDER BY filed_date ASC LIMIT 1""",
                [ticker, tag, fpe],
            ).fetchone()[0]
            restated = con.execute(
                """SELECT value FROM pit_facts
                   WHERE ticker=? AND tag=? AND fiscal_period_end=?
                   ORDER BY filed_date DESC LIMIT 1""",
                [ticker, tag, fpe],
            ).fetchone()[0]
            if orig != restated:
                return ticker, tag, fpe, first_filed, last_filed, orig, restated
        return None
    finally:
        con.close()


@pytest.mark.skipif(not REAL_DB.exists(), reason="real PIT database not built yet")
def test_real_restatement_pit_gating():
    """REAL-DATA CASE: original value before the restatement's filing date,
    restated value after."""
    case = _find_real_restatement()
    if case is None:
        pytest.skip("no differing-value restatement found in ingested sample")
    ticker, tag, fpe, first_filed, last_filed, orig, restated = case

    before = get_fact_as_of(
        ticker, tag, as_of_date=last_filed - timedelta(days=1),
        fiscal_period_end=fpe, db_path=REAL_DB,
    )
    after = get_fact_as_of(
        ticker, tag, as_of_date=last_filed + timedelta(days=1),
        fiscal_period_end=fpe, db_path=REAL_DB,
    )
    assert after == pytest.approx(restated)
    # The day before the final filing we must see SOME earlier filing's value,
    # never the not-yet-public restated one (unless an interim filing already
    # matched it — excluded by the differing-value search above for the
    # two-filing case; for >2 filings we assert the strict inequality only
    # when exactly two filings exist).
    assert before is not None
    assert before != pytest.approx(restated) or first_filed == last_filed


def test_synthetic_restatement_pit_gating(tmp_path):
    """SYNTHETIC FIXTURE (clearly labeled): ACME restates FY2020 NetIncomeLoss
    from 100.0 (filed 2021-02-15) to 80.0 (filed 2021-11-30)."""
    db = tmp_path / "pit_synth.duckdb"
    con = connect(db)
    init_db(con)
    rows = pd.DataFrame(
        [
            # original 10-K filing
            dict(cik="0000000001", ticker="ACME", tag="NetIncomeLoss",
                 fiscal_period_end=date(2020, 12, 31), start_date=date(2020, 1, 1),
                 filed_date=date(2021, 2, 15), value=100.0, unit="USD",
                 form="10-K", fy=2020, fp="FY", is_restatement=False),
            # 10-K/A restatement, filed later, different value
            dict(cik="0000000001", ticker="ACME", tag="NetIncomeLoss",
                 fiscal_period_end=date(2020, 12, 31), start_date=date(2020, 1, 1),
                 filed_date=date(2021, 11, 30), value=80.0, unit="USD",
                 form="10-K/A", fy=2020, fp="FY", is_restatement=True),
        ]
    )
    con.register("_rows", rows)
    con.execute("INSERT INTO pit_facts SELECT * FROM _rows")
    con.close()

    fpe = date(2020, 12, 31)
    # Before the original filing: nothing was public yet.
    assert get_fact_as_of("ACME", "NetIncomeLoss", date(2021, 1, 1), fpe, db) is None
    # Day before the restatement was filed: the ORIGINAL value.
    assert get_fact_as_of("ACME", "NetIncomeLoss", date(2021, 11, 29), fpe, db) == 100.0
    # Day after the restatement was filed: the RESTATED value.
    assert get_fact_as_of("ACME", "NetIncomeLoss", date(2021, 12, 1), fpe, db) == 80.0
    # And without pinning the fiscal period, the latest-period path agrees.
    assert get_fact_as_of("ACME", "NetIncomeLoss", date(2021, 12, 1), None, db) == 80.0
