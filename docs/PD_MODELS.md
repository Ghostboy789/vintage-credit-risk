# PD models

The application scorecard (champion), its LightGBM challenger, and how they are validated.
Rules are defined in `VALIDATION_PLAN.md` (sections 2 to 5) and referenced here by ID; this file
says how the code in `models/pd/` implements them and where it had to interpret them.

**Status: run on the Freddie Mac data on 2026-09-25** (1,349,995 loans in
`fct_scorecard_base`). The out-of-time and COVID samples were scored once. PASS, FAIL or AMBER is
written next to each rule in `VALIDATION_PLAN.md`; the results are summarised below. Source:
Freddie Mac Single-Family Loan-Level Dataset (sample files), used for non-commercial research.

## Running it

```
python -m models.pd.run --dry-run           # development data only: no out-of-time scoring
python -m models.pd.run                     # real marts under VINTAGE_DATA_ROOT
python -m models.pd.run --fixtures OUT_DIR  # synthetic fixtures; every output under OUT_DIR
python -m models.pd.run --reuse-scores      # rebuild the artefacts from the saved scoring
```

Inputs: `fct_scorecard_base`, `dim_loan` (first payment date and terminal Zero Balance Code, for
the exclusion table) and `fct_loan_month` (first modification month, for D1a).

Outputs:

| File | What |
|---|---|
| `models_out/loan_scores.parquet` | Score, PD, grade and three reason codes for every loan (contract `loan_scores`) |
| `models_out/challenger_scores.parquet` | Challenger PD for every loan |
| `models_out/scorecard.json` | The frozen scorecard: bins, WoE, points, coefficients, grades, every candidate's binning |
| `models_out/binning_report.csv` | One row per bin of every candidate: counts, default rate, raw and used WoE, IV, why it left the model |
| `models_out/oot_scoring_log.jsonl` | One line per out-of-time scoring (P3) |
| `artefacts/pd_models.json`, `artefacts/monitoring.json` | Published aggregates (contracts in `CONTRACTS.md`) |

The run refuses to write synthetic inputs to `artefacts/` or to the real `models_out/`, and
refuses to write artefacts that fail `tests/contracts.py`.

## Order of work and the out-of-time guard (P3)

1. The scorecard is fitted on `dev_train` only, and the challenger is tuned on `dev_train` and
   confirmed on `dev_test`. Both are then frozen; the scorecard's `model_id` is a hash of its
   points table, grades and scaling.
2. Development results (`dev_train`, `dev_test`) are computed.
3. `run.score_out_of_time` scores every loan, `oot` and `covid` included, with both models in one
   call. It is the only code allowed to score those samples: `scorecard.score` and
   `challenger.predict` raise unless it calls them. It refuses a second call for the same
   scorecard and appends the call (timestamp, both model ids, counts) to the log. Tests check
   that no other code passes the override and that the real log never holds two calls for one
   model. A rescoring after a bug fix is a plan deviation and has to be recorded as one.
4. Everything that uses out-of-time or 2016+ outcomes (S2 to S5, C1, the sample table, D1a)
   runs after that call. If a later step fails, `--reuse-scores` refits (the fit is
   deterministic), checks the `model_id` and challenger id against the log, and rebuilds the
   artefacts from the saved scores instead of scoring again.

## Method as implemented

**Features and binning (S-method).** The 15 candidates in the plan's order, which also breaks
every tie. One engine, `optbinning` 1.0.0 `OptimalBinning`, with exactly the pinned parameters.
`term_band`, `number_of_units` and `super_conforming` are binned as categories (strings).
A feature is dropped if the solver status is not `OPTIMAL`/`FEASIBLE`, if it returns one
non-missing bin, or if a numeric feature's non-missing WoE is not monotonic (non-strict) in its
expected direction (`original_upb`: either direction). A missing bin with fewer than 20 defaults,
including an empty one, takes the lowest (highest-risk) WoE of the feature.

