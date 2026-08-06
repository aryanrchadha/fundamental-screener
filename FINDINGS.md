# FINDINGS — Composite Fundamental Screener

*Research memo covering four markets — the S&P 500 and the broader Russell
3000 (both SEC EDGAR), the KOSPI 120 (Korea's DART), and the BSE 100
(India) — plus survivorship-corrected re-runs of the three that support a
backtest. Scores are sector-neutral z-scores; buckets are equal-weight; the
spread is the top bucket minus the bottom. All fundamentals are
point-in-time, gated by the real filing date in every market.*

## Cross-market summary

Composite (LASSO where fitted, equal-weight prior otherwise), top-minus-
bottom bucket:

| Market | Names | Buckets | Months | Ann. return | NW t | DSR | Survives 95%? |
|---|---|---|---|---|---|---|---|
| **US** — S&P 500 | 503 | deciles | 167 | −0.7% | −0.29 | 0.092 | **No** |
| US, survivorship-corrected | 294→493 | deciles | 167 | −1.3% | −0.42 | 0.067 | **No** |
| **US** — Russell 3000 (top 300) | 300 | deciles | 167 | +0.4% | +0.10 | 0.170 | **No** |
| **Korea** — KOSPI 120 | 120 | quintiles | 105 | +2.4% | +0.33 | 0.238 | **No** |
| Korea, survivorship-corrected | 107→120 | quintiles | 105 | +2.4% | +0.33 | 0.238 | **No** (identical) |
| **India** — BSE 100 | 100 | quintiles | 26 † | +2.1% † | +0.34 † | 0.233 † | **No** † |

**† India's row is DESCRIPTIVE, not inferential, and should not be read as
a test.** It is included for completeness rather than omitted, because the
numbers are computable and hiding them would be its own distortion — but
the sample cannot support the statistics beside it. The reason is
measured, not asserted: across the 27 monthly cross-sections the composite
ranking has a **median month-to-month Spearman correlation of 0.998**. The
fundamental content updates only **three times** (the FY2024, FY2025 and
FY2026 annual filings); the slight monthly drift is the price term inside
Altman Z, not new information. So the nominal N of 26 monthly observations
carries an effective N closer to 3, and since standard errors scale as
1/√N, a t-statistic computed on 26 overstates precision by roughly
√(26/3) ≈ 2.9×. Deflating the +0.34 by that factor gives ≈ +0.11.

The conclusion is unaffected either way, which is why including the row
costs nothing: at +0.34 the naive t-stat is already far from significance,
so India neither strengthens nor weakens the finding. `screener/backtest.py`
still refuses to emit a validation table for India (`backtestable=False`),
and the dashboard still hides the views that would depend on one.

**Read across the table: six market-configurations, zero survivors.**

## Validation summary — S&P 500 (the primary sample)

| Strategy | Ann. return (D10−D1) | Ann. Sharpe | NW t-stat (lag 4) | Skew | Kurtosis | DSR | Survives 95%? |
|---|---|---|---|---|---|---|---|
| Piotroski F-Score | −1.7% | −0.18 | −0.69 | −0.39 | 3.80 | 0.043 | **No** |
| Altman Z-Score | −4.1% | −0.42 | −1.50 | −0.19 | 3.86 | 0.004 | **No** |
| Ohlson O-Score | −6.0% | −0.82 | −3.00 | −0.44 | 4.47 | 0.000 | **No** |
| Composite (LASSO) | −0.7% | −0.08 | −0.29 | −0.51 | 3.25 | 0.092 | **No** |

Newey-West lag chosen by floor(4·(T/100)^(2/9)) = 4. The Deflated Sharpe
Ratio uses N_trials = 4 (F, Z, O, composite — the honest count of related
hypotheses examined on this data) and the empirical skewness/kurtosis of
each spread series.

## The finding, stated plainly

**None of the three classical scores, nor the LASSO composite, produced a
positive decile spread in the large-cap US universe after 2012 — let alone
one that survives multiple-testing correction.** The point estimates are
mildly negative across the board. The starkest result is the O-Score: the
"safe minus distressed" spread lost ~6%/yr with a NW t-stat of −3.0. In
this sample, sector-neutral distress ranking was a *contrarian* signal —
consistent with the post-publication literature on the distress-risk
anomaly and with the QE-era pattern of junk-led rallies inside the S&P 500.

**The full-sample number understates how uninformative the ranking is.**
Looking at mean *decile-level* (not spread) annualized returns across the
whole sample, there is effectively no gradient at all:

| Decile | 1 (worst) | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 (best) |
|---|---|---|---|---|---|---|---|---|---|---|
| Ann. return | 21.0% | 18.3% | 18.6% | 20.1% | 16.0% | 19.5% | 18.4% | 20.1% | 18.2% | 20.3% |

Decile 1 (worst composite score) had one of the *highest* mean returns of
any decile, and decile 5 (middle) had the lowest — correlation between
decile rank and mean return across the full sample is essentially zero
(ρ = −0.02). Restricting to 2019 onward, once the scored universe is large
enough (see coverage below) for deciles to hold more than a handful of
names, the correlation turns weakly positive (ρ = 0.16) — a hint of the
expected monotonic gradient, but far too weak to call an effect: it is not
statistically distinguishable from noise once look at through the NW/DSR
lens, and it never translates into a full-period decile-spread number that
clears significance.

**Annual D10−D1 spread by calendar year** makes the composite's full-sample
number look worse than the post-2018 regime alone would suggest:

| Year | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Spread | −11.3% | −27.0% | +0.2% | +6.2% | +8.9% | +4.9% | +3.3% | +4.8% | −1.3% | −1.6% | +2.3% | −0.2% | −0.1% | −0.4% |

The two catastrophic years (2012: −11.3%, 2013: −27.0%) coincide exactly
with the thinnest part of the sample: only **120–153 companies** had a full
composite score each month in 2012 (out of 501), so each decile held on the
order of 12–15 names — a sample size where one or two large idiosyncratic
moves can dominate a "decile average." 2014–2019 was consistently positive
(if modest); 2020–2025, once coverage plateaus above 250–350 names/month,
the spread is essentially flat, oscillating within ±2.3%/yr with no
sustained direction either way. **The honest read is not "the effect
decayed" so much as "the effect was never reliably there, and the earliest,
noisiest years are doing most of the work in the negative full-sample
number."**

### Why coverage is what it is

Piotroski's F-Score has the highest exclusion rate of the three (60–70%
missing in the early sample, 39–49% later) because it requires the most
tags and the weakest-coverage tag among them: `GrossProfit` is directly
tagged for only ~42% of company-years, and its fallback `CostOfRevenue` for
just ~23% more — so gross-margin (criterion 8) alone accounts for a large
share of Piotroski's missingness. `LongTermDebtNoncurrent` is tagged for
~58% of company-years, though the leverage criterion only excludes when it
is present in one year and absent in the other (permanently-absent-in-both,
i.e. genuinely no long-term debt, is treated as "no increase" and does not
exclude). Altman and Ohlson need fewer tags and are less exposed to the
gross-margin gap, hence their consistently lower exclusion rates (~20–50%
vs. Piotroski's ~39–70%).

**Financials (76 of 503 constituents) and most REITs (part of the 31 Real
Estate names) are excluded from all three scores by construction, every
year, regardless of tagging quality** — banks and REITs don't file
classified balance sheets, so `AssetsCurrent`/`LiabilitiesCurrent` simply
do not exist for them. That is ~21% of the index permanently out of scope,
on top of the missing-tag exclusions above. It is also why Energy (21
names) and Utilities (31 names) repeatedly triggered the small-sector
universe-level z-score fallback during the backtest — GICS sectors with a
Financials-sized population next to them are naturally thin once you
subtract the always-excluded names.

### What the LASSO actually learned

The full annual coefficient history (feature order: F-Score, Z-Score,
O-Score, all sector-neutral and sign-aligned so higher = better):

| Refit date | α | F-Score | Z-Score | O-Score |
|---|---|---|---|---|
| 2014-01 | 0.0001 | −0.0304 | +0.0045 | −0.0248 |
| 2015-01 | 0.0030 | −0.0185 | −0.0009 | −0.0120 |
| 2016-01 | 0.0100 | −0.0057 | −0.0000 | −0.0093 |
| 2017-01 | 0.0100 | −0.0029 | −0.0000 | −0.0062 |
| 2018-01 | 0.0100 | −0.0006 | −0.0000 | −0.0053 |
| 2019-01 | 0.0100 | −0.0015 | −0.0000 | −0.0052 |
| 2020-01 | 0.0100 | −0.0000 | +0.0000 | −0.0045 |
| 2021-01 | 0.0300 | 0 | 0 | 0 |
| 2022-01 | 0.1000 | 0 | 0 | 0 |
| 2023-01 | 0.0100 | −0.0000 | −0.0000 | −0.0015 |
| 2024-01 | 0.0100 | 0 | 0 | 0 |
| 2025-01 | 0.0100 | 0 | 0 | 0 |

Two things stand out. First, **the Z-Score coefficient is essentially
always zero** — across every single refit from 2016 onward, LassoCV found
no stable relationship between sector-neutral Altman Z and forward returns
worth keeping, even at the smallest tested α. Second, **whenever the
F-Score and O-Score coefficients are nonzero, they are negative** — i.e.
the model's best expanding-window fit consistently found that
higher-Piotroski, safer-Ohlson names had *lower* forward 6-month returns
than the cross-section, the opposite of the textbook direction. This is
consistent with the annual O-Score spread finding above (distress ranking
was contrarian) and explains why the composite's realized spread, while
still negative, is closer to zero than the O-Score alone: the LASSO is
partially cancelling a signal it (correctly, given the training data)
believes points the wrong way, and by 2021 the CV-selected α (0.03–0.1, an
order of magnitude higher than the 2014–2020 values) shrinks everything to
zero outright.

## Decay

The full-period cumulative composite spread is −15.9%, split −16.7% in the
first half (2012–2018) and +1.0% in the second (2019–2025). Combined with
the annual breakdown above, this is better read as "no reliable effect at
any point, with a very noisy, thin-sample-driven drawdown concentrated in
2012–2013" rather than "a real effect that decayed."

The rolling 24-month annualized spread (dashboard "Rolling spread" tab, 144
overlapping windows) averages −0.1%/yr with a standard deviation of 7.0
points, ranging from −22.7% (window ending Feb 2014 — still inside the
noisy thin-coverage period) to +9.0% (window ending Feb 2017). Only **6.0%
of the 144 rolling windows** have a ±1.96-SE band that excludes zero — i.e.
in 94% of 24-month windows, the spread is statistically indistinguishable
from no effect at all, exactly what the full-sample NW t-stat and DSR
already imply, just visualized month by month.

Relative to the original publications — Piotroski (2000) reported ~7.5%/yr
high-minus-low on 1976–1996 data, concentrated in small/value stocks — the
effect in large-cap S&P 500 names post-2012 is, on this evidence, absent,
not merely diminished.

## PIT gating proof (for the skeptical reviewer)

The load-bearing test (`pit_fundamentals/tests/test_pit_restatement.py`)
found a genuine restatement in the ingested data rather than needing its
synthetic fallback: **Agilent Technologies (ticker `A`), tag `Assets`,
fiscal year ended 2014-10-31**, originally reported at **$10.831B** in the
10-K filed 2014-12-22, later revised to **$10.815B** (a ~0.15%, $16M
correction) in a filing dated 2015-12-21. `get_fact_as_of` returns the
original $10.831B figure for any `as_of_date` before 2015-12-21 and the
corrected $10.815B for any date on or after — proving the gate operates on
`filed_date`, not `fiscal_period_end`, on real EDGAR data, not a
constructed example.

## Limitations (read before quoting any number)

1. **Survivorship bias**: the default universe is *today's* S&P 500
   membership applied backward. This inflates absolute decile returns,
   though it affects both legs of the spread. `USE_PIT_UNIVERSE = True`
   applies Wikipedia's historical changes table, but that table is itself
   incomplete ("selected changes"), so this is mitigation, not correction.
2. **Large-cap only**: Piotroski's original effect concentrated in small,
   thinly-covered value stocks. Finding nothing in the S&P 500 does not
   prove the signals are dead in the Russell 2000.
3. **Ohlson coefficients are the 1980 textbook set**, not refit (a proper
   refit needs a default-event sample — out of scope here), and SIZE omits
   the GNP price deflator (harmless cross-sectionally, wrong in levels).
4. **EBIT approximation**: Altman's EBIT is net income plus tax and
   interest add-backs *where those tags are filed*; when absent, EBIT is
   understated rather than fabricated from an assumed tax rate.
5. **Financials (76/503 constituents) and most REITs are structurally
   excluded** from all three scores every year — no classified balance
   sheet means no `AssetsCurrent`/`LiabilitiesCurrent`. Combined with
   missing-tag exclusion (worst for Piotroski, driven mainly by
   `GrossProfit`/`CostOfRevenue` coverage of ~42%/23%), fully-scored
   coverage ran ~120–153 names/month in 2012, crossing 250 around 2019 and
   reaching ~350+ by 2025 (out of 501 constituents with price history).
6. **Total liabilities fallback** (Assets − StockholdersEquity) puts
   noncontrolling interests into liabilities, slightly overstating leverage
   for consolidated groups.

## US extension: Russell 3000 (same taxonomy, mostly the same names)

The S&P 500 result above is a large-cap-only sample by construction. Before
reaching for a second regulator, the more direct question is whether the
same US-GAAP taxonomy and the same scoring functions find anything
different in a wider, less mega-cap-concentrated US universe. `--universe
russell3000` answers that without introducing a new data source or a new
accounting standard: same SEC EDGAR/us-gaap facts, same
`screener/scores.py` functions, same 2012–2025 date range and monthly
rebalance — only the ticker list changes, sourced from BlackRock's IWV ETF
holdings (the standard free proxy for Russell 3000 membership, since the
licensed FTSE Russell constituent file is a commercial product). The
committed run caps the universe to the **top 300 names by index weight**
(`config.RUSSELL3000_MAX_TICKERS`); nothing downstream assumes the cap.

**Coverage.** 300 tickers ingested (650,339 fact rows), 187 of 297 names
fully scored in the latest cross-section — 297, not 300, because three
tickers' EDGAR companyfacts came back empty or near-empty (a recently
listed name with no historical XBRL yet is the typical cause). Exclusion
counts mirror the S&P 500 pattern exactly: Piotroski excludes the most
(108/297, driven by the same `GrossProfit`/`CostOfRevenue` coverage gap),
Altman and Ohlson fewer (62/297 and 57/297).

