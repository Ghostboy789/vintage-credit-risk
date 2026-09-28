# Loss and provisioning engine

The code in `models/loss/` turns the dbt marts into three published artefacts
(`artefacts/lgd_ead.json`, `ecl.json`, `capital.json`) and one model output
(`models_out/ecl_results.parquet`, the source of the `fct_ecl` mart). It implements
`VALIDATION_PLAN.md` sections 1 (D7, D8), 4 (intervals), 6 (L1 to L3), 7 (E1 to E6), 8 (G1, G2)
and 9 (Basel), which were frozen before any result (tag `plan-freeze`). This page says how each
rule was implemented, which details the plan left open, and the results of the run on the
Freddie Mac data (full tables, each with its interval and `n`, are in the artefacts).

```
python -m models.loss.run                         # real marts under VINTAGE_DATA_ROOT
python -m models.loss.run --fixtures --out <dir>  # the synthetic fixtures, never to artefacts/
```

Options: `--draws` (default 1000, the plan's number). The macro scenarios run when the
`VINTAGE_HPI_CSV` environment variable points at the FHFA file below; otherwise the ECL has no
forward-looking information and `ecl.json` says `scenarios.used = false` (E5).

| File | What |
|---|---|
| `lgd.py` | Realised LGD and EAD, G1 segments, downturn LGD, resolution mix, the two D8 sensitivities, R5 and R6, the G2 model |
| `lifetime.py` | L1 competing-risk hazard, L2 behavioural 12-month PD, L3 monthly paths |
| `ecl.py` | Staging (E1), exposure and discounting, ECL and its parameter draws (E2), backtest (E3), migration and stage 2 drivers |
| `capital.py` | Basel IRB K, RWA and capital (section 9) |
| `macro.py` | House-price covariate and the three scenarios (E6) |
| `stats.py` | Intervals, the multinomial logit fitter, metric objects |
| `run.py` | Loads the marts, runs everything, checks the artefacts against `CONTRACTS.md`, writes them |

## LGD and EAD (D7, D8, G1, G2)

- **Sample.** `fct_loss_events` rows with `in_lgd_sample` (default at least 36 months before the
  cut-off): `credit_event_loss` and `paid_off` (LGD 0 by definition). `defect_settlement`,
  `other_exit`, `cured_active` and `open` defaults are not in it; their share of each default
  year's primary defaults is `resolution_mix`.
- **G1 segments.** Mean `lgd_economic`, `lgd_gross_of_mi` and `lgd_undiscounted` overall and by
  LTV band, state, disposition type and default year. A segment with fewer than 50 resolved
  defaults is folded into `other`. Intervals: 1,000 bootstrap resamples of the resolved defaults
  (loans, unstratified, seed 20260923); every segment's interval comes from the same resamples.
- **LGD in ECL.** The G1 `lgd_economic` mean of the loan's origination LTV band (`other` for a
  folded band; the overall mean if nothing was folded and the band has no defaults).
- **Sensitivities (D8).** (a) Zero-loss exclusions, always run: `cured_active` defaults and
  `other_exit` defaults whose terminal code is 16, dated in the same 36-month window, join the
  sample with LGD 0. (b) Open workouts, run only if `open` defaults are more than 10% of all
  primary defaults dated at least 36 months before the cut-off: each takes the 90th-percentile
  `lgd_economic` of its LTV-band segment. Each reports the overall mean with its own bootstrap
  and the difference from the primary estimate. Neither replaces it. Defect settlements and
  code 96 stay out of both.
- **EAD.** `mean_ead` is the mean EAD (D7) of all primary defaults, bootstrap interval. No credit
  conversion factor: the loans have no undrawn limit.
- **Reconciliation.** R5 compares `computed_loss` with Freddie Mac's `actual_loss` where it is
  populated; R6 compares `total_expenses` with its four components. Each passes if at least
  99.5% of events agree within $1. Only counts and the largest difference are published;
  exception lists would be loan-level and stay outside the repository.