**WoE sign.** WoE is computed once, in `scorecard.woe_iv`, as
`ln(share of non-defaults in bin / share of defaults in bin)` from the bin counts. The plan
describes this as the opposite sign to optbinning's; in optbinning 1.0.0 the binning table uses
the same sign (a test checks they agree on the fixture), so no sign flip is applied. The formula
in the plan is what the code follows; only that remark in the plan does not hold for this
version.

**Screening and model.** IV below 0.02 dropped; IV above 0.5 flagged in the binning report for a
leakage review, not dropped. Correlation screen on the WoE design at |r| above 0.7, pairs in
descending order, lower IV dropped (equal IV: the later candidate). statsmodels `Logit`, Newton,
`maxiter=100`; a fit that does not converge stops the run. Elimination one feature per refit, in
the plan's order of rules (positive coefficient, p above 0.01, VIF 5 or more, more than 12
features); on a tie the later candidate is dropped.

**Points and grades.** Factor `20 / ln 2`, offset `600 - factor * ln 50`, points per attribute as
in the plan, rounded half away from zero (as spreadsheet `ROUND`), so the website calculator and
the workbook can add the published integers. `pd_12m` is computed from the integer score. The
master scale merge runs on `dev_train` in the order A, G, B, F, C, E, D, recounting after every
merge; a grade merged earlier follows its host if the host merges later. Each surviving grade's
PD band is the union of its members' bands, and its integer score range is derived from that
band. A test checks the ranges against the PD formula.

**Scoring a category not seen in `dev_train`.** It is treated as a category below the 5%
cut-off, so it goes to the bin that holds the grouped rare categories; if the feature has no
such bin, it goes to the missing bin. The plan does not cover this case.

**Reason codes.** The three model features whose points fall furthest below that feature's
maximum, ties in candidate order. A feature already at its maximum is not a reason, so a reason
slot can be empty.

**Intervals.** As fixed in section 4: stratified loan bootstrap (1,000, seed 20260923,
percentile) for AUC, Gini, KS and the Gini drop; the same resamples for both models in C1;
Jeffreys for default rates in pass rules; Wilson for described rates; PSI and CSI bootstrapped
separately in each sample with the bin edges fixed (the bin counts of a loan resample are drawn
directly as multinomial counts, which is the same distribution). **When a percentile interval
does not contain its own point estimate**, which happens for statistics that resampling biases
upwards (PSI near zero, sometimes KS), the contract does not allow the interval to be published
with that value, so the interval is withheld and its bounds are written into `ci_method`
instead. Nothing is recomputed with another method.

**Pass-rule results where the plan leaves a case open.**
- S4a/S4b: PASS only if every grade passes; any FAIL fails; otherwise (some grades have fewer
  than 20 defaults and none fails) `INSUFFICIENT`.
- S3: `INSUFFICIENT` if fewer than two surviving grades have out-of-time loans.
- D1a: `PASS` at or below 10% of primary defaults; `AMBER` above it, meaning the
  modification-trigger sensitivity is required (it needs a new flag in the marts).
- S2 and S5 map green, amber and red to PASS, AMBER and FAIL.

**Fairness sensitivity.** `number_of_borrowers` is binned with the same engine (as a category).
The `dev_test` Gini "with" and "without" a feature come from a logistic refit on the final WoE
features plus or minus that feature, using the unrounded linear predictor for both sides.

**Stability.** Score PSI on the `dev_train` deciles against `oot`, and against each origination
year (all loans of that year in the scorecard population, that is, not excluded). CSI of each
model feature on its scorecard bins, missing bin included, `dev_train` against `oot`.

**Challenger (section 5).** Raw candidate features; categoricals (including `term_band`) as
LightGBM categories with `dev_train`'s levels; monotone constraints -1 for `fico`, +1 for the LTV,
CLTV, DTI, MI and rate-spread features, none for `original_upb` (no direction assumed) and the
categoricals. Each fold is trained with early stopping on its validation AUC; the fold AUC is the
best-iteration AUC and the final round count is the mean best iteration rounded half up. SHAP
values are LightGBM's TreeSHAP (`pred_contrib`), global importance as mean |SHAP| on `dev_test`.
C1.2 puts challenger PDs on the champion's merged master scale. C1.4 checks SHAP values are finite
for every `oot` and `covid` loan and that predictions move only in the constrained direction when
each constrained feature is swept over its `dev_train` deciles for 500 loans.

