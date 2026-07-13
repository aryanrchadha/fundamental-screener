"""Sector-neutral standardization of the raw scores.

Raw F/Z/O levels are not comparable across sectors (utilities carry
structurally more leverage than software; Z-Score punishes that even when
it is normal for the industry). So each score is z-scored WITHIN its GICS
sector at each cross-section before ranking or blending.

Sectors with fewer than MIN_SECTOR_SIZE names fall back to a whole-universe
z-score (a sector mean/std computed on 2 points is not meaningful) and a
warning is logged.

Sign convention: O-Score is a distress logit where HIGHER IS WORSE, so it is
sign-flipped here — after this module, higher always means better/safer for
all three inputs. This is explicit and unit-tested.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

import config

log = logging.getLogger(__name__)

# Scores whose raw sign points the "wrong" way (higher = worse).
FLIP_SIGN = {"o_score"}


def sector_zscore(
    scores: pd.DataFrame,
    sectors: pd.Series,
    min_sector_size: int = config.MIN_SECTOR_SIZE,
) -> pd.DataFrame:
    """Z-score each column of `scores` within sector for one cross-section.

    Returns columns renamed with a `_z` suffix. NaN inputs stay NaN.
    """
    sectors = sectors.reindex(scores.index)
    out = pd.DataFrame(index=scores.index)
    for col in scores.columns:
        raw = scores[col].astype(float)
        if col in FLIP_SIGN:
            raw = -raw  # higher = better, uniformly, from here on
        z = pd.Series(np.nan, index=raw.index)
        uni_mean, uni_std = raw.mean(), raw.std(ddof=0)
        for sector, members in raw.groupby(sectors, dropna=False):
            valid = members.dropna()
            if len(valid) >= min_sector_size and valid.std(ddof=0) > 0:
                z.loc[members.index] = (members - valid.mean()) / valid.std(ddof=0)
            else:
                if len(valid) > 0:
                    log.warning(
                        "Sector %r has %d names with %s — falling back to "
                        "universe-level z-score for its members",
                        sector, len(valid), col,
                    )
                if uni_std and uni_std > 0:
                    z.loc[members.index] = (members - uni_mean) / uni_std
        out[f"{col}_z"] = z
    return out