- **G2 (stretch).** Two stages on the six pre-registered factors (origination LTV band, MI band
  none / 1-25% / over 25%, loan-size band up to $100k / $200k / $300k / $450k / above, occupancy,
  property type, state): a logit for a positive loss, then a fractional logit for severity given
  a loss (severity clipped to [0, 1] for that fit only; published LGDs are never capped). "State
  group" is not defined in the plan; here, as for every G2 factor, a level with fewer than 50
  training defaults is pooled into `other`, and a dummy that is a linear combination of others
  (for example an MI band implied by an LTV band) is dropped. Fitted on defaults to 2010-12,
  compared on 2011-01 to 2023-03 against the LTV-band mean from the same training defaults. The
  paired bootstrap of `MAE_model - MAE_segment_mean` must lie entirely below 0 for the model to
  replace G1 in ECL; if it does, it is refitted on the whole LGD sample and applied loan by loan,
  and the LGD part of the ECL interval is then not drawn (the draws cover G1 means only).

## Lifetime PD (L1 to L3)

- **L1.** Multinomial logit {stay, default, prepay} on loan-months with `months_on_book` of 1 or
  more, reporting months to 2016-12, before or at the loan's first primary default. Default is
  `is_first_default_month`; prepayment is exit type `prepaid`. Terminal records with exit type
  `other_exit` (codes 16, 96) or `matured` are censored: left out rather than counted as a
  month survived. Covariates: grade, age band, rate-incentive band (a null incentive takes the
  middle band). The cell counts are aggregated in DuckDB and fitted by Newton-Raphson with the
  counts as frequency weights, which gives the loan-level maximum-likelihood estimate and its
  covariance.
- **L2.** Logit of `default_next_12m` on `fct_stage_inputs` rows at quarter-ends 1999-03 to
  2015-12 with a non-null outcome (so cured loans are outside the fit). Covariates: grade, age
  band (`pre` pooled with `1_12`), behaviour state, `modified`. Grouped cells, same fitter.
- **Merges.** The plan's rule (a grade with no events merges into its surviving neighbour nearer
  D, in the order A, G, B, F, C, E, D; D itself into the larger neighbour, C on a tie) is applied
  per model. A grade with no loans at all takes its nearest grade towards D. The plan names only
  grades; the same "no events, pool with the neighbour" rule is applied to the ordered bands
  (age, incentive, behaviour state, modified), pooling a failing band into the band before it.
  Grade merges are listed in the E4c evidence in `ecl.json`; band merges are not published. On
  the real data no grade or band needed a merge in L1 or L2.
- **L3.** Months 1-12: default `PD12 / 12` a month and prepayment from L1 applied to survivors;
  the monthly default is capped at the survivors left after prepayment, so survival never goes
  negative. From month 13, default and prepayment both from L1 applied to survivors. The
  incentive band is held at its reporting-date value. Lifetime PD is the sum of marginal
  defaults. `pd_term_structure` is this path for a new loan (months on book 0, middle incentive
  band, clean, not modified) over 30 years, by grade, at the latest reporting date; its `n` is
  the loans of that grade in the L1 fitting sample.

## Staging and ECL (E1, E2)

- **Stage** = the maximum of the dbt `stage_floor` and the PD rule: `PD12_now / PD12_ref >= 2.0`
  and `PD12_now - PD12_ref >= 0.0020`, with `PD12_ref` the L2 PD at the loan's grade and current
  age band, behaviour `clean`, not modified. No probation from stage 2 to 1.
- **Exposure.** At a reporting date the interest-bearing balance
  (`current_upb - non_interest_bearing_upb`) amortises at the current rate (the note rate if
  missing) over `remaining_term`; the deferred balance is held until maturity. A default in
  projection month m has exposure equal to the balance at the start of month m (after m - 1
  scheduled payments) and is discounted by `(1 + note_rate / 1200) ^ -m`.
- **ECL.** Stage 1: months 1 to min(12, remaining term). Stage 2: to the end of the remaining
  term. Stage 3: LGD x current UPB. The economic LGD is already discounted from default to
  disposition, so the two discountings do not overlap.
- **Intervals (`parameter_draws_1000`).** 1,000 draws of the L1 and L2 coefficients from their
  normal sampling distributions. LGD is drawn only when G2 fails and the LTV-band means are
  used (from their bootstrap); in the published run G2 passed, so each loan's LGD comes from the
  two-stage model and is held fixed across draws, and the intervals carry no LGD uncertainty. The
  portfolio and each loan's stage are held at their point-estimate values; 2.5% and 97.5%
  percentiles. They do not cover the scenarios or model choice, and L1's covariance treats
  loan-months as independent, so the intervals are too narrow. Where a percentile interval
  misses the point estimate (possible with skewed draws) it is widened to include it, as the
  contract requires `ci_low <= value <= ci_high`.
- **In-sample.** Reporting dates up to 2016-12 fall inside the L1 or L2 fitting window and are
  labelled `in_sample`. The G1 LGDs use defaults to 2023-03 at every date.