**Secondary out-of-time windows.** `oot_2017_2019` and `oot_2022_2024` filter the scored `oot`
sample by vintage year. The 7,941 `oot` loans of the 2021 vintage (first payment in 2022)
fall in neither window.

## Results (real data, 2026-09-25)

Scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`, out-of-time scoring logged
once at 2026-09-24T23:57:05Z. All intervals are 95%: bootstrap_1000 (stratified loan resamples,
percentile) for AUC, Gini, KS and the drops; Jeffreys for rates in pass rules; Wilson for sample
default rates. Full tables, with n on every number, are in `artefacts/pd_models.json` and
`artefacts/monitoring.json`.

**Samples.** 12-month primary defaults (D1 + D3) and default rate (Wilson):

| Sample | Loans | Defaults | Default rate |
|---|---|---|---|
| `dev_train` (1999-2015) | 539,519 | 2,101 | 0.39% [0.37%, 0.41%] |
| `dev_test` (1999-2015) | 231,384 | 871 | 0.38% [0.35%, 0.40%] |
| `oot` (2017-2024, outside the COVID window) | 258,337 | 896 | 0.35% [0.32%, 0.37%] |
| `covid` | 138,385 | 243 | 0.18% [0.15%, 0.20%] |

Excluded: 83,473 HARP loans, 1,439 indeterminate exits (all code 96), 29 out-of-time loans with
an incomplete window, and the 2025 vintage (49,995 loans). The development rate is about half the
0.76% the plan's sizing table suggested; see "What failed" below.

**The scorecard.** Seven features survived: `fico`, `ltv_pct`, `dti_pct`, `rate_spread_pct`,
`term_band`, `property_type`, `channel`, all with negative coefficients. Dropped: `cltv_pct`
(|r| 0.931 with `ltv_pct`) and `mi_pct` (|r| 0.744 with `ltv_pct`) in the correlation screen;
`original_upb`, `loan_purpose`, `occupancy_status`, `number_of_units` and `first_time_homebuyer`
with IV below 0.02; `super_conforming` in elimination (p 0.025). Every binning ended `OPTIMAL`,
so optbinning's 600-second limit was never reached. Two features have IV above 0.5 and were
reviewed for leakage: `fico` (1.33) and `rate_spread_pct` (0.72). Both are fixed at origination
(the credit score at application, and the note rate against its first-payment-month median), so
neither carries post-origination information; a high IV is expected for the bureau score and for
risk-based pricing. All seven master-scale grades met the size rule on `dev_train`; none was
merged. Grade score ranges: A 687 and above, B 667-686, C 647-666, D 627-646, E 606-626,
F 586-605, G 585 and below. The points table (`points_table` in `pd_models.json`, and
`models_out/scorecard.json`) is the whole model: the website calculator and the Excel workbook
add those integers and apply `pd_12m = 1 / (1 + exp((score - 487.1229) / 28.8539))`, labelled
"12-month PD, 1999-2015 development average".

**Discrimination (champion, primary definition).**

| Sample | Gini | AUC | KS |
|---|---|---|---|
| `dev_train` | 0.7230 [0.7068, 0.7391] | 0.8615 [0.8534, 0.8696] | 0.5704 [0.5558, 0.5899] |
| `dev_test` | 0.7109 [0.6855, 0.7354] | 0.8555 [0.8428, 0.8677] | 0.5736 [0.5482, 0.6019] |
| `oot` | **0.5336 [0.5055, 0.5625]** | 0.7668 [0.7528, 0.7813] | **0.4183 [0.3932, 0.4503]** |
| `oot`, 2017-2019 vintages | 0.5054 [0.4441, 0.5727] | 0.7527 [0.7221, 0.7864] | 0.3875 [0.3329, 0.4595] |
| `oot`, 2022-2024 vintages | 0.5327 [0.4995, 0.5679] | 0.7664 [0.7498, 0.7839] | 0.4236 [0.3950, 0.4583] |
| `covid` | 0.3191 [0.2455, 0.3883] | 0.6596 [0.6227, 0.6942] | 0.2792 [0.2243, 0.3452] |
| `oot` + `covid` (pooled) | 0.4995 [0.4717, 0.5288] | 0.7498 [0.7358, 0.7644] | 0.3939 [0.3715, 0.4248] |

**Pass rules.**

| Rule | Result | Numbers |
|---|---|---|
| D1a | PASS | 2,185 loans modified before or without a primary default against 54,615 primary defaults: 4.0% (a ratio, no interval), under the 10% trigger |
| S1 | PASS | WoE monotonic in the expected direction for all four numeric model features |
| S2 | AMBER (PASS with finding) | Relative Gini drop `dev_test` to `oot` 0.2494 [0.2010, 0.2951]; absolute 0.1773 [0.1390, 0.2127] |
| S3 | PASS | Realised `oot` rate rises through every grade, A 0.08% to G 1.84%; no inversion |
| S4a | FAIL | Grade C: mean PD 0.28% against realised 0.22% [0.17%, 0.27%]; the other six grades pass |
| S4b | FAIL | Six of seven grades fail; only E passes |
| S5 | PASS (green) | Score PSI `dev_train` to `oot` 0.0446 [0.0426, 0.0467], 10 bins |
| C1 | FAIL (not recommended) | Challenger's `oot` Gini gain -0.0124 [-0.0249, -0.0001] |

**Calibration in the large** (realised over mean predicted PD; the Jeffreys interval divided by
the mean PD): `dev_test` 0.975 [0.912, 1.041]; `oot` 1.076 [1.007, 1.148]; 2017-2019 vintages
0.680 [0.592, 0.778]; 2022-2024 vintages 1.326 [1.229, 1.428]; `covid` 0.753 [0.663, 0.853].
Under the naive definition D2 (secondary): `oot` 1.526 [1.444, 1.612] and `covid` 5.94
[5.68, 6.21], the forbearance effect that D3 was written to remove.

**Stability.** Score PSI is green overall, but the feature CSIs are not: `dti_pct` 0.654 and
`channel` 2.750 (red); `ltv_pct` 0.199, `term_band` 0.182, `rate_spread_pct` 0.117 and
`property_type` 0.115 (amber); `fico` 0.062 (green). PSI of each origination year against
`dev_train` is red for 2010-2012 (0.42 to 0.59): the post-crisis vintages score much safer than
the development average, which the pooled 1999-2015 reference hides.

**Fairness sensitivity** (`dev_test` Gini of a logistic refit): `number_of_borrowers` has IV
0.393; adding it would raise the Gini from 0.7105 [0.6849, 0.7350] to 0.7364 [0.7140, 0.7594].
It stays out of the model (a marital-status proxy under ECOA); that is the cost of the
exclusion. `first_time_homebuyer` (IV 0.013) failed the IV screen and changes nothing.

**Challenger.** LightGBM chose 15 leaves, 200 minimum child samples, L2 penalty 10 and 202
rounds; mean fold AUC 0.8720, `dev_test` AUC 0.8688 (confirm step passed). It is better in time
(`dev_test` Gini 0.7375 [0.7142, 0.7605] against 0.7109) but worse out of time (`oot` Gini
0.5212 [0.4934, 0.5509]; paired gain -0.0124 [-0.0249, -0.0001]). Criteria 2 to 4 hold
(calibration fails in 6 grades, as for the champion; score PSI 0.0429; SHAP and monotone
constraints fine). Mean |SHAP| on `dev_test` ranks `fico` first (0.717), then `dti_pct` (0.312),
`rate_spread_pct` (0.251) and `channel` (0.203). It is not recommended; the scorecard stays the
model used downstream.

**Runtime.** Development-only dry run 8 min 46 s; the full run (fit, challenger grid, the one
scoring, bootstraps, D1a over the loan-month mart, artefacts) 20 min 13 s on a 16 GB laptop.

## What failed, and why

- **S4b fails in six of seven grades, and not in the direction the plan expected.** The plan
  expected over-prediction because its sizing table put the development default rate near
  0.76%. That table counted defaults by Freddie Mac's `loan_age`, which restarts after a
  modification; on the plan's own months-on-book clock the rate is 0.39%, close to the
  out-of-time 0.35% (logged in the plan's Deviations). Overall calibration is therefore close
  (ratio 1.076 [1.007, 1.148]), and the failure is one of slope: the scorecard under-predicts
  grades A to D and over-predicts F and G. The development PDs are spread too far apart for the
  out-of-time population, the same flattening the Gini drop measures. The two windows pull in
  opposite directions (2017-2019 over-predicted, ratio 0.68; 2022-2024 under-predicted, 1.33),
  so one recalibration would not fix both. As the plan fixes, nothing is recalibrated on
  out-of-time data; provisioning uses L2.
- **S4a fails in one grade in time.** Grade C over-predicts slightly: its mean PD, 0.28%, is just
  above the upper bound of the realised 0.22% [0.17%, 0.27%]. With seven grades each tested at
  95%, one marginal miss is within what chance alone produces, but the rule has no multiplicity
  allowance and the FAIL stands.
- **S2 is Amber at the edge of Red.** The relative Gini drop, 24.9%, is 0.06 points below the
  Red line, and its interval [20.1%, 29.5%] crosses it. Under D2 it is 27.1% (secondary). It is
  a finding, not evidence of stability. Likely contributors, not tested causally: the `channel`
  and `dti_pct` shifts below, and a post-2009 population with far less spread in credit quality
  than the crisis-era development data.
- **`channel` is partly an era marker.** Freddie Mac codes third-party loans as `T` (TPO not
  specified) in every vintage to 2008 and in none after; from 2008 they are split into broker
  `B` and correspondent `C`. `T` is 31% of `dev_train` and no out-of-time loan. The scorecard
  gives `T` its riskiest channel WoE, so part of `channel`'s weight records the crisis years
  rather than the channel. This is the kind of field the plan excludes for identifying the era,
  but it was not foreseen, and the model is not changed after seeing out-of-time results. Its
  CSI (2.75) shows it. A next release should map or drop `T` before fitting.
- **`dti_pct` shifted.** Almost no out-of-time loan has a DTI above 51.5% (the agencies' 50% cap) or
  a missing DTI, and 42% have a DTI of 40.5-51.5% against 22% in development.
- **The challenger fails C1** on criterion 1: it gains in time and loses out of time.
- Engine note: for `super_conforming`, optbinning 1.0.0 returned a `true` bin with 3 defaults
  although `min_bin_n_event=20` (a two-category feature has nothing to merge with). The feature
  left the model at elimination, so the scorecard is not affected.

## What this does not establish

As `VALIDATION_PLAN.md` section 11:
- **No reject inference.** Only loans Freddie Mac bought: conforming, fixed-rate, first-lien
  loans from approved applicants. Nothing here says how the scorecard ranks declined or
  non-conforming borrowers.
- **US population, not Indian loans.** The methods map to Ind AS 109 and RBI practice; the
  numbers do not transfer.
- **No second bureau score.** VantageScore 4.0 is empty for every loan, so only Classic FICO is
  used and the two cannot be compared.
- **Associations, not causal effects.** A point weight is not the effect of changing an
  attribute.
- **Not a production PD.** The PD is a 1999-2015 development average, labelled as such wherever
  it is shown; S4b shows it is not calibrated for recent vintages. The provisioning PD is L2.
- **Not a fair-lending review.** Geography and number of borrowers are excluded; no
  disparate-impact test is possible without protected attributes.
- **One out-of-time period.** 896 out-of-time defaults from 2017-2019 and 2021-2024
  originations; the intervals are sampling intervals for that period, not a forecast for others.
