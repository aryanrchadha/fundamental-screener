# FINDINGS — Composite Fundamental Screener

*Research memo. Sample: S&P 500 (current constituents), monthly rebalance,
2012-01 to 2025-12 (167 monthly D10−D1 spread observations). Scores are
sector-neutral z-scores; deciles are equal-weight; spreads are decile 10
(best score) minus decile 1 (worst). All fundamentals are point-in-time,
gated by SEC filing date.*

## Validation summary

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

## Bottom line

As a *screener* the artifact works and the infrastructure (the PIT database
especially) is reusable. As a *strategy*, the composite's edge does not
exist in this sample: DSR = 0.09, far below the 0.95 bar, and the honest
conclusion is that classical statement-score investing in large-cap US
equities has not paid since at least 2012.