- **Cured loans** (`defaulted_before` and not in default) get the L2 PD for their current state,
  an extrapolation; `cured_population` publishes their count, exposure and ECL at every date.
- **Stage migration** is between consecutive quarter-ends; a loan missing at the later date is
  `exited`. **Stage 2 drivers** give the dbt reason, or `pd_deterioration` when only the PD rule
  applies.

## Backtest (E3, L1a)

At each year-end 2016-12 to 2024-12, stage 1 and 2 loans with a non-null `default_next_12m`, by
grade: predicted = mean `PD12` (probability-weighted when the scenarios run), realised with its
Jeffreys interval. Green inside the 2.5% and 97.5% quantiles of `Binomial(n, PD) / n`; amber
inside the same quantiles of the Vasicek distribution with rho 0.15; red otherwise. A date passes
with no red grade; the rule passes if all seven non-COVID dates pass (2019-12 and 2020-12 shown,
not counted). A missing date gives INSUFFICIENT. A failure states whether the red grades all sit
on one side of the prediction ("cycle") or on both ("ranking"). The rule is computed on every
grade before the small-cell suppression removes grades with fewer than 10 loans from the
published table. L1a compares the mean predicted 12-month prepayment (the L3 path) with the
realised `prepaid_next_12m`, Wilson interval, described only.

## Macro scenarios (E6, stretch)

- **Source.** FHFA House Price Index master file,
  `https://www.fhfa.gov/hpi/download/monthly/hpi_master.csv`, series `hpi_type = traditional`,
  `hpi_flavor = purchase-only`, `frequency = monthly`, `place_id = USA`, column `index_sa`
  (seasonally adjusted, January 1991 = 100). Months after the data cut-off (2026-03) are ignored.
  The file is public FHFA data and is not committed; set `VINTAGE_HPI_CSV` to its location.
- **Covariate.** `x(month)` = the 12-month % change in the index ending three months earlier.
  L1 uses `x` of the loan-month. L2 predicts defaults over the next 12 months, so it uses the
  mean of `x` over those 12 months (the realised values when fitting, the scenario's values when
  projecting). The plan does not say which month's value L2 takes; this choice is what lets the
  scenarios move the first-year PD and the staging. `PD12_ref` uses `x` at the loan's first
  payment month.
- **Scenarios** for the 12-month change after the reporting date: base = the median over the
  index's history to the cut-off, held flat; adverse = the realised changes January 2007 to
  December 2011, replayed, then base; upside = the 90th percentile for 24 months, then base. In
  the first three projection months the lagged covariate is already observed and uses the
  actual index. The base median uses the whole history, including years after a historical
  reporting date (stated hindsight).
- **Weights** 60 / 25 / 15. Staging uses the probability-weighted `PD12`; each scenario's ECL
  uses those stages; the published (`final`) ECL is the weighted average of the three.
  `scenario_totals` and `ecl_results` carry each scenario, so the 100%-adverse ECL is published
  as the sensitivity.

## Basel IRB capital (section 9, stretch, illustrative)

`K = LGD * N(G(PD) / sqrt(1 - R) + sqrt(R / (1 - R)) * G(0.999)) - PD * LGD`, R = 0.15,
`RWA = 12.5 * K * EAD`, capital `K * EAD`. PD: the mean of each grade's annual 12-month default
rate at the 17 year-ends 1999-12 to 2015-12, floored at 0.05%, with a t interval over the years.
LGD: the downturn `lgd_gross_of_mi` (defaults dated 2008-01 to 2011-12) of the loan's LTV band,
floored at 5%, folded like G1. Applied loan by loan to non-defaulted exposures at the latest
reporting date and summed by grade. Not a regulatory number: see `limits` in `capital.json`.

## Results on the Freddie Mac data

Run of 2026-09-28: 109 quarter-ends from 1999-03 to 2026-03 (24.7 million loan-quarters), final
scorecard grades, 1,000 parameter draws, the three house-price scenarios. Intervals on ECL are
the parameter-draw percentiles described above (too narrow; LGD not drawn, because G2 passed).
Coverage = ECL / exposure; its interval divides the ECL interval by the fixed exposure.