| Strategy | Ann. return (D10−D1) | Ann. Sharpe | NW t-stat | Skew | Kurtosis | DSR | Survives 95%? |
|---|---|---|---|---|---|---|---|
| Piotroski F-Score | −4.2% | −0.32 | −1.14 | −0.87 | 6.57 | 0.011 | **No** |
| Altman Z-Score | −4.4% | −0.40 | −1.58 | −0.24 | 2.91 | 0.005 | **No** |
| Ohlson O-Score | −7.1% | −0.74 | −2.58 | +0.50 | 4.59 | 0.000 | **No** |
| Composite (LASSO) | +0.4% | +0.03 | +0.10 | −0.40 | 4.59 | 0.170 | **No** |

**The wider universe does not rescue the signal — if anything it sharpens
the same failure.** The individual scores are directionally identical to
the S&P 500 table (all three negative, O-Score the worst by a wide margin,
consistent with distress ranking being contrarian in this sample rather
than a large-cap-specific artefact). The composite's point estimate is
closer to flat here (+0.4%/yr vs. the S&P 500's −0.7%/yr) but still carries
a DSR of 0.170, nowhere near the 0.95 bar, and the annual coefficient
history shows the identical shrinkage pattern: nonzero, negative F/O
coefficients through 2018, shrinking to exactly zero for 2019–2022 as the
CV-selected α jumps an order of magnitude, a small nonzero O-Score
coefficient returning 2023–2025. The Z-Score coefficient never exceeds
−0.0006 in magnitude at any refit (effectively zero throughout), the same
pattern as the S&P 500 — LassoCV finds no stable relationship between
sector-neutral Altman Z and forward returns in either US universe.

**Decay shape.** 167 months, full-period cumulative composite spread −8.0%
(vs. the S&P 500's −15.9%), split +3.3% in the first half and −10.9% in the
second — the same qualitative "no reliable effect, concentrated drawdown"
pattern as the S&P 500's own first/second-half split, on an independently
constructed universe with a different, broader set of names. The rolling
24-month chart (144 of 167 windows populated) shows **0 windows clearing
the DSR band in either direction** — no false-positive stretch of the kind
the S&P 500's *survivorship-corrected* run produced (20 of 144 windows
there, discussed and explicitly not oversold in the rolling-decay section
below). Mean annualized spread across windows is +0.9%/yr against a median
±26.2%/yr hurdle; by window-year, small positive spreads 2015–2019
(+4% to +9%), a return to negative territory in 2021–2022 (−11%/−6%) that
the S&P 500's own rolling windows do *not* show over the same years
(+3%/+2%, still positive there) — a genuine divergence between the two US
universes worth flagging rather than glossing over, though neither reading
clears the DSR band in either direction — and −22%/−17% in the earliest
2013–2014 windows, the same short-history-inflates-volatility effect the
S&P 500's earliest windows show, here on a differently-selected universe
rather than a coincidence of shared tickers.

**What this run actually tests — stated honestly, because it is less than
the section title implies.** Checking the two ticker sets directly: **286
of the 300 Russell 3000 names here are already S&P 500 constituents**; only
14 are not (`ALAB`, `AU`, `BE`, `EA`, `LNG`, `NET`, `NTRA`, `NU`, `RKLB`,
`RVMD`, `SNOW`, `SPCX`, `SPOT`, plus Berkshire under its bare-concatenated
ticker form). Weight-ranking a ~2,580-name free proxy and then capping to
the top 300 by weight does not, in practice, sample a broader universe —
it re-selects almost exactly the same mega-caps the S&P 500 already
contains, because both rankings are dominated by market capitalization.
**This run therefore does not meaningfully test "is the effect concentrated
outside the S&P 500's 503 names" — that would require sampling by name
count or including the smaller Russell 3000 constituents the weight cap
excludes, which remains untested.** What it does show, more modestly: an
independently constructed universe (different source, different sector
labels, a different tie-breaking process for the handful of non-overlapping
names) that is 95% the same companies reproduces the same result to within
noise — a consistency check on the pipeline and the finding's robustness to
universe-construction detail, not a test of whether the effect lives in
smaller US names. Falsifying the "just the S&P 500" hypothesis properly
would need `config.RUSSELL3000_MAX_TICKERS = None` (or a materially higher
cap) run against the genuinely non-overlapping mid/small-cap tail — left as
future work, and flagged here rather than implied by this run's title.

**What it does not establish either**: survivorship correction. Unlike the
S&P 500's Wikipedia constituent-changes table, there is no free historical
Russell reconstitution feed, so `Russell3000Universe.membership()` always
returns `None` — this run is silently subject to the same look-ahead risk
Wikipedia's table (imperfectly) mitigates for the S&P 500, and that
limitation is left explicit rather than worked around with fabricated
membership dates.

## International extension (Brazil / B3): what was proven and what wasn't

`pit_fundamentals` now ingests a second, real, free taxonomy — Brazil's CVM
Dados Abertos — for 16 Ibovespa blue chips (`screener/universe_br.py`). This
was chosen over India/China/South Africa because none of those have a free,
structured, EDGAR-equivalent bulk fundamentals source; CVM does.

**Proven, with real numbers**: `get_fact_as_of`/`build_pit_snapshot` and the
unmodified Piotroski/Ohlson scoring functions work identically on CVM
account-code data. 13 of 16 tickers scored (F-Score 3–8, O-Score −7.0 to
−10.7, all comfortably distress-free, consistent with these being the
largest, most stable names on the exchange). The 3 banks and 1 insurer were
excluded automatically — Brazilian financial institutions file under COSIF,
which reuses BPA/BPP/DRE's numeric codes for entirely different accounts
(confirmed concretely: code `"1.01"` is *Ativo Circulante* for an
industrial filer but *Caixa e Equivalentes de Caixa* for Banco do Brasil,
Bradesco, and Itaú, and BB Seguridade's income-statement codes use
insurance-specific labels that don't match the industrial DRE template
either). The adapter verifies each account's text label before accepting
its value and drops mismatches — the same "exclude and log, never
fabricate" discipline as the US path, just triggered by a different
mechanism (label verification vs. missing classified-balance-sheet tags).

**Not proven / explicitly out of scope**: this is a scoring demonstration,
not a second backtest. There's no free B3 historical constituent list, no
FX-aware return pipeline, and — a genuine finding from reading the raw
data, not a hypothetical caveat — CVM's `composicao_capital` (share count)
file carries no scale metadata analogous to `ESCALA_MOEDA`. Cross-checking
real filings found Petrobras's raw share count matches its known ~13B
shares directly, while Vale's raw figure (~4.5M) is off by roughly 1000x
from its known ~4.5B shares — implying inconsistent self-reported scale
across filers with no way to detect which convention a given company used
from the file alone. Altman Z's market-cap term is flagged unreliable for
CVM-sourced names as a result; this was caught by actually inspecting
values against known real share counts, not assumed.

## International extension (South Korea / DART): from untested to verified

A third taxonomy adapter, `pit_fundamentals/dart_kr_client.py`, targets
Korea's DART OpenAPI (the natural next candidate after Brazil, per the
prior extension's own recommendation). It was first built without a
registered API key — DART requires one (`crtfc_key`) for every call,
including the free company-code list, and none was available initially —
using only official documentation plus two independently citable sources:
a Korean quant-investing tutorial's worked example and the open-source
DartLab project's documentation that DART tagging is genuinely less
consistent than CVM's fixed codes (the same concept appears as
`ifrs-full_Revenue`, `dart_Revenue`, or bare `Revenue` depending on the
filer). A key was later obtained and the adapter was run against
Samsung Electronics' real FY2022-2023 filings — the exercise is worth
recording in full because it caught real bugs the pre-key version could
not have:

