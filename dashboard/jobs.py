"""Run pipeline steps from the dashboard as background subprocesses.

The GUI never imports and calls the pipeline in-process. Each step runs
as exactly the CLI command the README documents (`python -m
screener.backtest --universe kospi`, ...), so a run started from the
browser and one started from a terminal produce the same artifacts, logs
and failure modes. The dashboard just reads what those commands write.

One job at a time: ingest, backtest and validation all write to the same
per-universe files, and two concurrent writers to one DuckDB file or
parquet would corrupt the run rather than speed it up.

Every backtest/validation step first copies the artifacts it is about to
overwrite into data/backups/<timestamp>/. A run from a button is easy to
start by accident (or against a smaller panel than the one the existing
validation CSV was computed from), and the previous outputs are not in git.
Ingest is not backed up: it appends to a resumable DuckDB rather than
replacing it, and the R3K database is hundreds of MB.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import config
from screener.universes import get_universe

STEPS = ("ingest", "backtest", "validation")
BACKUP_DIR = config.DATA_DIR / "backups"

# The ingest CLI selects its source by --taxonomy for non-US markets and
# by --universe for the two EDGAR ones. --db is always passed explicitly:
# without it the ingest falls back to data/pit.duckdb (the S&P 500 DB),
# which would silently mix another market's facts into the US database.
_INGEST_ARGS = {
    "sp500": ["--universe", "sp500"],
    "russell3000": ["--universe", "russell3000"],
    "kospi": ["--taxonomy", "dart-kr", "--years", *[str(y) for y in range(2015, 2024)]],
    "india": ["--taxonomy", "bse-in"],
}


def survivorship_supported(universe: str) -> bool:
    """Only universes with a real point-in-time membership source. Russell
    3000 has none (no free reconstitution feed) and India is screener-only,
    so offering the toggle there would promise a correction that cannot
    happen."""
    return universe in ("sp500", "kospi")


@dataclass(frozen=True)
class Step:
    name: str
    cmd: list[str]
    outputs: tuple[Path, ...] = ()       # files this step overwrites (backed up first)

    def display(self) -> str:
        return "python " + " ".join(self.cmd[1:])


def step_commands(universe: str, steps, survivorship: bool = False,
                  limit: int | None = None) -> list[Step]:
    """The CLI command for each requested step, in pipeline order."""
    uni = get_universe(universe)
    if survivorship and survivorship_supported(universe):
        uni = uni.corrected()                # so `outputs` are the _pit paths
    surv = ["--survivorship"] if uni.survivorship_corrected else []
    py = [sys.executable, "-m"]
    out = []
    for step in STEPS:                       # enforce order regardless of input order
        if step not in steps:
            continue
        if step == "ingest":
            cmd = py + ["pit_fundamentals.ingest", *_INGEST_ARGS[universe], "--db", str(uni.db_path)]
            if limit and universe in ("sp500", "russell3000"):
                cmd += ["--limit", str(int(limit))]
            out.append(Step(step, cmd))
        elif step == "backtest":
            files = (uni.panel_path, uni.bucket_returns_path, uni.coefs_path)
            if not uni.backtestable:
                files += (uni.rolling_path,)  # run_screen writes its descriptive rolling chart too
            out.append(Step(step, py + ["screener.backtest", "--universe", universe, *surv], files))
        elif uni.backtestable:               # validation refuses screener-only universes
            out.append(Step(step, py + ["screener.validation", "--universe", universe, *surv],
                            (uni.validation_path, uni.rolling_path)))
    return out


def backup(paths, dest_root: Path = BACKUP_DIR) -> Path | None:
    """Copy whichever of `paths` exist into a fresh timestamped folder."""
    existing = [Path(p) for p in paths if Path(p).exists()]
    if not existing:
        return None
    dest = dest_root / time.strftime("%Y%m%d-%H%M%S")
    n = 0
    while dest.exists():                     # two steps in the same second
        n += 1
        dest = dest_root / (time.strftime("%Y%m%d-%H%M%S") + f"-{n}")
    dest.mkdir(parents=True)
    for p in existing:
        shutil.copy2(p, dest / p.name)
    return dest


@dataclass
class Job:
    label: str
    steps: list[Step]
    status: str = "running"                  # running | done | failed | stopped
    started: float = field(default_factory=time.time)
    finished: float | None = None
    lines: deque = field(default_factory=lambda: deque(maxlen=2000))


class JobRunner:
    def __init__(self):
        self._lock = threading.Lock()
        self._job: Job | None = None
        self._proc: subprocess.Popen | None = None
        self._stop = threading.Event()

    @property
    def job(self) -> Job | None:
        return self._job

    def busy(self) -> bool:
        return self._job is not None and self._job.status == "running"

    def start(self, label: str, steps: list[Step]) -> Job:
        with self._lock:
            if self.busy():
                raise RuntimeError("a pipeline job is already running")
            self._stop.clear()
            self._job = Job(label=label, steps=steps)
            threading.Thread(target=self._run, args=(self._job,), daemon=True).start()
            return self._job

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc and proc.poll() is None:
            proc.terminate()

    def _run(self, job: Job) -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        for step in job.steps:
            if self._stop.is_set():
                break
            job.lines.append("$ " + step.display())
            try:
                saved = backup(step.outputs)
                if saved:
                    job.lines.append(f"(previous outputs backed up to {saved.relative_to(config.ROOT_DIR)})")
                self._proc = subprocess.Popen(
                    step.cmd, cwd=config.ROOT_DIR, env=env, text=True, bufsize=1,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                )
            except OSError as e:
                job.lines.append(f"failed to start: {e}")
                job.status = "failed"
                break
            for line in self._proc.stdout:
                job.lines.append(line.rstrip("\n"))
            rc = self._proc.wait()
            if self._stop.is_set():
                job.status = "stopped"
                break
            if rc != 0:
                job.lines.append(f"[exit code {rc}] — later steps skipped")
                job.status = "failed"
                break
        else:
            job.status = "done"
        if job.status == "running":
            job.status = "stopped"
        job.finished = time.time()
        self._proc = None


RUNNER = JobRunner()
