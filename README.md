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

**Across all three markets** — S&P 500, KOSPI 120, BSE 100 — plus the
survivorship-corrected re-runs, that bar is never cleared:

| Market | Months | Composite ann. | NW t | DSR | Survives? |
|---|---|---|---|---|---|
| US — S&P 500 | 167 | −0.7% | −0.29 | 0.092 | No |
| US, survivorship-corrected | 167 | −1.3% | −0.42 | 0.067 | No |
| Korea — KOSPI 120 | 105 | +2.4% | +0.33 | 0.238 | No |
| Korea, survivorship-corrected | 105 | +2.4% | +0.33 | 0.238 | No |
| India — BSE 100 | 26 † | +2.1% † | +0.34 † | 0.233 † | No † |

† Descriptive only, not a test: India's composite ranking has a median
month-to-month rank correlation of 0.998 and updates on just three annual
filings, so its effective sample is nearer 3 than 26. Reported for
completeness; the pipeline still refuses to emit a validation table for it.
Full reasoning in [FINDINGS.md](FINDINGS.md).

## Rolling out-of-sample decay

The rolling chart's shaded band is derived from the Deflated Sharpe Ratio,
not a plain SE band: for each 24-month window it marks the spread needed
for **that window's own DSR to reach 95%**. It is the DSR inverted, and the
correspondence is exact — "outside the band" and "DSR ≥ 0.95" agree on 100%
of test windows.

The same chart is produced for **every** backtestable run — `--universe
sp500` and `--universe kospi`, each with and without `--survivorship` — and,
by explicit request rather than by default, for the screener-only India
universe too:

| Run | Windows | Clears DSR hurdle | Breaches negative hurdle | Median hurdle | Mean spread |
|---|---|---|---|---|---|
| US S&P 500 (static) | 144 | **0 / 144** | 1 / 144 | +18.5%/yr | −0.1%/yr |
| US, survivorship-corrected | 144 | 20 / 144 † | **27 / 144** | +8.5%/yr | −0.5%/yr |
| Korea KOSPI 120 | 82 | **12 / 82** — all Feb 2019 – May 2020 | 19 / 82 | +13.9%/yr | −2.1%/yr |
| Korea, survivorship-corrected | 82 | identical to static | | | |
| **India BSE 100** ‡ | **3** | 0 / 3 | 0 / 3 | +17.9%/yr | +2.3%/yr |

‡ India is not a backtestable universe (see below) — 27 monthly
cross-sections and a 24-month window leave only 3, 96%-overlapping windows.
Shown because it was explicitly asked for at the standard window, not
because 3 points support the same reading as 144 or 82. See FINDINGS.md.

Rolling spread by window-year:

| | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **US** | −21% | −19% | −3% | +4% | +6% | +5% | +3% | +2% | +3% | +2% | −2% | −1% | +0% |
| **Korea** | | | | | | | **+24%** | +8% | −14% | −26% | −2% | −1% | −2% |

**Korea shows real decay** — an early stretch beating a
multiple-testing-corrected benchmark, then five years that do not. **The US
never clears the bar in its headline configuration**, so the two fail in
genuinely different ways.

† **Do not read the corrected-US row as a positive result.** Its 20
clearing windows are outnumbered by 27 significantly *negative* ones, and
the full-sample verdict on that exact series is composite −1.3%/yr, t
−0.42, DSR 0.067 — a decisive failure. A null series with time-varying
volatility will throw off stretches that clear a 95% bar; quoting them is
the selection error the DSR exists to prevent. Full discussion in
[FINDINGS.md](FINDINGS.md), along with the caveat that Korea's clearing
windows lean partly on its thinnest cross-sections.

View any of them with e.g. `python -m dashboard.app --universe sp500` →
"Rolling spread".

## Survivorship correction: run, and reported

`--survivorship` restricts every rebalance to names actually listed/in the
index on that date, writing to separate `*_pit` outputs so both runs stand
side by side:

```bash
python -m screener.backtest   --universe sp500 --survivorship
python -m screener.validation --universe sp500 --survivorship
```

**S&P 500** (Wikipedia's constituent-changes table unwound backwards; the
2012 cross-section shrinks from 503 names to 294):