**Headline, 2026-03.** Exposure $80.0bn on 342,587 loans. Probability-weighted ECL $272.4m
[269.6, 275.0]; coverage 34.0 bp [33.7, 34.4]. By stage: stage 1 $41.0m (292,874 loans), stage 2
$124.3m (46,668), stage 3 $107.1m (3,045). Scenarios: base $261.5m [259.0, 263.9], 100% adverse
$320.4m [316.9, 323.8], upside $235.7m [233.2, 238.1].

**LGD and EAD.** Overall realised economic LGD 0.249 [0.246, 0.252], gross of MI 0.280
[0.277, 0.284], undiscounted 0.265 [0.261, 0.268], n = 35,688 resolved primary defaults (bootstrap
1,000). By origination LTV band (economic): up to 60 0.132 [0.124, 0.141], 60-80 0.289
[0.284, 0.294], 80-90 0.255 [0.247, 0.265], 90-95 0.174 [0.166, 0.182], over 95 0.236
[0.225, 0.247]. The high-LTV bands are not the worst on the economic basis, which is consistent
with mortgage insurance paying part of their loss (not tested separately here). Adding the zero-loss exclusions (D8a)
lowers the overall LGD to 0.197 [0.195, 0.200]; open workouts are 1.1% of primary defaults, so the
D8b sensitivity was not needed. Mean EAD $171,862 [170,894, 172,761], n = 54,615. R5 and R6 pass
with no event outside $1. **G2 passes** (MAE difference -0.0134 [-0.0150, -0.0116] on 16,168
held-out defaults), so the ECL uses the two-stage LGD model loan by loan.

**Over time, through 2008 and COVID** (probability-weighted ECL; stage mix as a share of loans):

| Quarter-end | ECL $m [95%] | Coverage bp | Stage 1 / 2 / 3 % | Stage 2 from the PD rule alone |
|---|---|---|---|---|
| 2006-12 | 97.4 [96.9, 97.8] | 36.2 | 94.8 / 4.6 / 0.6 | 67% |
| 2007-06 | 112.5 [112.0, 113.0] | 37.9 | 94.8 / 4.6 / 0.6 | 70% |
| 2007-12 | 156.6 [155.9, 157.1] | 48.1 | 94.3 / 4.9 / 0.7 | 66% |
| 2008-03 | 204.3 [203.1, 205.4] | 60.4 | 86.1 / 13.0 / 0.9 | 89% |
| 2008-12 | 374.3 [372.1, 376.4] | 97.4 | 77.8 / 20.7 / 1.5 | 89% |
| 2009-06 | 479.7 [478.1, 481.1] | 125.8 | 79.3 / 18.2 / 2.5 | 87% |
| 2009-12 | 578.6 [577.8, 579.4] | 147.0 | 89.9 / 6.4 / 3.7 | 55% |
| 2010-03 (peak) | 610.5 [609.7, 611.3] | 151.9 | 89.6 / 6.4 / 4.1 | 63% |
| 2011-12 | 535.0 [533.8, 536.2] | 131.0 | 90.0 / 6.3 / 3.7 | 61% |
| 2016-12 | 202.3 [201.1, 203.3] | 42.0 | 94.7 / 4.2 / 1.1 | 66% |
| 2020-03 | 175.8 [174.9, 176.6] | 30.2 | 94.8 / 4.4 / 0.7 | 69% |
| 2020-06 | 388.8 [386.3, 391.2] | 69.5 | 90.6 / 8.7 / 0.8 | 36% |
| 2020-12 | 299.8 [298.0, 301.5] | 59.4 | 90.2 / 9.0 / 0.8 | 52% |
| 2021-12 | 190.0 [188.9, 191.0] | 40.3 | 90.0 / 9.2 / 0.8 | 78% |
| 2023-03 | 210.3 [206.8, 213.6] | 36.7 | 82.4 / 17.0 / 0.6 | 93% |
| 2026-03 | 272.4 [269.6, 275.0] | 34.0 | 85.5 / 13.6 / 0.9 | 90% |

Dates to 2016-12 are in-sample for L1 or L2.

**Where the lag shows.**
- *2008.* Coverage was 36-38 bp through mid-2007 and only 48 bp at 2007-12. Stage 2 jumped in
  one quarter (4.9% to 13.0% at 2008-03), almost all of it through the PD rule, whose only moving
  input for a clean loan is the lagged house-price covariate. Coverage peaked at 2010-03
  (152 bp), after the peak in defaults, when 4.1% of loans were in stage 3. The model provisions as
  delinquencies and the lagged index arrive, a few quarters behind the start of the crisis; from
  2006 data it does not anticipate it.
