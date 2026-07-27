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

## International extension: South Korea / DART

`pit_fundamentals/dart_kr_client.py` adds a third taxonomy — Korea's DART
OpenAPI, run by the Financial Supervisory Service — following the same
"map to the shared canonical tags" design as the Brazil adapter. DART
requires a registered `crtfc_key` for every call, including its free
company-code list:

```bash
export DART_API_KEY="your_free_key"   # register at https://opendart.fss.or.kr
python -m pit_fundamentals.ingest --taxonomy dart-kr --years 2022 2023
```

**Live-verified against 21 real KOSPI blue chips, FY2022-2023**
(`screener/universe_kr.py` — every corp_code resolved from DART's own
118,508-entity corpCode registry by KRX stock code, none from memory).
The verification standard is the accounting identity **Assets =
Liabilities + Equity holding exactly** on extracted values: 37/40
company-years pass; the other three are the FY2022 financial institutions,
for which DART itself returns status 013 "no data" (the endpoint's
documented historical exclusion of financials — their coverage begins
FY2023). Ohlson O-Score, computed through the **unmodified**
`screener/scores.py` functions, scores all 18 non-financials with an
economically coherent ranking:

| Rank | Company | O-Score | Reads as |
|---|---|---|---|
| Safest | Samsung Electronics | −14.85 | fortress balance sheet |
| … | Celltrion, Hyundai Mobis, Amorepacific | −13.5 to −13.3 | cash-rich |
| Mid | SK Hynix | −11.14 | 2023 memory-downcycle loss year |
| … | Kakao | −10.76 | ₩1.8T net loss in 2023 |
| Riskiest | KEPCO | −9.39 | famously debt-laden utility |
| Excluded | KB, Shinhan, Samsung Life | — | liquidity-order balance sheets, no current/non-current split |

The two live-verification passes caught **five real bugs**, each now a
regression test: (1) SCE tags seven different values under the identical
`account_id` `"ifrs-full_Equity"`, so it's never mapped; (2) the initial
EBIT guess never appears in real filings — filers use the Korea-specific
`dart_OperatingIncomeLoss`; (3) candidate **priority** must be enforced,
not left to filing row order — SK Hynix's balance sheets carry both total
and parent-attributable equity as separate rows and *flipped their order
between FY2022 and FY2023*, silently swapping which survived dedup and
breaking the accounting identity by exactly the NCI amount; (4)
single-statement filers (SK Hynix, NAVER, Kakao, Amorepacific) put their
entire income statement under `sj_div='CIS'` with no `IS` section — an
earlier revision excluded CIS and silently lost all their income facts;
(5) for restated years DART serves figures from documents received up to
two years after fiscal year end, so the filing-date search window is now
+1..+2 years with a validated `rcept_no` date-prefix fallback (first 8
digits = receipt date, empirically confirmed on four real filings).

### Shares outstanding: a second endpoint

Share counts appear nowhere in `fnlttSinglAcntAll` (confirmed by direct
inspection, not assumed) — they live in DART's separate
**`stockTotqySttus`** API, which the adapter now also calls, mapping the
common class's 유통주식수 (circulating shares, already net of treasury)
onto the same canonical `CommonStockSharesOutstanding` tag the US path
uses. Resolved for **all 42 company-years with zero unmatched filers**,
and the values reproduce known real corporate actions:

| Company | FY2022 → FY2023 | Real event |
|---|---|---|
| Celltrion | 137.8M → 207.2M | Dec-2023 Celltrion Healthcare merger |
| SK Innovation | 84.2M → 95.2M | 2023 capital raise |
| KB Financial | 389.6M → 378.7M | buyback-and-cancel |
| Kia | 400.9M → 396.2M | share cancellation |

Getting the share *class* right is load-bearing: `se` (the class label)
has no single spelling across filers — `보통주`, `의결권 있는 보통주`,
`의결권 있는\n보통주` (Shinhan, embedded newline), `의결권 있는 주식\n(보통주)`
(LG Electronics) — so exact-match silently returned nothing for two of the
21. A substring test catches all four while correctly excluding `우선주`
(preferred), Amorepacific's `종류주` (class share), and the `합계` total row
that *bundles* preferred: for Hyundai Motor that's 202.3M common vs 261.3M
total, a 23% error in both dilution and market cap.

**With shares mapped, all three scores now compute** — Piotroski **16/21**,
Altman Z **18/21** (pairing DART shares with KRX prices via yfinance `.KS`
tickers), Ohlson O **18/21**. Samsung's implied market cap of ₩469T matches
its real common-only capitalisation, and Altman ranks KEPCO at **Z = 0.28**,
squarely in the distress zone — correct for a utility carrying ~₩200T of
debt after years of selling power below cost.

