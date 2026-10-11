"""Suite-wide guard: no test may modify the real pipeline outputs.

Tests exercise code that writes parquet/CSV artifacts to whatever paths a
Universe carries. If a test forgets to redirect one of them to tmp_path,
it silently overwrites real results in data/ — which happened: one test
replaced data/in_bucket_returns.parquet with a one-row fixture on every
run for weeks, and the dashboard showed it as India's bucket returns.
This fixture snapshots every file under data/ (except caches that tests
legitimately touch) and fails the session if any was created, changed or
deleted.
"""

from pathlib import Path

import pytest

import config

# Caches that tests may legitimately read through (requests-cache, sector
# lookups); nothing here is a research result.
_IGNORED_SUFFIXES = {".sqlite", ".sqlite-journal", ".sqlite-wal", ".sqlite-shm", ".log"}
_IGNORED_NAMES = {"sector_cache.json"}


def _snapshot(root: Path) -> dict[str, tuple[float, int]]:
    out = {}
    if not root.exists():
        return out
    for p in root.rglob("*"):
        if (p.is_file() and p.suffix not in _IGNORED_SUFFIXES and p.name not in _IGNORED_NAMES
                and "backups" not in p.parts):
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_mtime_ns, st.st_size)
    return out


@pytest.fixture(scope="session", autouse=True)
def _real_data_is_untouched():
    root = Path(config.DATA_DIR)
    before = _snapshot(root)
    yield
    after = _snapshot(root)
    changed = sorted(k for k in before.keys() & after.keys() if before[k] != after[k])
    created = sorted(after.keys() - before.keys())
    deleted = sorted(before.keys() - after.keys())
    problems = [f"{label}: {', '.join(files)}" for label, files in
                (("modified", changed), ("created", created), ("deleted", deleted)) if files]
    assert not problems, "tests touched real files under data/ — " + "; ".join(problems)