- *COVID.* ECL more than doubled in one quarter (2020-03 to 2020-06) through the 30-days-past-due
  backstop and forbearance flags (the PD rule explains only 36% of stage 2 at 2020-06), while
  stage 3 hardly moved because forborne 90+ loans are stage 2 by design (D3). Realised defaults
  stayed low under the primary (D1, forbearance-exempt) default definition, so this was
  over-provisioning under that definition: at 2020-12 the model predicted 1.8x to 5.5x the
  realised 12-month default rate by grade. That comparison is partly circular, since D1 is the
  definition that exempts forbearance from counting as default in the first place; under the
  naive (D2) definition the realised rate is higher and the over-provisioning smaller.
- *2022-23.* Stage 2 rose again to 17% with almost no delinquency change: 93% of stage 2 at
  2023-03 is the PD rule alone, when house-price growth slowed. Because `PD12_ref` carries the
  house-price value at origination, loans originated in the 2020-22 boom look deteriorated when
  growth slows. The sensitivity below measures how much of stage 2 this explains.

**Stage 2 sensitivity to the house-price definition (V-05).** `PD12_now` uses the mean
house-price covariate over the next 12 months under each scenario; `PD12_ref` uses its value at
the first payment month. `models/loss/stage2_sensitivity.py` restages two dates three ways and
recomputes the probability-weighted ECL, holding the fitted models fixed (point estimates, no
parameter draws, so no intervals; `artefacts/stage2_sensitivity.json`):
(a) as published; (b) `PD12_ref` on the same forward-mean definition as `PD12_now` (the realised
mean over the 12 months after the first payment month, the definition L2 is fitted on);
(c) the house-price term dropped from both sides (fitted coefficients kept, L2 not refitted).

| Date | Variant | Stage 2 loans (share) | PD rule only | Stage 2 ECL $m | Total ECL $m |
|---|---|---|---|---|---|
| 2023-03 | (a) published | 47,641 (17.0%) | 44,179 | 127.3 | 210.3 |
| 2023-03 | (b) forward-mean reference | 41,764 (14.9%) | 38,302 | 111.1 | 195.2 |
| 2023-03 | (c) no house-price term | 12,806 (4.6%) | 9,344 | 55.6 | 147.9 |
| 2026-03 | (a) published | 46,668 (13.6%) | 41,855 | 124.3 | 272.4 |
| 2026-03 | (b) forward-mean reference | 42,440 (12.4%) | 37,627 | 113.5 | 263.4 |
| 2026-03 | (c) no house-price term | 15,039 (4.4%) | 10,226 | 70.8 | 228.2 |

Row (a) reproduces the published stage 2 counts and ECL exactly. The definition gap is a small
part of the effect: putting both sides on the same definition removes 5,877 stage 2 loans at
2023-03 (12% of stage 2) and 4,228 at 2026-03 (9%), and lowers total ECL by $15.1m and $8.9m.
Most of the PD-rule stage 2 comes from the house-price covariate itself: loans look deteriorated
because national house-price growth now is below what it was around their origination, with no
change in the borrower's own behaviour. Dropping the term from both sides leaves stage 2 at 4.6%
and 4.4% of loans and lowers total ECL by $62.4m and $44.2m. What this does not establish: which
rule is right (whether a national house-price move alone should count as a significant increase
in credit risk is a policy choice, not tested here); that stage 2 under (b) or (c) predicts
defaults better; anything about dates other than these two. Variant (b) uses house prices
realised after origination, carried forward past the data cut-off for loans that first paid in
the last year.

**Backtest (E3): PASS, with a clear bias.** No Red grade at any date. Of the 49 counted
grade-dates, 4 are Green and 45 Amber: the model over-predicts in 48 of 49 (pooled predicted
0.766% against realised 0.529%, 2,008,959 loan-dates; predicted over realised 0.99x to 2.41x).
It passes only because the Vasicek band allows for systematic cycle error. Ranking holds (realised
rates rise from A to G at every date except 2023-12, where F is above G). The PD model was not
refitted and no overlay was added.

**Prepayment (L1a, described).** The rate incentive follows the refinancing cycle but misses its
size: mean predicted against realised 12-month prepayment 0.229 vs 0.270 at 2020-12, 0.208 vs 0.126
at 2021-12 (no burnout in the model), 0.056 vs 0.073 at 2023-12.

