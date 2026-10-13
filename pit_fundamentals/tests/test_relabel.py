"""Facts filed under a ticker the source has since renamed must follow the
company to its current ticker, without re-downloading anything."""

import duckdb

from pit_fundamentals.ingest import relabel_if_stale
from pit_fundamentals.schema import init_db


def _db_with(rows):
    con = duckdb.connect(":memory:")
    init_db(con)
    for cik, ticker in rows:
        con.execute("INSERT INTO ingest_log VALUES (?, ?, 1, now())", [cik, ticker])
        con.execute("INSERT INTO pit_facts (cik, ticker, tag) VALUES (?, ?, 'Assets')", [cik, ticker])
    return con


def test_stale_ticker_is_relabelled_to_the_current_one():
    con = _db_with([("0001067983", "BRKB")])
    assert relabel_if_stale(con, "0001067983", "BRK-B", {"BRK-B", "AAPL"}) == "BRKB"
    assert con.execute("SELECT DISTINCT ticker FROM pit_facts").fetchall() == [("BRK-B",)]
    assert con.execute("SELECT ticker FROM ingest_log").fetchall() == [("BRK-B",)]


def test_a_still_requested_sister_class_keeps_its_facts():
    con = _db_with([("0000920760", "LEN")])
    assert relabel_if_stale(con, "0000920760", "LEN-B", {"LEN", "LEN-B"}) is None
    assert con.execute("SELECT DISTINCT ticker FROM pit_facts").fetchall() == [("LEN",)]


def test_unknown_or_unchanged_company_is_left_alone():
    con = _db_with([("1", "AAPL")])
    assert relabel_if_stale(con, "1", "AAPL", {"AAPL"}) is None
    assert relabel_if_stale(con, "2", "MSFT", {"MSFT"}) is None