1. **The Statement of Changes in Equity trap.** Samsung's real filing
   tags **seven different values** — total equity, per-component balances,
   NCI- vs. parent-attributable net income subtotals — under the single
   `account_id` `"ifrs-full_Equity"`, all within the SCE section alone.
   The original code processed every statement section indiscriminately,
   which would have silently produced conflicting `StockholdersEquity`
   facts for the same fiscal year with no principled way to pick the
   right one. Fix: only Balance Sheet / Income Statement / Cash Flow
   sections are ever mapped; SCE (and the harmless-but-redundant CIS,
   which merely duplicates the income statement's net income) are
   excluded entirely.
2. **The EBIT guess was wrong.** The original mapping guessed the core
   IFRS concept `ProfitLossFromOperatingActivities` for operating income.
   It never appears in Samsung's real filing — Samsung tags operating
   income (영업이익) with the Korea-specific extension
   `dart_OperatingIncomeLoss` instead, exactly the kind of tagging
   divergence the module's own pre-key docstring had flagged as a risk
   without being able to confirm it either way.
3. **Long-term debt needed summing, not a single lookup.** IFRS has no
   single "total long-term debt" line; Samsung's real filing confirms
   non-current bonds and non-current bank loans are reported as two
   separate Balance Sheet rows. The fix sums both confirmed real
   component tags rather than guessing a combined line that doesn't
   exist.

**Post-fix, live-verified result**: `ifrs-full_Assets` (₩455.9T) equals
`ifrs-full_Liabilities` (₩92.2T) plus `ifrs-full_Equity` (₩363.7T) exactly,
and Ohlson O-Score computes end-to-end through the **unmodified**
`screener/scores.py` functions, returning −14.8 — appropriately deep in
distress-free territory for one of the world's largest, most stable
companies. DART's financial-statement endpoint — confirmed by direct
inspection, not assumed — carries no share-count field anywhere in its
response; that data lives in a separate DART API family, since mapped
(see "Shares outstanding" below).

The meta-finding worth keeping: **the pre-key version's stated
low-confidence flags were directionally correct** (it explicitly called
out the EBIT mapping and the SCE-style risk as uncertain) but couldn't
have caught the exact failure mode without a live response — this is the
concrete argument for why "build without live testing, clearly flagged"
is a reasonable fallback but not a substitute for the real thing.

### The 21-name crosswalk sweep: three more real bugs

The crosswalk was then extended from Samsung alone to **21 KOSPI blue
chips**, every corp_code resolved from DART's own 118,508-entity corpCode
registry by KRX stock code (never from memory), each then live-verified
against the accounting identity Assets = Liabilities + Equity holding
*exactly* on extracted values. The first sweep failed the identity for 15
of 20 FY2022 extractions and returned 5 as empty — and every failure
traced to a real, distinct data-shape issue Samsung's filings alone could
never have revealed:

1. **Candidate priority vs. filing row order.** SK Hynix's FY2022 and
   FY2023 balance sheets both carry `ifrs-full_Equity` (total, including
   noncontrolling interests) *and*
   `ifrs-full_EquityAttributableToOwnersOfParent` as separate real rows —
   and the template's row order **flipped between the two years**. The
   dedup was keeping whichever row came first, so FY2022 got parent-only
   equity and failed the identity by exactly the ₩24.2B of NCI. Candidate
   priority (total first) is now enforced explicitly in the dedup, with a
   regression test covering both row orders.
2. **Single-statement vs. two-statement IFRS presentation.** SK Hynix,
   NAVER, Kakao, and Amorepacific present one combined statement of
   comprehensive income: their *entire* income statement lives under
   `sj_div='CIS'` with no `IS` section at all. The earlier Samsung-derived
   fix had excluded CIS as "redundant" — true for Samsung's two-statement
   format, fatal for single-statement filers, whose Revenue and
   NetIncomeLoss silently vanished. CIS is now mapped (dual-statement
   filers' duplicate rows collapse harmlessly in dedup); SCE remains
   excluded.
3. **Restated years are served from much later documents.** For FY2022,
   DART returned Hyundai Motor's and Kakao's figures from documents
   received in **March 2024** — the filing-date search window (originally
   Jan–Jun of year+1) couldn't match them, and the rows were dropped. The
   window is now +1..+2 years, with a guarded fallback: the first 8 digits
   of `rcept_no` are the receipt date, an assumption explicitly **not**
   relied on earlier but since confirmed empirically on four independent
   real filings where both fields were visible side by side.

Post-fix: **37/40 company-years pass the exact accounting identity**; the
other three are the FY2022 financial institutions (KB, Shinhan, Samsung
Life), for which DART itself returns status 013 "no data" — the endpoint's
documented historical exclusion of financials, whose coverage begins
FY2023. From FY2023 they return liquidity-order balance sheets with no
current/non-current split, so O-Score excludes them automatically via
missing tags — the same principled financial-institution exclusion as the
US (missing classified-balance-sheet tags) and Brazil (COSIF label
mismatch) pipelines, arrived at through a third distinct mechanism.

O-Scores for all 18 non-financials, unmodified pipeline: Samsung
Electronics safest (−14.85), then LG Corp (−13.94), Celltrion (−13.50),
Hyundai Mobis (−13.44), Amorepacific (−13.27) … SK Hynix mid-pack (−11.14,
consistent with its 2023 memory-downcycle loss year), Kakao low (−10.76,
₩1.8T net loss in 2023), and KEPCO riskiest (−9.39, the famously
debt-laden utility). The ordering required no tuning to look like this —
it falls out of the 1980 coefficients on honestly-mapped data, which is
about as good a sanity check as a bankruptcy score can get without a
default sample.

### Shares outstanding: the second endpoint, and why the class label mattered

The one remaining gap — share counts, needed for Piotroski's dilution
criterion and Altman Z's market-cap term — was closed by wiring DART's
separate `stockTotqySttus` ("주식의 총수 현황") API, since share counts
appear nowhere in the financial-statement response. Two things are worth
recording.

**First, the data validated itself.** DART reports issued, treasury, and
circulating counts per share class; the identity *issued − treasury =
circulating* holds on **every row of all 42 company-years**, so the
circulating figure is internally consistent rather than trusted blind.
The mapped values then reproduce known real corporate actions without any
tuning: Celltrion 137.8M → 207.2M across its December-2023 Healthcare
merger, SK Innovation 84.2M → 95.2M from its 2023 capital raise, KB
Financial 389.6M → 378.7M and Kia 400.9M → 396.2M from buyback-and-cancel
programmes. A share series that independently rediscovers the year's
actual equity events is about as strong a correctness signal as this kind
of mapping admits.

**Second, share-class selection was the real trap** — and a
single-company check would have sailed past it. The class label `se` has
no consistent spelling: `보통주` for most filers, but `의결권 있는\n보통주`
for Shinhan (with an embedded newline) and `의결권 있는 주식\n(보통주)` for
LG Electronics. Exact-match returned *nothing* for those two. Worse, the
obvious fallback — the `합계` (total) row — is wrong, because it bundles
preferred stock: for Hyundai Motor that is 202.3M common against 261.3M
total, so taking the total would overstate market cap and corrupt the
dilution check by 23%. A substring test on `보통주` resolves all four
observed spellings while excluding `우선주` (preferred) and Amorepacific's
`종류주` (a separate class share). Only the common class is mapped, which
deliberately mirrors the US path's own convention of pairing common
shares with the common ticker's price — a shared limitation applied
consistently, not a Korea-specific defect.

With shares mapped, **all three scores compute for Korea**: Piotroski
16/21, Altman Z 18/21, Ohlson O 18/21. Altman required only KRX prices
(yfinance `.KS` tickers) on top of the DART shares; Samsung's implied
market cap of ₩469T matches its real common-only capitalisation, and the
Z ranking puts KEPCO at **0.28**, deep in the distress zone — the correct
read for a utility carrying roughly ₩200T of debt after years of selling
electricity below cost, and a pleasing cross-check that Piotroski's
independent verdict on the same firm (F = 7, i.e. *improving*) is not
contradictory but complementary: KEPCO is a highly distressed balance
sheet that was getting better year-over-year.

The remaining exclusions are structural rather than mapping gaps, and
worth stating so they are not mistaken for bugs: NAVER and SK Telecom
report no gross-profit or cost-of-sales line whatsoever — service
companies presenting a single `ifrs-full_OperatingExpense` — so
Piotroski's Δ-gross-margin criterion excludes them, exactly as it excludes
the many US service companies whose `GrossProfit` tag is likewise absent
(directly tagged for only ~42% of US company-years). Deriving a
gross-profit proxy from operating expense would be fabrication, so the
company-year is dropped and logged instead.

## The Korean backtest: a second market, and what it says about the first

Wiring KRX prices in turned Korea from a scoring demonstration into a real
backtest. Universe: the **120 most liquid KOSPI names**, selected by a
stated rule (DART's own 784-company KOSPI filer list, ranked by median
daily traded value from 2014-2025 Yahoo history) rather than a
hand-assembled list. Fundamentals FY2015–2023, 105 monthly rebalances
(2017-03 → 2025-11), median 93 fully-scored names per month, **quintiles**
rather than deciles because 120 names split ten ways leaves ~9 per bucket.

| Strategy | Ann. return (D5−D1) | Ann. Sharpe | NW t-stat | Skew | Kurtosis | DSR | Survives 95%? |
|---|---|---|---|---|---|---|---|
| Piotroski F-Score | **+5.9%** | 0.38 | 1.02 | −0.01 | 2.84 | 0.519 | **No** |
| Altman Z-Score | −3.2% | −0.17 | −0.45 | 1.03 | 5.62 | 0.059 | **No** |
| Ohlson O-Score | −2.3% | −0.16 | −0.43 | −0.79 | 4.00 | 0.062 | **No** |
| Composite (LASSO) | +2.4% | 0.11 | 0.33 | 1.16 | 7.61 | 0.238 | **No** |

**Nothing survives in Korea either — but the failure has a different
shape, which is the interesting part.** In the US every one of the four
strategies had a *negative* point estimate, and the O-Score's was
significantly negative (t = −3.0): distress ranking was actively
contrarian. In Korea the Piotroski F-Score is *positive* (+5.9%/yr, the
best Sharpe of any score in either market) and the quintile returns are
close to monotone across the top four buckets — D5 19.6% > D4 15.7% >
D3 13.7% > D2 11.2% annualised. That is the gradient the literature
predicts.

It still does not clear the bar, for two honest reasons. First, D1 — the
*worst*-ranked quintile — returned 17.2%/yr, second only to D5, so the
monotone top does not translate into a long-short spread; the bottom
bucket did nearly as well as the top. Second, a Newey-West t-stat of 1.02
over 105 months is simply not significant, and the Deflated Sharpe Ratio
(0.519) sits far below the 0.95 bar once the four-hypothesis correction
and the return distribution's fat tails are applied. The composite's
kurtosis of 7.6 is the highest of any series in this project, and DSR
penalises it accordingly. The walk-forward LASSO again shrank every
coefficient to zero, so the composite is the equal-weight prior throughout.

The defensible reading is *"not yet ruled out in Korea, ruled out in the
US"* — a weaker claim than "the effect lives in emerging markets", and one
that would need a wider universe and a longer sample to sharpen.

### Currency: handled by not converting

Fundamentals and prices are both in KRW, so every ratio the scores compute
(market cap / total liabilities, sales / assets) is unit-free, and the
long-short spread is a local-currency return in which an FX translation
would multiply both legs by the same factor and cancel. No conversion is
applied and none is needed. The corollary is that the Korean and US
**levels above are not directly comparable** without conversion — only
their t-stats and Sharpes, which are unit-free, are.

### Limitations specific to this backtest

1. **Survivorship bias, again.** The 120 names are today's liquid KOSPI
   ranked over the full sample and applied backwards; delisted and
   liquidity-losing companies are absent. There is no free historical
   KOSPI-200 constituent table to correct with, so this is the same known
   bias as the S&P 500 default, not a smaller one.
2. **Liquidity selection is itself a filter.** Ranking by traded value
   selects large, heavily-covered names — precisely where Piotroski's
   original small-cap effect is least expected to appear.
3. **The sample is short.** 105 months with a ~93-name cross-section is
   thin next to the US run's 167 months, and the first usable date is
   dictated by DART's structured data beginning at FY2015.
4. **Sector-neutralisation uses KSIC divisions, not GICS.** GICS is
   licensed; KSIC is Korea's official statistical classification and comes
   straight from DART. It is a defensible peer grouping but not the same
   grouping the US path uses, so cross-market comparison of the
   *sector-neutral* step is approximate.

## Rolling out-of-sample decay: Korea, and the contrast with the US

The rolling chart's band is now derived from the Deflated Sharpe Ratio, as
the brief asked, rather than the plain ±1.96 SE band an earlier revision
shipped. For each 24-month window it plots the spread that window would
have needed for **its own DSR to reach 95%**, given its volatility,
empirical skew and kurtosis, length, and the four related scores examined
on this data. The construction is the DSR algebraically inverted, and the
correspondence is exact: across 177 test windows, "outside the band" and
"that window's DSR ≥ 0.95" agree 100% of the time. A line inside the band
marks a stretch that would **not** have survived the same correction the
summary table applies.

Getting there required fixing an error of my own: the first version of this
band plotted SR0 — the expected best-of-four-random Sharpe — and described
it as a stricter bar than the SE band. It is the *looser* one; the expected
maximum of four draws sits near the 1.05σ level, below a 1.96σ interval.
A unit test comparing the two band widths is what caught it.

**Korea (82 windows, Feb 2019 – Nov 2025), median hurdle +13.9%/yr:**

| Rolling-window year | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|
| Mean annualized spread | **+24%** | +8% | −14% | −26% | −2% | −1% | −2% |

**12 of 82 windows clear the DSR hurdle, and every one of them ends between
February 2019 and May 2020.** Nothing since comes close. The first half of
the rolling sample averages −0.1%/yr and the second half −4.1%/yr. This is
the clearest decay signal anywhere in the project: a genuine early stretch
in which the Korean composite beat a multiple-testing-corrected benchmark,
followed by five years in which it did not.

One caveat, stated because it cuts against the finding's strength: those
clearing windows look back over March 2017 – May 2020, where the median
cross-section held 80 fully-scored names (minimum 33) against 99 in the
period after. The strongest stretch therefore leans partly on the thinnest
data, and some of that +24% is likely small-cross-section noise rather than
signal.

**US (144 windows, Dec 2013 – Nov 2025), median hurdle +18.5%/yr:**

| Window year | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Static | −21% | −19% | −3% | +4% | +6% | +5% | +3% | +2% | +3% | +2% | −2% | −1% | +0% |
| Surv.-corrected | −23% | −19% | −0% | +12% | +6% | +2% | +4% | +4% | −4% | −9% | −1% | +0% | +0% |

**The static US run clears the hurdle in 0 of 144 windows.** Its shape is
also different from Korea's: a deep negative patch in 2013–2015 driven by
the thin early cross-section (120–150 scored names), then a mildly positive
plateau of +2% to +6% from 2016–2022 that never approaches the +18.5%
hurdle, then back to flat. No decay, because there was never anything to
decay from.

### A result worth not overselling: the corrected US run *does* clear 20 windows

The survivorship-corrected US series behaves differently enough to be worth
recording. **20 of its 144 windows clear the DSR hurdle** — all ending
between September 2015 and July 2020, with realized spreads of +8.8% to
+15.4% against hurdles of 5.5% to 10.1%. The static and corrected spread
series correlate only 0.459, so they are genuinely different series rather
than a rescaling: the corrected universe drops ~40% of names in the early
years, and its rolling volatility is lower through that stretch, which
lowers the hurdle enough for the mid-decade spread to clear it.

It would be easy to present that as the project's one positive finding. It
is not, for two reasons stated together:

1. In the same corrected run, **27 of 144 windows breach the NEGATIVE
   hurdle** — more significantly-bad stretches (19%) than
   significantly-good ones (14%).
2. The full-sample verdict on exactly this series is unambiguous: composite
   annualized −1.3%, Newey-West t −0.42, **DSR 0.067**. It fails decisively.

That combination is precisely the pathology the Deflated Sharpe Ratio
exists to catch. A null series with time-varying volatility will produce
stretches that clear a 95% bar; selecting those stretches after the fact is
itself a testing decision, and one the DSR's N_trials = 4 does not account
for. The rolling chart is a diagnostic for *shape*, not a licence to quote
its best windows. Read on the whole sample — which is the only reading that
is not conditioned on the outcome — the corrected US composite is the
second-worst of the eight strategy-market pairs in this memo.

Korea static and corrected produce identical rolling series, for the reason
established in the survivorship section: the listing gate removed only
company-months that had no computable score.

The Korea-versus-US contrast survives all of this. Korea's decay is a
first-half/second-half collapse (−0.1%/yr to −4.1%/yr) with every clearing
window in the first 16 months of the sample. The US never clears at all in
its headline configuration. That distinction only becomes visible with a
DSR-derived band; a plain SE band flags 11% of Korean and 7% of US windows
and obscures it.

### India: the same chart, produced deliberately against the odds, and barely a chart at all

India is registered `backtestable=False` precisely because its source
supports too few independent cross-sections for inference — so this chart
was not built by default the way the US and Korean ones were. It exists
because it was explicitly requested with the 24-month window kept for
consistency, over the alternative of a shorter window or no chart at all,
and the numbers below are the direct consequence of that choice.

India has **27 monthly cross-sections total**. A 24-month rolling window
therefore produces exactly **3 windows** (April, May, June 2026), and any
two of them share 23 of their 24 months — 96% overlap. This is not
"limited data" in the way Korea's 82 windows or the US's 144 are limited;
it is close to the smallest number of windows a rolling chart can show at
all (2 would be the minimum to draw a line).

| Window ending | Ann. spread | DSR-95% band | Plain SE band |
|---|---|---|---|
| 2026-04 | +0.7% | ±17.9% | ±12.7% |
| 2026-05 | +3.8% | ±18.6% | ±12.6% |
| 2026-06 | +2.3% | ±17.9% | ±12.4% |

All three points sit far inside both bands — nowhere close to clearing
either. That is at least consistent with the descriptive full-sample
number reported earlier in this memo (+2.1%/yr, naive t +0.34, marked as
not a test): three overlapping snapshots of the same underlying series
agreeing with its own average is expected, not informative. It would be a
mistake to read "3 points near zero" as either confirming or decaying
anything — there is no earlier period in the data for the effect to have
decayed FROM. The chart is shown (dashboard, `--universe india`, "Rolling
spread" tab) with an on-chart warning stating the window count and pointing
back here, rather than either being withheld or presented to match the
US/Korea charts' visual weight.

## Survivorship correction, run for both backtestable universes

Both markets were re-run with each rebalance restricted to names actually
listed then (`--survivorship`, writing to separate `*_pit` outputs so the
two runs can be compared rather than one overwriting the other).

**S&P 500.** Wikipedia's constituent-changes table, unwound backwards,
shrinks the January-2012 cross-section from 503 names to 294. Annualised
D10−D1 by strategy, static vs corrected: F-Score −1.7% → −1.3%, Z-Score
−4.1% → −5.4%, O-Score −6.0% → −4.2%, composite −0.7% → −1.3%. The
correction moves individual scores in *both* directions — it is not a
uniform haircut — and changes no conclusion: nothing survives Deflated
Sharpe either way.

**KOSPI.** First-annual-filing dates were pulled per company from DART's
own index; 13 of the 120 names were not yet KOSPI filers in 2016 (Samsung
Biologics, Woori Financial, the HD Hyundai spin-offs, Netmarble). The
corrected run is **bit-for-bit identical to the static one** — same 105
months, same spread series, same statistics to three decimals.

That identity is the most useful thing in this section. Of the 362
company-months the listing gate removed, **zero** had a computable score:
a company that has not filed an annual report has no facts in the PIT
snapshot, so it scores NaN and never reaches bucket formation. The
filing-date gate had already made look-ahead structurally impossible, and
the listing gate is belt-and-braces confirming it. This is independent
evidence that the point-in-time database does what it claims, obtained by
trying to break it rather than by asserting it.

**What neither correction fixes.** Both handle look-ahead. Neither fully
handles delisting survivorship, and the Korean limit is worth recording
because the obvious approach fails silently:

- DART's `corp_cls` is a **current** attribute, not a historical one.
  Querying the filing index with `corp_cls='Y'` returns 684 KOSPI filers
  for 2016 and reports *zero* of them missing by 2025 — an impossible
  delisting rate over a decade, and purely an artefact of the filter
  excluding anything since reclassified. Dropping the filter shows 2,097
  companies filed annual reports in that window, of which 406 now carry
  class 'E'. A membership table built the naive way would have been
  survivorship-biased *and* looked authoritative.
- Those names cannot be priced regardless: Yahoo returned usable `.KS`
  history for only **4 of a 40-name sample** of them, because it drops
  delisted KRX tickers.

So the residual bias is quantified rather than papered over, and the
reported levels remain optimistic in both markets.

## India: a fourth market, and a weaker guarantee

`pit_fundamentals/india_client.py` covers the top 100 Indian companies by
market cap. It is deliberately built differently from the other three, and
the reason is a finding in itself about what "free fundamentals data"
means outside the US.

Every other regulator here publishes machine-readable statements with a
filing date attached to each number. India does not. What exists, verified
by direct request:

- **BSE's public API** serves audited-results announcements carrying a real
  dissemination timestamp (Reliance's FY2024: 2024-04-22T19:00:20) — an
  authoritative filing date. But the values are in an attached PDF; the
  XBRL URL patterns all 404 and the structured-results endpoints return
  BSE's generic HTML error page.
- **Yahoo Finance** serves the values for `.NS` tickers, and unusually
  completely — every canonical tag, including a direct `EBIT` and share
  count. But no filing date whatsoever.

Neither source can support point-in-time gating alone; joined, they can.
Values come from Yahoo keyed to fiscal period end, gated by the BSE
dissemination date of the announcement that first reported that period,
refused entirely if no announcement falls in a plausible window.

**Verification**: 387/387 company-years satisfy Assets = Liabilities +
Equity to within 0.1% (after correcting the equity mapping to the
including-NCI row — the parent-only row leaves a hole exactly the size of
minority interest, ₹181,836 crore on Reliance FY2026). Filing lags run
9–134 days, median 40, consistent with SEBI's 60-day deadline. Scores
through the unmodified pipeline put **Vodafone Idea at a *negative* Altman
Z of −1.64 and the highest Ohlson O in the universe** — two independent
distress models agreeing, with no tuning, on India's most famously
distressed large-cap. The leveraged utilities and infra names (IRFC,
POWERGRID, NTPC, Tata Power, Adani Green) cluster immediately above it.

**The screen itself.** 2,700 company-months across 27 dates, 77 of 100
names scored in the latest cross-section, composite = equal-weight average
of the three sector-neutral z-scores (a LASSO fit on ~3 independent
fundamental cross-sections would be fitting noise). The ranking separates
the recognisable Indian quality cohort — HDFC AMC, Pidilite (F = 9),
Cummins India, Divi's Laboratories, DMart — from the capital-intensive and
heavily-geared one — Grasim (Z = 0.75), Hindalco, Adani Enterprises, Tata
Motors PV. Worth noting the mechanism: this is the *sector-neutral*
composite, so Nestlé India sits in the bottom quintile on a raw Altman Z of
23.8 because it trails its Consumer Defensive peers, not because it is
distressed. That is the sector-neutralisation working as designed, and it
is a reason to read the composite as a within-sector ranking rather than an
absolute safety score.

**The honest weakness.** Yahoo serves one *current* value per fiscal
period. A figure revised later appears as though it always read that way,
so `is_restatement` is always False and the load-bearing restatement test
that anchors the EDGAR, CVM and DART paths has no Indian equivalent — the
source physically cannot express one. Look-ahead is prevented;
restatement-blindness is not. Yahoo also supplies only ~5 annual periods,
leaving three broad annual cross-sections after the year-on-year deltas.
India is therefore registered with `backtestable=False`: `run_screen()`
writes the scores panel, a bucket-return series, and — since enough months
exist to fill one 24-month window — a rolling-spread chart, but no LASSO
coefficients and no Newey-West/Deflated-Sharpe validation table. The
bucket returns and rolling chart are computed and shown deliberately (see
the rolling-decay section above for the 3-window result), but every place
they appear is labeled descriptive rather than inferential. The
quantitative justification for withholding the validation table — a 0.998
median month-to-month rank correlation and an effective sample nearer 3
than 26 — is in the cross-market summary at the top of this memo, alongside
India's descriptive spread.

## Scoped but not built: China / SSE-SZSE

A fifth market was researched against the same standard used to decide
whether to build Brazil, Korea, and India — free, structured, and capable
of a genuine per-fact *filing* date, not just fiscal period end — and,
unlike those three, China did not clear that bar, so no adapter was built.

Neither CSRC, SSE, nor SZSE publish a bulk structured statement API. The
CSRC-mandated disclosure portal, cninfo.com.cn, is the closest analog to
EDGAR/CVM/DART but is PDF-based: real announcement timestamps, no
structured line items — structurally identical to India's BSE half.
**Tushare Pro**'s statement endpoints genuinely return a real filing date
(`ann_date`/`f_ann_date`) alongside full structured data, the closest
DART-equivalent found, but reaching them needs 2,000 points — in practice
a paid donation or heavy community-contribution activity, not free
registration, failing the same bar this project already applies to FMP's
optional key (degrade gracefully, never require payment). **AKShare**
wraps Eastmoney for free structured statements (keyed by period end, not a
filing date) and separately wraps cninfo for free real announcement
timestamps (PDF only) — a join in principle, India-style, but unverified
against real filings the way India's BSE+Yahoo join was (387/387
accounting-identity checks) before it was trusted enough to build.
**Baostock** is free, no key, and its `query_*` functions return a
genuinely separate `pubDate` (disclosure) vs. `statDate` (period end) — the
most defensibly free-and-dated option found — but it returns precomputed
*ratios*, not the raw `Assets`/`Liabilities`/`NetIncomeLoss`-style line
items `screener/scores.py`'s Piotroski/Altman/Ohlson functions are built
on; feeding it would mean rewriting the score functions per market, which
would break this project's central claim that all three scores run
**unmodified** across every market.

The decision, stated the same way India's PIT weakness was rather than
silently omitted: build a real adapter later only around an AKShare
Eastmoney+cninfo join, live-verified against real filings to the same
standard as the other three adapters — not before, and not with a
period-end date relabeled as a filing date, which would be exactly the
kind of PIT-fake the rest of this project's discipline exists to prevent.

## Bottom line

As a *screener* the artifact works and the infrastructure (the PIT database
especially) is reusable. As a *strategy*, the composite's edge does not
exist in this sample: DSR = 0.09, far below the 0.95 bar, and the honest
conclusion is that classical statement-score investing in large-cap US
equities has not paid since at least 2012.

The Korean extension does not overturn that, and it is worth being precise
about what it adds. Across **two independent markets, two regulators, two
accounting taxonomies, and 272 combined monthly observations, not one of
the eight strategy-market pairs survives a Deflated Sharpe correction.**
The one bright spot — Korea's Piotroski F-Score at +5.9%/yr with a
near-monotone quintile gradient — has a t-stat of 1.02 and a bottom bucket
that returned nearly as much as the top. Two markets failing the same way
is meaningfully stronger evidence than one, and the honest summary is that
these scores are a defensible *screen* and a genuinely reusable piece of
infrastructure, but not, on this evidence, a strategy.

The Russell 3000 extension adds a third independent full backtest without
adding a new regulator or taxonomy — and it is worth being precise about
what it does and does not show, stated in full in its own section above.
Because the committed run caps the universe to the top 300 names by index
weight, 286 of those 300 are already S&P 500 constituents; it is a
consistency check on the pipeline (an independently constructed,
95%-overlapping universe reproduces the same failure shape — all four
strategies fail, O-Score worst, the Z-Score coefficient effectively zero
at every refit), not a genuine test of whether the null result is specific
to large-cap names. That test would need the smaller Russell 3000
constituents the weight cap excludes, and remains open.

Correcting for survivorship does not rescue it. Re-running the S&P 500 and
Korea with each rebalance restricted to names actually listed at the time
leaves the US conclusion unchanged (individual scores move in both
directions, none survives) and leaves the Korean result numerically
identical, because the filing-date gate had already made look-ahead
impossible. The Russell 3000 run has no equivalent correction available —
no free historical Russell reconstitution feed exists, unlike Wikipedia's
imperfect-but-real S&P 500 changes table — so that limitation is left
explicit rather than worked around. Adding India extends the screen but
deliberately not the evidence base: its composite ranking has a median
month-to-month rank correlation of 0.998 and updates on only three annual
filings, so its 26 monthly observations carry an effective sample nearer
3. Its descriptive spread (+2.1%/yr, naive t +0.34) is reported in the
cross-market table for completeness and marked as not a test. A fifth
market, China, was researched and deliberately not built — no free source
combines structured statements with a genuine filing date without a
paywall or an unverified join, and the project's PIT discipline treats
that as disqualifying rather than a gap to paper over.

Across everything here — **twelve strategy-market pairs (three full
backtestable markets × four strategies), two survivorship-corrected
re-runs, six market-configurations, three regulators and three accounting
taxonomies — there are zero survivors.** That consistency is the result.
It is also why the reusable part of this project is the point-in-time
infrastructure rather than the signal.