**Basel IRB (illustrative).** At 2026-03, non-defaulted exposure $79.27bn: RWA $31.45bn (average
risk weight 39.7%), capital $2.516bn (3.17% of exposure), against an ECL of $165.3m
[162.6, 167.9] on the same loans (stages 1 and 2), so unexpected loss capital is about 15 times
expected loss. Long-run PD (t interval over 17 year-ends) runs from 0.196% [0.116, 0.277] for
grade A to 6.72% [4.95, 8.48] for G; downturn LGD gross of MI from 0.195 [0.181, 0.210] (LTV up to
60) to 0.464 [0.442, 0.487] (over 95).

**Runtime.** 3 h 49 min on a 16 GB laptop (peak working set 9.2 GB), 1,000 draws and three
scenarios; 26 min with 50 draws.

## Ind AS 109 and RBI mapping

Ind AS 109 is converged with IFRS 9 on impairment, so each step above has a direct counterpart.
The numbers are US mortgage numbers and do not carry over; the method does.

| Step here | Ind AS 109 / IFRS 9 | Indian practice |
|---|---|---|
| Stage 3 = primary default (D1: 90+ days past due, or a credit event) | Credit-impaired; 90 days past due is the rebuttable default presumption (B5.5.37) | RBI NPA: overdue more than 90 days under the IRAC norms (D9 maps the buckets) |
| Stage 2 backstop at 30+ days past due | 30 days past due is the rebuttable SICR presumption (5.5.11) | SMA-1 (31-60 days) and SMA-2 (61-90 days) sit in stage 2; SMA-0 cannot be separated in this data (D9) |
| PD-deterioration rule against the PD expected at origination | SICR compares lifetime default risk now with that at initial recognition (5.5.9) | Indian lenders under Ind AS usually combine dpd backstops with a PD or rating-notch test; the 2.0x and +0.20 point thresholds are this project's, not a regulatory number |
| Forbearance, repayment plans, cure probation in stage 2 | Qualitative SICR indicators; a modified asset is assessed against its original recognition (5.5.12) | RBI restructuring rules keep a restructured account downgraded through a specified period; here probation is 6 months after a cure |
| 12-month ECL (stage 1), lifetime ECL (stages 2 and 3) | 5.5.3, 5.5.5 | Same under Ind AS 109 |
| Discounting at the original note rate | Effective interest rate (B5.5.44) | Same |
| Three house-price scenarios weighted 60/25/15 | Unbiased, probability-weighted, with forward-looking information (5.5.17) | Same; Indian lenders typically use GDP and sector indicators rather than house prices |
| Illustrative IRB capital | Basel II/III retail mortgage formula | RBI has not implemented IRB for Indian banks; they use the standardised approach |

Indian scheduled commercial banks provision under RBI's IRAC norms rather than Ind AS 109 ECL;
RBI proposed an ECL framework for banks in a discussion paper in January 2023. NBFCs that follow
Ind AS already apply Ind AS 109 ECL. Nothing here is a view on how any Indian lender should
provision.

## What this does not establish

- No result here is an audited or regulatory provision or capital figure.
- The ECL intervals cover parameter uncertainty only, and are too narrow (above).
- Re-default risk after a cure is not modelled separately; cured loans use an extrapolated L2 PD.
- The prepayment model has no house-price or burnout effect.
- The backtest pass does not show the PD is calibrated: it over-predicts almost everywhere and
  passes only against the wide Vasicek band. The ECL is therefore likely conservative outside a
  crisis, and it rose late into 2008.
- The house-price scenarios are one national index with fixed weights and a replayed 2007-11
  path; they are not a forecast, and the base scenario uses the index's full history (hindsight at
  historical dates).
- Loan-level LGD comes from origination attributes only; current LTV is not used.
- Everything is US conforming mortgage data; the methods carry over to Ind AS 109, the numbers
  do not.

## Tests

`tests/test_loss.py`: E4a hand-worked loans (a one-month loan by hand, a 36-month loan against an
independent month-by-month loop, stage 3); E4b staging edge cases (29 against 30 days past due,
cure probation and its end, a forborne 90+ loan in stage 2, a loan in default, the PD rule's two
thresholds, a credit-event exit leaving the book); E4c paths summing to 1 (1e-12); the Vasicek
quantile against the plan's distribution function; backtest colours and the pass rule; a Basel
K computed by hand; the grade-merge order; the logit fitter; the LGD sensitivities; the
scenario paths; the engine's grouped ECL against a loan-by-loan sum on the fixtures; and an end
to end run on the fixtures checked against `CONTRACTS.md`.
