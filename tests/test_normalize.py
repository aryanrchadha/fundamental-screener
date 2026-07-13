"""Tests for sector-neutral z-scoring: moments, small-sector fallback, and
the O-Score sign flip."""

import numpy as np
import pandas as pd
import pytest

from screener.normalize import sector_zscore


def test_sector_moments_are_standard():
    rng = np.random.default_rng(42)
    n = 60
    sectors = pd.Series(["Tech"] * 30 + ["Energy"] * 30,
                        index=[f"T{i}" for i in range(n)])
    scores = pd.DataFrame(
        {"f_score": rng.normal(5, 2, n), "z_score": rng.normal(3, 1, n)},
        index=sectors.index,
    )
    z = sector_zscore(scores, sectors)
    for sector in ["Tech", "Energy"]:
        for col in ["f_score_z", "z_score_z"]:
            grp = z.loc[sectors == sector, col]
            assert grp.mean() == pytest.approx(0.0, abs=1e-10)
            assert grp.std(ddof=0) == pytest.approx(1.0, abs=1e-10)


def test_small_sector_falls_back_to_universe(caplog):
    sectors = pd.Series(
        ["Big"] * 10 + ["Tiny"] * 2, index=[f"T{i}" for i in range(12)]
    )
    rng = np.random.default_rng(0)
    scores = pd.DataFrame({"f_score": rng.normal(5, 2, 12)}, index=sectors.index)
    with caplog.at_level("WARNING"):
        z = sector_zscore(scores, sectors, min_sector_size=5)
    assert any("falling back" in r.message for r in caplog.records)
    # Tiny-sector members must equal the UNIVERSE z-score, not a 2-point one.
    uni = (scores["f_score"] - scores["f_score"].mean()) / scores["f_score"].std(ddof=0)
    for t in ["T10", "T11"]:
        assert z.loc[t, "f_score_z"] == pytest.approx(uni[t])


def test_o_score_sign_flip():
    """Higher raw O (worse) must map to LOWER o_score_z (worse) — after
    normalization, higher always means better across all three inputs."""
    sectors = pd.Series(["S"] * 6, index=list("ABCDEF"))
    raw = pd.DataFrame({"o_score": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}, index=sectors.index)
    z = sector_zscore(raw, sectors)
    assert z["o_score_z"].is_monotonic_decreasing
    assert z.loc["A", "o_score_z"] > 0 > z.loc["F", "o_score_z"]


def test_nan_stays_nan():
    sectors = pd.Series(["S"] * 6, index=list("ABCDEF"))
    raw = pd.DataFrame({"f_score": [1, 2, 3, 4, 5, np.nan]}, index=sectors.index)
    z = sector_zscore(raw, sectors)
    assert np.isnan(z.loc["F", "f_score_z"])
