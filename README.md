# Composite Fundamental Screener

A production-quality research artifact: a **point-in-time (PIT) fundamentals
database** built from SEC EDGAR XBRL filings, three classical statement
scores (**Piotroski F**, **Altman Z**, **Ohlson O**), sector-neutral
standardization, a **LASSO composite**, a monthly **decile backtest**, and
honest statistical validation (**Newey-West** t-stats + **Deflated Sharpe
Ratio**), served in a Plotly Dash dashboard.

## Headline validation result

> Regenerate with `python -m screener.validation`; the table below is the
> committed run (S&P 500 current constituents, 2012–2025, monthly rebalance,
> D10 − D1 equal-weight spread). **See FINDINGS.md for the full memo.**

<!-- VALIDATION_TABLE_START -->
| Strategy | Ann. return | Ann. Sharpe | NW t-stat | DSR | Survives 95%? |
|---|---|---|---|---|---|
| Piotroski F-Score | −1.7% | −0.18 | −0.69 | 0.043 | No |
| Altman Z-Score | −4.1% | −0.42 | −1.50 | 0.004 | No |
| Ohlson O-Score | −6.0% | −0.82 | −3.00 | 0.000 | No |
| **Composite (LASSO)** | **−0.7%** | **−0.08** | **−0.29** | **0.092** | **No** |

**Honest headline: nothing survives.** The composite's edge does not exist
in large-cap US equities post-2012 — the walk-forward LASSO mostly shrinks
the score weights to zero, and the O-Score spread is significantly
*negative* (distress ranking was contrarian in this sample).
<!-- VALIDATION_TABLE_END -->

The Deflated Sharpe Ratio corrects for the fact that **four related
hypotheses** were tested on the same data (F alone, Z alone, O alone, the
composite). A strategy only "survives" if DSR > 0.95.

## Known limitation: survivorship bias

The default universe is **today's** S&P 500 constituent list applied to
history, which overstates returns (winners survive). Wikipedia's historical
changes table is ingested (`screener/universe.py`), and setting
`USE_PIT_UNIVERSE = True` in `config.py` restricts each rebalance to actual
constituents at that date — but the changes table is itself labeled
"selected changes" and is incomplete in early years, so full correction
(Project 58 in the broader portfolio) remains future work. Treat all
backtest levels as optimistic.

## Setup

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e ./pit_fundamentals     # standalone reusable PIT package
pip install -r requirements.txt
```

Set your SEC contact (required by EDGAR's fair-use policy):

```bash
export SEC_USER_AGENT="fundamental-screener your.email@example.com"
```

Optional: `export FMP_API_KEY=...` enables the FMP gap-fill fallback; the
pipeline runs fully without it.

## Run

```bash
python -m pit_fundamentals.ingest --universe sp500   # ~30 min first run (rate-limited, resumable)
python -m screener.backtest                          # scores, composite, deciles -> data/*.parquet
python -m screener.validation                        # NW t-stats + DSR summary -> console + CSV
python -m dashboard.app                              # http://localhost:8050
pytest                                               # full test suite
```

`--limit 50` on the ingest gives a small fast universe (what the Colab
notebook uses). Re-running is cheap: all HTTP responses are disk-cached
(`requests-cache`, SQLite) and ingested CIKs are skipped unless `--refresh`.

## The point-in-time discipline

Every XBRL fact is stored with its **`filed` date**, and every query is
gated by `filed_date <= as_of_date` — fiscal period end is *never* the
availability gate. Restatements are stored as additional rows (nothing is
overwritten) and become visible only from their own filing date. The
load-bearing proof is `pit_fundamentals/tests/test_pit_restatement.py`,
which finds a real restatement in the ingested data and asserts the original
value is returned the day before the restatement was filed and the restated
value the day after.

Reuse the database from any project:

```python
from pit_fundamentals import get_fact_as_of, build_pit_snapshot
```

## Project structure

```
pit_fundamentals/   # standalone PIT database package (own pyproject.toml)
screener/           # universe, scores, normalize, composite, backtest, validation
dashboard/          # Plotly Dash app (6 views)
tests/              # score formulas, normalization, CV-leakage guard, PIT-universe exclusion
notebooks/          # colab_quickstart.ipynb — full pipeline end to end
config.py           # universe, dates, TTLs, SEC User-Agent, toggles
```

## Design notes

- **DuckDB** over sqlite3: the workload is analytical (window functions over
  millions of fact rows, cross-sectional pivots); DuckDB does this in
  milliseconds and reads straight into pandas.
- **Annual statements only**: flow tags are filtered to ≥300-day durations
  and balance-sheet tags to 10-K filings, so YoY deltas compare fiscal years
  — never a 10-Q against a 10-K.
- **No imputation, ever**: a company-quarter missing a required tag is
  excluded from that score and logged.
- **Leakage guards**: LASSO alpha selection uses `TimeSeriesSplit` (unit-
  tested by inspecting the splitter type); refits are annual on an expanding
  window whose training labels' forward windows have fully closed.
