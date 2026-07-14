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

## International extension (South Korea / DART): honest status — untested

A third taxonomy adapter, `pit_fundamentals/dart_kr_client.py`, targets
Korea's DART OpenAPI (the natural next candidate after Brazil, per the
prior extension's own recommendation). Its status is meaningfully weaker
than the Brazil work above, and that difference is the finding worth
recording here: **CVM required zero credentials, so every mapping in
`cvm_br_client.py` was verified by downloading and grep'ing real 2022-2024
filings before being committed. DART requires a registered API key
(`crtfc_key`) for every single call — including the free company-code
list — and none was available in this session.** Rather than proceed on
memory or plausible-sounding guesses, research was restricted to DART's
official developer documentation plus two independent, citable sources:
a Korean quant-investing tutorial's worked example (confirming
`account_id="ifrs-full_CurrentAssets"` for a real Samsung Electronics
filing) and the open-source DartLab project's account-normalization
documentation, which reveals that DART tagging is genuinely less
consistent than CVM's centrally-fixed codes: the same concept appears as
`ifrs-full_Revenue` (Samsung), `dart_Revenue` (SK Hynix), or bare
`Revenue` (LG Energy Solution) depending on the filer. The code map
handles this with prefix-stripped candidate matching rather than a single
fixed lookup, but the mapping choices themselves are unverified beyond
that one confirmed data point.

Consequently: the module is architecturally complete (filing-date gating
via `rcept_dt`, restatement handling, the same canonical-tag contract) and
covered by synthetic-fixture tests proving the *logic* is correct given
DART's documented response shape — but zero real Korean company numbers
have been produced or checked. Long-term debt and shares outstanding were
deliberately left unmapped rather than guessed (they likely need either a
DART-specific extension tag or a separate API endpoint family not used
here), so Piotroski's dilution criterion and Altman Z's market-cap term
will not compute for Korean names even once a key is supplied; Ohlson
O-Score needs neither and is the one score expected to work immediately.
`screener/universe_kr.py` ships with exactly one entry (Samsung
Electronics) rather than a fabricated crosswalk, for the same reason.
**Anyone using this adapter should treat every number it produces as
provisional until checked against a real filing.**

## Bottom line

As a *screener* the artifact works and the infrastructure (the PIT database
especially) is reusable. As a *strategy*, the composite's edge does not
exist in this sample: DSR = 0.09, far below the 0.95 bar, and the honest
conclusion is that classical statement-score investing in large-cap US
equities has not paid since at least 2012.