| Strategy | Static | Corrected |
|---|---|---|
| Piotroski F-Score | −1.7% | −1.3% |
| Altman Z-Score | −4.1% | −5.4% |
| Ohlson O-Score | −6.0% | −4.2% |
| **Composite** | **−0.7%** | **−1.3%** |

The correction moves individual scores in both directions and changes no
conclusion: nothing survives Deflated Sharpe either way.

**KOSPI** (first-annual-filing dates pulled per company from DART; 13 of
the 120 listed after 2016, so the 2016 universe is 107): the corrected run
is **bit-for-bit identical** to the static one. That is not a null result
— it is evidence the point-in-time discipline already works. Of the 362
company-months the listing gate removed, **zero** had a computable score:
a company that had not filed yet has no facts in the PIT snapshot, so
look-ahead was structurally impossible rather than merely avoided.

**What is still uncorrected, and why.** Both corrections handle *look-ahead*
(names appearing before they existed). Neither fully handles *delisting*
survivorship, and for Korea that limit was established empirically rather
than assumed:

- DART's `corp_cls` is a **current** attribute. Querying its filing index
  with `corp_cls='Y'` returns 684 KOSPI filers for 2016 and reports zero
  missing by 2025 — an impossible delisting rate, and purely an artefact of
  the filter hiding anything since reclassified. Dropping the filter shows
  2,097 companies filed in that window, 406 of which now carry class 'E'.
- Those names cannot be priced anyway: Yahoo returned usable `.KS` history
  for only **4 of a 40-name sample**, because it drops delisted KRX tickers.

So the residual bias is quantified rather than silently corrected with data
that does not exist. Treat all backtest levels as optimistic.

## US extension: Russell 3000 (full universe) — a "survivor," and why it isn't one

`--universe russell3000` swaps the ticker source without touching anything
else — same SEC EDGAR/us-gaap taxonomy, same `screener/scores.py`, same
2012–2025 date range, its own database (`data/pit_r3k.duckdb`) and output
paths so a run never collides with the S&P 500 one. There is no free,
direct Russell-index constituent feed (FTSE Russell licenses that data), so
`screener.universe.get_russell3000_constituents()` uses BlackRock's IWV ETF
— built to track the Russell 3000 as closely as possible — and reads its
full daily holdings CSV (no key, no login): confirmed live, ~2,580 equity
holdings with ticker, name, sector, and index weight. This is standard
practice in quant research (ETF replication holdings as an index-membership
proxy) precisely because the licensed constituent file is a commercial
product — documented here as an approximation, not the real thing.

```bash
python -m pit_fundamentals.ingest --universe russell3000 --db data/pit_r3k.duckdb
python -m screener.backtest    --universe russell3000
python -m screener.validation  --universe russell3000
python -m dashboard.app        --universe russell3000
```

An initial committed run capped the universe to the top 300 names by index
weight — but checking the ticker sets directly showed 286 of those 300
were already S&P 500 constituents, making that run a pipeline consistency
check, not a genuine breadth test. `config.RUSSELL3000_MAX_TICKERS` is now
`None` (full universe): of the resulting **2,547 tickers with real Yahoo
price history** (2,582 requested; the rest are genuinely delisted/unknown,
confirmed by three retries each still failing), only 494 overlap the S&P
500 — **2,053 are genuinely non-overlapping names**, the real test this
project's own prior draft asked for.

Getting a trustworthy result at this scale required fixing two real bugs,
both only visible once the universe stopped being large-cap-only:

1. **Yahoo silently rate-limits large single-batch requests.** A single
   `yf.download()` call for all 2,582 symbols returned real data for only
   ~2 of them — `YFRateLimitError` on most of the batch, which yfinance
   swallows into NaN columns rather than raising, so it looked like a data
   problem rather than a request-shape one. Fixed in `screener/prices.py`
   by chunking the download (250 symbols/call) with a pause between
   chunks and an escalating-backoff retry for symbols still missing after
   a chunk — confirmed live: 2,547/2,582 recovered.
2. **Yahoo pads pre-listing history with literal `0.0`, not `NaN`.**
   Confirmed on a real ticker (`DEC`/Diversified Energy, IPO'd Nov 2023,
   whose cached history showed `0.0` for every month back to 2021). A real
   market close is never exactly $0.00, so this silently produced an
   infinite forward return (`p1 / p0` with `p0 == 0`) the moment the stock
   actually started trading, crashing the LASSO fit. Fixed by treating an
   exact-zero close as missing.