**Remaining exclusions are structural, not mapping gaps**: NAVER and
SK Telecom report no gross-profit or cost-of-sales line at all (service
companies presenting a single `ifrs-full_OperatingExpense`), so Piotroski's
Δ-gross-margin criterion drops them — exactly as it drops the many US
service companies whose `GrossProfit` tag is likewise absent. Only the
common share class is mapped, so companies with large preferred floats get
a common-only market cap (the same limitation the US path already carries).

### The Korean backtest

With KRX prices wired in, the KOSPI universe runs the same pipeline
end-to-end:

```bash
python -m screener.backtest  --universe kospi
python -m screener.validation --universe kospi
python -m dashboard.app       --universe kospi
```

Universe: **120 most liquid KOSPI names**, FY2015–2023 fundamentals,
105 monthly rebalances (2017-03 → 2025-11), median 93 fully-scored names
per month. Buckets are **quintiles**, not deciles — 120 names split ten
ways would leave ~9 per bucket. Both the bucket count and a uniform
`MIN_NAMES_PER_BUCKET` rule live in config rather than being hand-tuned
per market.

| Strategy | Ann. return (D5−D1) | Ann. Sharpe | NW t-stat | DSR | Survives 95%? |
|---|---|---|---|---|---|
| Piotroski F-Score | **+5.9%** | 0.38 | 1.02 | 0.519 | No |
| Altman Z-Score | −3.2% | −0.17 | −0.45 | 0.059 | No |
| Ohlson O-Score | −2.3% | −0.16 | −0.43 | 0.062 | No |
| Composite (LASSO) | +2.4% | 0.11 | 0.33 | 0.238 | No |

**Nothing survives in Korea either** — but the result is not a carbon copy
of the US. The Piotroski F-Score is the one strategy with a genuinely
positive point estimate (+5.9%/yr, the best Sharpe of any score in either
market), and Korea's quintile returns are close to monotone at the top
(D5 19.6% > D4 15.7% > D3 13.7% > D2 11.2% annualised) — with the notable
exception of D1 at 17.2%, so the worst-ranked names also did well and the
long-short spread nets out near zero. A t-stat of 1.02 is nowhere near
significance, and the walk-forward LASSO again shrank every coefficient to
zero, so the composite reverts to the equal-weight prior. Treat the
positive F-Score number as "not yet ruled out", not as an edge.

Currency is handled by *not* converting: fundamentals and prices are both
in KRW, so every ratio the scores compute is unit-free, and the long-short
spread is a local-currency return in which an FX translation would multiply
both legs by the same factor and cancel. Comparing the *levels* above
against the US table would not be valid without conversion.

**Survivorship bias is real here too** — the 120 names are today's liquid
KOSPI, ranked over the full sample and applied backwards, so companies that
delisted or lost liquidity are absent. There is no free historical KOSPI-200
constituent table to correct with.

Filers outside these 120 may use tag spellings, share-class labels, or
statement layouts the sweep didn't encounter.

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
# US (S&P 500, deciles)
python -m pit_fundamentals.ingest --universe sp500   # ~30 min first run (rate-limited, resumable)
python -m screener.backtest                          # scores, composite, buckets -> data/*.parquet
python -m screener.validation                        # NW t-stats + DSR summary -> console + CSV
python -m dashboard.app                              # http://localhost:8050

# South Korea (KOSPI 120, quintiles) — needs DART_API_KEY
python -m pit_fundamentals.ingest --taxonomy dart-kr --years 2015 2016 2017 2018 2019 2020 2021 2022 2023
python -m screener.backtest    --universe kospi
python -m screener.validation  --universe kospi
python -m dashboard.app        --universe kospi

pytest                                               # full test suite
```

Every market-specific detail — ticker source, Yahoo exchange suffix, bucket
count, output paths, currency — is a field on a `Universe`
(`screener/universes.py`), so adding a market means adding a Universe
rather than editing the backtest.

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
  dart_kr_client.py    # South Korea/DART adapter (live-verified on Samsung)
  ingest.py            # CLI: --taxonomy {us-gaap, cvm-br, dart-kr}
screener/           # universe, scores, normalize, composite, backtest, validation
  universe_br.py       # curated B3 blue-chip ticker->CNPJ crosswalk
  universe_kr.py       # KOSPI crosswalk loader (120 names)
  kospi_universe.csv   # the universe itself, tracked so a clean clone reproduces it
  universes.py         # Universe defs: suffix, bucket count, paths, currency
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
