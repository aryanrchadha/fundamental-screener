"""The GUI layer: pipeline commands launched from the browser, backups,
the stale-validation banner and the company drill-down."""

import os
import sys
import time
from dataclasses import replace

import pandas as pd
import pytest

from dashboard import jobs
from dashboard.jobs import JobRunner, Step, backup, step_commands, survivorship_supported
from screener.universes import INDIA, KOSPI, SP500


def _args(steps):
    return [s.cmd[2:] for s in steps]       # drop "<python> -m"


def test_steps_run_in_pipeline_order_whatever_the_input_order():
    names = [s.name for s in step_commands("sp500", ["validation", "ingest", "backtest"])]
    assert names == ["ingest", "backtest", "validation"]


def test_ingest_always_targets_the_universes_own_db():
    """Without --db the ingest CLI defaults to data/pit.duckdb, the S&P 500
    database — a KOSPI or India ingest would land in the US DB."""
    for name, uni in (("sp500", SP500), ("kospi", KOSPI), ("india", INDIA)):
        cmd = _args(step_commands(name, ["ingest"]))[0]
        assert cmd[cmd.index("--db") + 1] == str(uni.db_path)
    assert "dart-kr" in _args(step_commands("kospi", ["ingest"]))[0]


def test_survivorship_flag_only_where_a_membership_source_exists():
    assert survivorship_supported("sp500") and survivorship_supported("kospi")
    assert not survivorship_supported("russell3000") and not survivorship_supported("india")
    assert "--survivorship" in _args(step_commands("kospi", ["backtest"], survivorship=True))[0]
    assert "--survivorship" not in _args(step_commands("russell3000", ["backtest"], survivorship=True))[0]


def test_backups_cover_the_files_each_step_overwrites():
    bt, val = step_commands("sp500", ["backtest", "validation"], survivorship=True)
    pit = SP500.corrected()
    assert set(bt.outputs) == {pit.panel_path, pit.bucket_returns_path, pit.coefs_path}
    assert set(val.outputs) == {pit.validation_path, pit.rolling_path}
    assert step_commands("sp500", ["ingest"])[0].outputs == ()


def test_india_gets_no_validation_step_and_limit_is_us_only():
    assert [s.name for s in step_commands("india", list(jobs.STEPS))] == ["ingest", "backtest"]
    assert "--limit" in _args(step_commands("sp500", ["ingest"], limit=50))[0]
    assert "--limit" not in _args(step_commands("kospi", ["ingest"], limit=50))[0]


def test_backup_copies_existing_files_and_skips_missing(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("x")
    dest = backup([a, tmp_path / "missing.parquet"], dest_root=tmp_path / "bk")
    assert (dest / "a.csv").read_text() == "x"
    assert not (dest / "missing.parquet").exists()
    assert backup([tmp_path / "missing.parquet"], dest_root=tmp_path / "bk") is None


def _wait(runner, timeout=20):
    t0 = time.time()
    while runner.busy() and time.time() - t0 < timeout:
        time.sleep(0.05)
    return runner.job


def test_runner_streams_output_and_stops_at_first_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "BACKUP_DIR", tmp_path)
    py = sys.executable
    ok = Step("one", [py, "-c", "import time; print('hello from step one'); time.sleep(0.5)"])
    bad = Step("two", [py, "-c", "import sys; sys.exit(3)"])
    never = Step("three", [py, "-c", "print('should not run')"])

    r = JobRunner()
    r.start("test", [ok, bad, never])
    with pytest.raises(RuntimeError, match="already running"):
        r.start("second", [ok])               # one job at a time
    job = _wait(r)
    log = "\n".join(job.lines)
    assert job.status == "failed" and job.finished is not None
    assert "hello from step one" in log and "exit code 3" in log
    assert "should not run" not in log

    r.start("again", [ok])
    assert _wait(r).status == "done"


def _panel(n_tickers=12):
    rows = []
    for d in pd.date_range("2024-01-31", periods=4, freq="ME"):
        for i in range(n_tickers):
            rows.append(dict(as_of_date=d, ticker=f"T{i}", sector="Energy", f_score=float(i % 10),
                             z_score=1.0, o_score=-5.0, composite_score=float(i), decile=float(i % 5 + 1)))
    return pd.DataFrame(rows)


def test_company_history_has_one_panel_per_score():
    from dashboard.app import fig_company_history

    fig = fig_company_history(_panel(), "T3")
    assert len(fig.data) == 4
    assert all(len(t.x) == 4 for t in fig.data)
    assert "T3" in fig.layout.title.text


def test_stale_banner_when_validation_predates_backtest(tmp_path):
    from dashboard.app import stale_warning

    paths = {k: tmp_path / f"{k}.bin" for k in ("ret", "val", "roll")}
    for p in paths.values():
        p.write_text("x")
    uni = replace(SP500, bucket_returns_path=paths["ret"], validation_path=paths["val"],
                  rolling_path=paths["roll"])
    now = time.time()
    os.utime(paths["ret"], (now - 100, now - 100))
    assert stale_warning(uni) is None                 # validation newer than the backtest

    os.utime(paths["val"], (now - 200, now - 200))
    assert "Validation" in str(stale_warning(uni))
    assert "Rolling" not in str(stale_warning(uni))
    assert stale_warning(replace(uni, backtestable=False)) is None


def test_app_shows_a_run_prompt_when_a_universe_has_no_panel(tmp_path):
    import dashboard.app as appmod

    uni = replace(SP500, panel_path=tmp_path / "none.parquet")
    rendered = str(appmod.build_app(uni).layout)
    assert "No scores panel for sp500" in rendered
    assert "Run pipeline" in rendered


def test_watchlist_rows_report_latest_and_year_ago_decile():
    from dashboard.app import fig_watchlist, watchlist_rows

    dates = pd.date_range("2024-01-31", periods=14, freq="ME")
    p = pd.DataFrame([dict(as_of_date=d, ticker=t, sector="X", f_score=5.0, z_score=2.0, o_score=-5.0,
                           composite_score=0.1, decile=float(1 + i // 7) if t == "A" else 3.0)
                      for i, d in enumerate(dates) for t in ("A", "B")])
    rows = {r["ticker"]: r for r in watchlist_rows(p, ["A", "B"])}
    assert rows["A"]["decile"] == 2.0 and rows["A"]["decile_12m_ago"] == 1.0
    assert rows["A"]["as_of_date"] == "2025-02-28"
    assert watchlist_rows(p, []) == []
    fig = fig_watchlist(p, ["A", "B"], "decile", 5)
    assert len(fig.data) == 2 and tuple(fig.layout.yaxis.range) == (0.5, 5.5)