Both are documented in `screener/prices.py`'s module docstring so the next
person scaling this pipeline doesn't rediscover them from a stack trace.

| Strategy | Ann. return (D10−D1) | Ann. Sharpe | NW t-stat | DSR | Survives 95%? |
|---|---|---|---|---|---|
| Piotroski F-Score | −6.9% | −0.49 | −1.69 | 0.001 | No |
| Altman Z-Score | −10.6% | −1.04 | −3.97 | 0.000 | No |
| Ohlson O-Score | −17.6% | −1.30 | −4.07 | 0.000 | No |
| **Composite (LASSO)** | **+13.2%** | **0.75** | **2.32** | **0.988** | **YES** |

**This is the only "survivor" in the entire project — read the rest of this
section before believing it.** Every individual score is strongly and
significantly *negative* (O-Score's t-stat of −4.07 is the most significant
result anywhere in this project, in the *distress-is-contrarian* direction
already seen in every other market), yet the LASSO composite is positive
with DSR = 0.988. That combination is possible because every LASSO
coefficient is negative at every refit — the composite ranks the
*worst*-fundamentals names into D10, and D10 beat D1. Four things point to
this being an artifact rather than a real reversal:

- **A direct audit confirms the survivorship-bias hypothesis rather than
  just arguing for it.** If D10 structurally over-represents companies
  that crashed and survived (rather than the ones that crashed and
  delisted, absent from any backtest built on today's constituent list),
  that predicts D10 should be full of "distressed survivors." Checking
  directly against the 742 D10 tickers with price history: 392 (52.8%)
  had a peak-to-trough drawdown worse than −70% at some point in-sample,
  and 202 of those (27% of all D10 names) recovered to over half their
  prior peak afterward — `GME` (−91.1% drawdown, then the short squeeze)
  and `SBET` (−99.9%, then the crypto pivot) are both in this group,
  tying this check to the outlier-month one below. **Removing just these
  202 names from D10 drops annualized return from +13.2% to +8.9%, t from
  2.32 to 1.88, and DSR from 0.988 to 0.9145 — below the bar** — on its
  own, without touching anything else about the run.
- **No survivorship correction exists for this universe** (see below) —
  today's Russell 3000 list only contains names that are still around, so
  the "worst fundamentals" bucket structurally excludes every company that
  went bankrupt between 2012 and today and keeps only the ones that
  survived, many via a distress-recovery rally — the mechanism the audit
  above confirms directly rather than merely predicts.
- **Nearly the entire return is concentrated in specific single-name,
  single-month events.** December 2020's spread is dominated by `GME` —
  GameStop's short-squeeze month, **+1,625% in one month**, equal-weighted
  into a 102-name bucket; April 2025 by `SBET` (+2,267%, a crypto-treasury
  pivot). Winsorizing the spread series at the 1st/99th percentile still
  survives (DSR 0.993), but **dropping just those two months entirely
  drops DSR to 0.932 — below the 0.95 bar.** A result whose survival flips
  depending on whether two months are capped or removed is not robust.
- **The effect is entirely a post-2019 phenomenon.** Cumulative spread:
  −2.8% in the first half (2012–2018), **+383.5%** in the second
  (2019–2025) — a genuine cross-sectional factor premium does not usually
  materialize from nothing across 7 flat years and then explode across the
  pandemic/meme-stock/crypto-mania era specifically.

Full discussion, including the rolling-window breakdown by year, is in
[FINDINGS.md](FINDINGS.md). **The honest reading is not "found an edge in
small-caps" — it is a worked example of exactly the failure mode Deflated
Sharpe and rolling-window scrutiny exist to catch**, made possible here
only because uncorrected survivorship bias and equal-weighting are both
much more dangerous in a ~2,500-name small/micro-cap universe than in a
500-name large-cap one.

**What this does not add**: no survivorship correction (`.corrected()` is
supported by the `Universe` interface, but `Russell3000Universe.membership()`
always returns `None` — there is no free historical Russell reconstitution
feed, unlike Wikipedia's imperfect-but-real S&P 500 changes table, so
claiming a correction here would be fabricating data that does not exist,
not correcting for its absence). That absence is precisely what makes this
result untrustworthy rather than merely unlucky.

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

## International extension: India / BSE + Yahoo

`pit_fundamentals/india_client.py` adds a fourth market — and it is built
differently, because India's free data landscape is genuinely worse. Each
of the other three regulators publishes machine-readable statements with a
filing date on every number (EDGAR's `filed`, CVM's `DT_RECEB`, DART's
`rcept_dt`). India has no free equivalent. What it has, established by
direct request rather than assumption, is two halves:

- **BSE's public API** serves audited-results announcements with a real
  dissemination timestamp — Reliance's FY2024 results went out
  2024-04-22T19:00:20. Authoritative filing dates. But the numbers sit in
  an attached PDF: the XBRL URLs 404 and the structured-results endpoints
  return BSE's HTML error page.
- **Yahoo Finance** serves the values for `.NS` tickers, unusually
  completely — every canonical tag including a direct `EBIT` and share
  count. But it attaches no filing date at all.

Neither is point-in-time capable alone. This adapter joins them: Yahoo
values, gated by the BSE dissemination date of the announcement that first
reported that period. The join is the contribution.

```bash
python -m pit_fundamentals.ingest --taxonomy bse-in --db data/pit_in.duckdb  # no API key
python -m screener.backtest --universe india                                 # runs the screen
python -m dashboard.app     --universe india                                 # localhost:8050
```

Universe: **top 100 by market cap** from BSE's own 5,082-name scrip master,
filtered to those with ≥1000 days of Yahoo history
(`screener/india_universe.csv`, tracked). Verification: **387/387
company-years satisfy Assets = Liabilities + Equity to within 0.1%**, and
filing lags run 9–134 days (median 40) — consistent with SEBI's 60-day
audited-results deadline.

Scores through the **unmodified** `screener/scores.py` (F 78/100, Z 79/100,
O 80/100) land where they should:

| Company | Altman Z | Reads as |
|---|---|---|
| **Vodafone Idea** | **−1.64** | *negative* Z — India's most distressed large-cap (AGR dues, negative net worth) |
| IRFC | 0.37 | leveraged rail-financing entity |
| Grasim, POWERGRID, NTPC, Tata Power, Adani Green | 0.7–1.4 | capital-intensive, heavily-geared utilities and infra |

Vodafone Idea also tops the Ohlson O ranking — two independent distress
models agreeing on the same name, with no tuning.

### The screen, and what the dashboard shows

`--universe india` runs `run_screen()`: it builds the scores panel, a
bucket-return series, and a rolling-spread chart — but deliberately **no
LASSO fit and no Newey-West/Deflated-Sharpe validation table**. 2,700
company-months across 27 dates, 77 of 100 names scored in the latest
cross-section. The composite is the documented **equal-weight** prior
rather than a LASSO fit — fitting three coefficients on ~3 independent
fundamental cross-sections would be fitting noise.

Latest cross-section, top and bottom of the composite ranking:

| | Company | F | Z | O | Sector |
|---|---|---|---|---|---|
| **Top** | HDFC Asset Management | 8 | 89.1 | −18.3 | Financial Services |
| | Pidilite Industries | 9 | 25.3 | −12.1 | Basic Materials |
| | Cummins India | 8 | 36.6 | −12.5 | Industrials |
| | Divi's Laboratories | 6 | 38.8 | −13.4 | Healthcare |
| **Bottom** | Grasim Industries | 6 | 0.75 | −9.0 | Basic Materials |
| | Hindalco Industries | 3 | 2.02 | −9.6 | Basic Materials |
| | Adani Enterprises | 4 | 2.19 | −9.1 | Energy |
| | Tata Motors Passenger Vehicles | 4 | 1.33 | −9.6 | Consumer Cyclical |

The top is the recognisable Indian quality cohort — asset-light,
cash-generative, low-leverage — and the bottom is the capital-intensive,
heavily-geared one. Note this is the *sector-neutral composite*, so a name
can carry a high raw Z and still rank low if it trails its own sector
(Nestlé India, raw Z = 23.8, sits in the bottom quintile against Consumer
Defensive peers).

**The dashboard degrades honestly, view by view rather than all-or-nothing.**
The searchable table, sector heatmap, F-Score scatter, bucket returns, and
rolling spread are all real for India, built from the scores panel and
labeled descriptive wherever they're shown. Only the validation summary —
the one view that would present a point estimate as a statistical result —
renders an explanation of why it's absent instead of an empty table.

**The rolling chart exists, and it is close to the smallest one that can.**
27 monthly cross-sections and a 24-month window leave exactly **3
overlapping windows** (96% month-overlap between any two), all sitting far
inside the DSR band (spreads +0.7% to +3.8%/yr against a ±18% hurdle). This
was built deliberately, at the same 24-month window as the US/Korea charts
for visual consistency, over a shorter-window alternative — see
[FINDINGS.md](FINDINGS.md) for the exact values and why 3 near-identical,
96%-overlapping points confirm nothing about decay one way or the other.

**The PIT guarantee here is weaker, and that is a property of the source.**
Yahoo serves one *current* value per period, so a figure revised later
appears as though it always read that way. Look-ahead is prevented;
restatement-blindness is not, `is_restatement` is always False, and the
load-bearing restatement test has no Indian equivalent because the source
cannot express one. Yahoo also gives only ~5 annual periods, leaving ~4
scoreable years after year-on-year deltas — **enough for a screener, too
short for a backtest**, which is why India is not registered as a backtest
universe.

## Scoped but not built: China / SSE-SZSE

A fifth market was researched with the same standard applied to Brazil,
Korea, and India — build only if a real free source supports it — and,
unlike those three, **China does not clear that bar**, so no adapter exists
here. What was checked:

- **CSRC / SSE / SZSE** publish no bulk structured financial-statement API.
  **cninfo.com.cn** (巨潮资讯网), the CSRC-mandated disclosure portal, is the
  closest analog to EDGAR/CVM/DART — but it is fundamentally PDF-based: its
  query endpoint returns real announcement timestamps and a PDF link, no
  structured line items. Structurally identical to India's BSE half: a real
  date, zero structured values.
- **Tushare Pro**'s `income`/`balancesheet`/`cashflow` endpoints genuinely
  return `ann_date`/`f_ann_date` (a real PIT-capable filing date) alongside
  full structured statements — the closest thing to a Korea/DART-style
  source found. But reaching those endpoints needs 2,000 points, which in
  practice means a paid donation or heavy community-contribution activity,
  not free registration (120 points, insufficient) — so it fails the same
  bar FMP's optional key already respects (degrade gracefully, never
  require payment).
