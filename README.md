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

## International extension: Brazil / B3 (proof of concept)

`pit_fundamentals` supports a second taxonomy end-to-end: Brazil's CVM
Dados Abertos (the SEC's direct counterpart — a free, no-key, structured
open-data portal), via `pit_fundamentals/cvm_br_client.py`. Brazil was
chosen over other "leading EM" exchanges (India's NSE/BSE, China's
SSE/SZSE, South Africa's JSE) because none of those have a free, structured,
EDGAR-like bulk fundamentals source — CVM does. (South Korea's DART system
is the next-best candidate; it requires registering for a free API key,
which would need the same optional/degrades-gracefully treatment this
project already gives `FMP_API_KEY` — left as future work.)

```bash
python -m pit_fundamentals.ingest --taxonomy cvm-br --years 2022 2023 --db data/pit_br_demo.duckdb
```

This ingests a manually curated, documented crosswalk of 16 Ibovespa blue
chips (`screener/universe_br.py` — CNPJ mappings verified against real 2023
CVM filings, not guessed) and maps CVM's standardized account codes
(`CD_CONTA`, e.g. `"1.01"` = *Ativo Circulante*) onto the exact same
canonical tags US-GAAP facts use (`Assets`, `NetIncomeLoss`, ...), so
`screener/scores.py`'s Piotroski/Altman/Ohlson functions run **completely
unmodified** on Brazilian filings. Real result from this run (16 tickers,
13 scored successfully):

| Ticker | Sector | F-Score | O-Score |
|---|---|---|---|
| WEGE3 (WEG) | Industrials | 8 | −10.4 |
| ABEV3 (Ambev) | Consumer Staples | 8 | −10.4 |
| LREN3 (Lojas Renner) | Consumer Discretionary | 7 | −8.7 |
| VALE3 (Vale) | Materials | 6 | −9.3 |
| PETR4 (Petrobras) | Energy | 6 | −9.4 |
| ITUB4, BBDC4, BBAS3 (banks) | Financials | — | — |
| BBSE3 (insurer) | Financials | — | — |

The three banks and the insurance holding company were **automatically
excluded** — not via a hardcoded "skip financials" list, but because
Brazilian banks file under COSIF (a different chart of accounts that reuses
the *same* numeric codes for different line items — e.g. code `"1.01"`
means *Caixa e Equivalentes de Caixa* for a bank vs. *Ativo Circulante* for
an industrial filer). `cvm_br_client.py` verifies each account's text label
before trusting its code and drops any mismatch rather than mismapping it —
confirmed against real filings from Banco do Brasil, Bradesco, Itaú, and BB
Seguridade, each excluded on exactly the fields their non-industrial chart
of accounts diverges on.

**What this is not**: a second backtestable universe. There is no free
historical B3 constituent-membership table, no BRL/USD-aware return
pipeline in `screener/backtest.py`, and a real, discovered data-quality gap
in CVM's own data — the `composicao_capital` (share count) file has no
`ESCALA_MOEDA`-style scale field, and cross-checking real filings shows some
companies self-report in thousands and others in raw share counts with no
way to detect which from the file alone. Altman Z's market-cap term is
therefore **not** reliable for CVM-sourced companies without a manual
per-company scale check; F-Score and O-Score (neither needs market cap) are
unaffected and were verified against hand-checked real filings.

## International extension: South Korea / DART (⚠ NOT live-verified)

`pit_fundamentals/dart_kr_client.py` adds a third taxonomy — Korea's DART
OpenAPI, run by the Financial Supervisory Service — following the same
"map to the shared canonical tags" design as the Brazil adapter. **Unlike
Brazil, this one has not been run against a live API response.** DART
requires a registered `crtfc_key` for every call, including its free
company-code list, and no key was available while this was built. Every
endpoint URL, parameter name, and response field is sourced from DART's
official developer guide, cross-checked against a real worked example
(Samsung Electronics' FY2019 filing tags current assets as
`ifrs-full_CurrentAssets`) and an independent open-source project
(DartLab) that documents Korean filers tagging the *same* concept three
different ways — `ifrs-full_Revenue` (Samsung), `dart_Revenue` (SK Hynix),
bare `Revenue` (LG Energy Solution) — which is why the code map tries
prefix-stripped candidate names rather than one fixed lookup. But nothing
here has been sanity-checked against real numbers. Before trusting any
score derived from it:

```bash
export DART_API_KEY="your_free_key"   # register at https://opendart.fss.or.kr
python -m pit_fundamentals.ingest --taxonomy dart-kr --years 2023
```

`screener/universe_kr.py` ships with exactly **one** entry (Samsung
Electronics, `005930`) — its `corp_code` is quoted from a published
tutorial's worked example, not verified live either. Populate the rest
yourself once you have a key (instructions in that file's docstring);
inventing plausible-looking 8-digit corp_codes for other companies would
silently point at the wrong data or nothing at all, which is worse than
leaving them out. Long-term debt and shares outstanding are deliberately
left unmapped (they need either a DART-specific extension tag or a
separate API family this adapter doesn't call) — Piotroski's dilution
check and Altman Z's market-cap term won't compute for Korean names as a
result, but Ohlson O-Score needs neither and should work once tested.

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
  edgar_client.py     # SEC EDGAR HTTP client (rate-limited, cached)
  cvm_br_client.py     # Brazil/CVM Dados Abertos adapter (verified live)
  dart_kr_client.py    # South Korea/DART adapter (NOT live-verified — see docstring)
  ingest.py            # CLI: --taxonomy {us-gaap, cvm-br, dart-kr}
screener/           # universe, scores, normalize, composite, backtest, validation
  universe_br.py       # curated B3 blue-chip ticker->CNPJ crosswalk
  universe_kr.py       # KOSPI crosswalk (1 verified entry, rest TODO — see docstring)
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
