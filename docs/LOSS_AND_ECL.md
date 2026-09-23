# Loss and provisioning engine

The code in `models/loss/` turns the dbt marts into three published artefacts
(`artefacts/lgd_ead.json`, `ecl.json`, `capital.json`) and one model output
(`models_out/ecl_results.parquet`, the source of the `fct_ecl` mart). It implements
`VALIDATION_PLAN.md` sections 1 (D7, D8), 4 (intervals), 6 (L1 to L3), 7 (E1 to E6), 8 (G1, G2)
and 9 (Basel), which were frozen before any result (tag `plan-freeze`). This page says how each
rule was implemented and which details the plan left open. It contains no results: those are in
the artefacts, each with its interval and `n`.

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
  Every merge is printed by the run and listed in the E4c evidence in `ecl.json`.
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
  normal sampling distributions and of the LTV-band LGD means from their bootstrap; the
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

## What this does not establish

- No result here is an audited or regulatory provision or capital figure.
- The ECL intervals cover parameter uncertainty only, and are too narrow (above).
- Re-default risk after a cure is not modelled separately; cured loans use an extrapolated L2 PD.
- The prepayment model has no house-price or burnout effect.
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