- **AKShare** wraps Eastmoney for full structured statements (keyed by
  period end, not a filing date) and separately wraps cninfo for real
  announcement timestamps (PDF-only) — two disconnected free, no-key
  interfaces that could in principle be joined the way India's adapter
  joins BSE dates to Yahoo values. Unverified: no live check was run
  against real filings the way India's join was (387/387 accounting-identity
  checks) before it was trusted enough to build.
- **Baostock** is free, no key, and its `query_*` functions return a
  genuinely separate `pubDate` (disclosure) vs. `statDate` (period end) —
  a real, if narrow, PIT signal, and the most defensibly free-and-dated
  option found. Its ceiling is what it returns: precomputed *ratios*
  (ROE, margins, current/quick ratio, YoY growth), not raw line items
  (`Assets`, `Liabilities`, `NetIncomeLoss`, ...). `screener/scores.py`'s
  Piotroski/Altman/Ohlson functions are built on raw balance-sheet and
  income-statement figures — a ratio-only source cannot feed them without
  rewriting the score functions themselves, which would break the
  project's central claim that all three scores run **unmodified** across
  every market.

**Verdict**: build a real adapter later only around an AKShare
Eastmoney+cninfo join, live-verified against real filings to the same
standard India's BSE+Yahoo join was (before that verification, it is not
more trustworthy than assuming). Do not build a PIT-fake adapter that
tags period-end dates as filing dates — the entire point of this project's
PIT discipline is that the two are not interchangeable.

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

**For the Korea universe**, `export DART_API_KEY=...` is not optional — DART
requires it on every call, including the free company-code list (unlike
FMP, there is no code path that runs without it). Getting one:

1. Go to <https://opendart.fss.or.kr> and register an account (free; the
   site is Korean-language but a browser translator handles it fine).
2. Under "인증키 신청/관리" ("API key request/management"), request a key.
   Approval is typically near-instant.
3. `export DART_API_KEY="your_40_char_key"` — never commit it. It is read
   only from the environment (`pit_fundamentals/dart_kr_client.py`'s
   `require_api_key()`); nothing in this codebase writes it to a file, and
   `data/` (where the HTTP cache lives) is gitignored regardless.

If the variable is unset, `--taxonomy dart-kr` fails immediately with an
actionable error rather than silently skipping Korea — check with:

```bash
python -c "from pit_fundamentals.dart_kr_client import require_api_key; require_api_key()"
```

**Re-ingesting Korea after an interruption.** Unlike the US EDGAR path
(which keeps an `ingest_log` table and skips already-loaded CIKs),
`run_dart_ingest` has no per-company skip-log — every re-run iterates over
all 120 companies again. What makes re-running cheap anyway is the HTTP
cache: every DART response (financials, share counts, filing dates) is
cached to `data/http_cache` with a 30-day TTL, so a company that completed
on a prior run is served from disk, not the network, on the next one. In
practice that means: first cold run ≈ 20 minutes for all 120 companies ×
9 years (down from 152 minutes before the filing-index and concurrency
fixes — see `dart_kr_client.py`'s module docstring); a re-run after an
interruption or crash only pays network cost for the companies that hadn't
finished, typically seconds to a couple of minutes depending on how far the
first run got. `data/http_cache.sqlite` is **shared across all four
taxonomies** (EDGAR, CVM, DART, BSE) and grows large (~2GB after a full
ingest of all four markets), so deleting it to force a fresh Korea pull
also invalidates the US/Brazil/India caches — fine if you're re-ingesting
everything, wasteful if you only want fresher Korean data. `requests_cache`
supports per-URL cache clearing if you need to be surgical about it.

## Run

```bash
# US (S&P 500, deciles)
python -m pit_fundamentals.ingest --universe sp500   # ~30 min first run (rate-limited, resumable)
python -m screener.backtest                          # scores, composite, buckets -> data/*.parquet
python -m screener.validation                        # NW t-stats + DSR summary -> console + CSV
python -m dashboard.app                              # http://localhost:8050

# Russell 3000 (full ~2,580-name universe, deciles — ~10-15 min incl. rate-limit
# retries; the composite "survives" here, see README/FINDINGS.md for why not to trust it)
python -m pit_fundamentals.ingest --universe russell3000 --db data/pit_r3k.duckdb
python -m screener.backtest    --universe russell3000
python -m screener.validation  --universe russell3000
python -m dashboard.app        --universe russell3000

# South Korea (KOSPI 120, quintiles) — needs DART_API_KEY
python -m pit_fundamentals.ingest --taxonomy dart-kr --years 2015 2016 2017 2018 2019 2020 2021 2022 2023
python -m screener.backtest    --universe kospi
python -m screener.validation  --universe kospi
python -m dashboard.app        --universe kospi

# India (top 100 by market cap) — screener only, no key needed
python -m pit_fundamentals.ingest --taxonomy bse-in --db data/pit_in.duckdb
python -m screener.backtest --universe india
python -m dashboard.app     --universe india

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
  dart_kr_client.py    # South Korea/DART adapter (verified on 21 KOSPI names)
  india_client.py      # India: BSE filing dates joined to Yahoo values
  ingest.py            # CLI: --taxonomy {us-gaap, cvm-br, dart-kr, bse-in}
screener/           # universe, scores, normalize, composite, backtest, validation
  universe_br.py       # curated B3 blue-chip ticker->CNPJ crosswalk
  universe_kr.py       # KOSPI crosswalk loader (120 names) + listing dates
  universe_in.py       # India crosswalk loader (100 names)
  india_universe.csv   # NSE ticker -> BSE scrip, tracked
  kospi_universe.csv   # the universe itself, tracked so a clean clone reproduces it
  universes.py         # Universe defs: suffix, bucket count, paths, currency
dashboard/          # Plotly Dash app (6 views; hides backtest views for screener-only universes)
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
