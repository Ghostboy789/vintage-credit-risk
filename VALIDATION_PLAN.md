# Validation plan (pre-registered)

**Written and committed before any model was fitted or any result computed.** The git history is
the evidence: this file's first commit comes before every commit that produces a model number.

The point of writing it first is to remove the freedom to tune into a flattering answer. Every
definition, sample split, threshold and pass rule below is fixed now. If a rule turns out to be
wrong or unworkable, the deviation is recorded in the "Deviations" section at the end, with the
date and the reason, and the original rule stays visible. A rule is never loosened so that a
result passes.

Rule IDs (D1, S3, E4 and so on) are referenced by the model documentation and the validation
report. Each pass rule has a `Result:` line that stays `pending` until the analysis runs; it is
then filled in with PASS, FAIL or AMBER and the numbers, whatever they are.

**What was looked at before writing this plan.** `docs/DATA_PROFILE.md` (loan counts, how loans
end by vintage, delinquency codes, loss-field and flag coverage), plus the three sizing
aggregates in Appendix A: flag and estimated-LTV coverage by calendar year, and the count of
12-month defaults per vintage under the definition in D1 with and without the forbearance rule
in D3. Those counts were needed to size the samples and check that calibration tests would have
enough events. No model, score, PD, LGD or ECL has been computed.

**Data.** Freddie Mac Single-Family Loan-Level Dataset, sample files, origination vintages 1999
to 2025, 50,000 loans each (1,350,000 loans, 74,919,968 loan-months), performance reported to
March 2026. Conforming, fully amortising fixed-rate first-lien mortgages bought by Freddie Mac
only: every loan in the sample is a fixed-rate loan, none is interest-only.

---

## 1. Definitions

All portfolio definitions below are implemented in the dbt project (SQL), not in Python, and are
tested there. Names in `code` are the mart columns defined in `CONTRACTS.md`.

### D0. Months on book

`months_on_book` = months from the loan's first payment date to the reporting month, plus one
(so the first payment month is 1). Freddie Mac's own `loan_age` field is **not** used for this,
because the user guide says it restarts from the modification's first payment date when a loan
is modified. Pre-first-payment records have `months_on_book` of 0 or less; they are kept (they
are real reporting months) but never count towards an outcome window.

### D1. Default (primary definition)

A loan defaults in the **first** month in which any of these holds:

| Trigger | Condition | Why |
|---|---|---|
| `dpd90` | Delinquency status is numeric and at least `03` (90 or more days past due), and the month is **not** exempt under D3 | 90 days past due is the Basel and IFRS 9 rebuttable backstop, and RBI's NPA line |
| `reo` | Delinquency status is `RA` (REO acquisition) | The lender has taken the property; a credit event by any measure |
| `credit_event_zbc` | Zero Balance Code is `02` third-party sale, `03` short sale or charge-off, `09` REO disposition, or `15` whole-loan sale | These are the four codes for which Freddie Mac calculates an actual loss. A short sale can happen before 90 days past due, so this trigger is needed on its own |

Only the first default counts for PD, the scorecard and the hazard model. A loan that cures and
defaults again keeps its first default date; re-defaults are not modelled (stated as a
limitation).

What does **not** count as default:
- **Loan modification** (`modification_flag` Y or P). Under EBA-style rules a distressed
  restructuring is an unlikeliness-to-pay default, but Freddie Mac modifications are almost
  always made on loans that are already 60 to 90+ days past due, so D1 catches them anyway.
  The share of modified loans that were never 90+ past due before their first modification is
  reported (rule D1a). If it exceeds 10% of primary defaults, a sensitivity definition that adds
  "first modification" as a trigger is added to the scorecard results, and the primary
  definition stays as it is.
- **Payment deferral** (`payment_deferral_flag`). Freddie Mac says deferrals are not
  modifications.
- **Zero Balance Codes `16` (reperforming loan securitisation) and `96` (repurchase for an
  underwriting or servicing defect before a credit event).** The loan leaves the data with no
  observable credit outcome. It is treated as **censored** at that month, not as a default and
  not as a prepayment.
- **Status `XX` (not available).** Treated as missing: neither a default trigger nor current.

D1a. Share of modified loans never 90+ before first modification, over primary default count.
Result: pending

### D2. Default sensitivity ("naive") definition

The same as D1 but without the D3 exemption. Both are built in `fct_default_events` (column
`definition`), and default counts per vintage are published under both, so anyone can see what
the forbearance rule changed.

### D3. COVID and disaster forbearance

In 2020 and 2021 servicers kept reporting forborne loans as delinquent while their payments were
suspended, so days past due kept ageing on loans whose borrowers were covered by a moratorium.
Treating those months as defaults would label a policy response as a credit event. Appendix A
shows the size of the effect: the 2019 vintage has 1,211 twelve-month defaults under the naive
definition and 150 under this rule.

The rule, applied to every month in the data (not only 2020 and 2021):
- A month with delinquency 90+ does **not** trigger `dpd90` if, in that same month,
  `borrower_assistance_plan` = `F` (forbearance) or `delinquency_due_to_disaster` = `Y`.
- Trial-period (`T`) and repayment (`R`) plans do not exempt a month. They are workout plans for
  borrowers who are already delinquent, not payment relief.
- The exemption lasts only while the flag is set. If a loan is still 90+ in the first month the
  flag is gone, it defaults in that month. If a payment deferral brings it current, it does not.
- `reo` and `credit_event_zbc` always trigger default, forbearance or not.
- Delinquency itself is never rewritten. Days-past-due buckets, roll rates and delinquency
  metrics show status exactly as reported, and carry a `forbearance_flag` so forborne loans can
  be split out.

Known asymmetry: Freddie Mac populates both flags only from January 2014. Disaster delinquencies
before then (for example the 2005 hurricanes) cannot be exempted and count as defaults. This is
stated wherever vintage default rates are compared across that date.

### D4. Cure

A defaulted loan cures in the month it completes **three consecutive months** at status `00`
with no Zero Balance Code. Three months matches the EBA minimum probation period and the US
convention of three consecutive payments before re-ageing. Cure closes a default episode (for
IFRS 9 stage 3 exit and cure-rate reporting); it does not remove the loan's first default date.

In roll rates, "cure" means something narrower: a month-to-month move from any past-due bucket
to `current`. The two are always labelled separately.

### D5. Prepayment and other exits

- **Prepayment**: Zero Balance Code `01` with no earlier default. Code `01` also covers maturity;
  it is labelled `matured` if `months_on_book` is at least the original term minus one, and
  `prepaid` otherwise. Partial prepayments (curtailments) are not prepayment events.
- **Credit-event exit**: Zero Balance Codes `02`, `03`, `09`, `15`.
- **Other exit**: codes `16` and `96` (censored, D1).

### D6. Twelve-month outcome window (scorecard)

`default_12m` = 1 if the loan's first primary default (D1) happens at `months_on_book` 1 to 12.

- A loan that prepays inside the window without defaulting is a **non-default** (0). It did
  not default within 12 months. Dropping prepayers would distort the population towards loans
  that stay on book.
- A loan that leaves through code `16` or `96` inside the window without defaulting is
  **indeterminate** and is excluded (`exclusion_reason = indeterminate_exit`).
- A loan not observed through `months_on_book` 12 and still active at the data cut-off is
  **window incomplete** and excluded.

Twelve months matches the IFRS 9 stage 1 horizon and the Basel one-year PD, so the scorecard's PD
scale and the provisioning PD answer the same question. The alternative, a 24-month window,
roughly doubles the event count (Appendix A) but loses the 2024 vintage from the out-of-time
sample and no longer matches the 12-month ECL horizon.

### D7. Exposure at default (EAD)

EAD = `current_upb` in the default month; if that is zero or missing (as in a zero-balance
record), the Zero Balance Removal UPB; if both are missing, the last positive `current_upb`
before the default month. Principal only; delinquent accrued interest enters the loss, not EAD.
There is **no credit conversion factor**: these are closed-end amortising loans with no undrawn
limit. For ECL projections, exposure in future month t is the contractual amortisation schedule
of today's balance at the current note rate over the remaining term, with any non-interest-bearing
(deferred) balance assumed repaid at maturity.

### D8. Realised loss and LGD

Freddie Mac's actual loss (user guide, July 2026) is

`actual_loss = removal_upb + net_sales_proceeds + delinquent_accrued_interest + total_expenses + mi_recoveries + non_mi_recoveries`

with recoveries disclosed as negative values and expenses as positive ones, and
`total_expenses = legal_costs + maintenance_and_preservation_costs + taxes_and_insurance + miscellaneous_expenses`.
Modification costs are excluded from actual loss by Freddie Mac and are excluded here too
(reported separately, never added into LGD).

Three LGD measures are computed for every resolved default. With
`net_recovery = -(net_sales_proceeds + mi_recoveries + non_mi_recoveries + total_expenses)`
(cash in less cash out at disposition) and
`df = (1 + note_rate / 1200) ^ -(months from default to disposition)`:

| Measure | Formula | Used for |
|---|---|---|
| `lgd_economic` (primary) | `(ead - net_recovery * df) / ead` | ECL, reporting |
| `lgd_undiscounted` | `computed_loss / ead`, where `computed_loss` is the formula above | Reconciliation to Freddie Mac's `actual_loss` |
| `lgd_gross_of_mi` | as `lgd_economic`, with `mi_recoveries` left out of `net_recovery` | Basel (section 9), and to show what mortgage insurance is worth |

Decisions inside these formulas:
- **Discounting** is at the loan's original note rate, which is its effective interest rate.
  Because discounting at the contract rate already charges for the interest forgone during the
  workout, `lgd_economic` does not add delinquent accrued interest on top. All disposition cash
  flows are dated at the Zero Balance Effective Date. That is conservative for recoveries and
  slightly flattering for expenses, which really accrue during the workout (stated).
- **Mortgage insurance** recoveries are netted in the primary measure. Under IFRS 9 (B5.5.55),
  credit enhancements that are part of the contract are included in expected loss; MI on these
  loans is. `lgd_gross_of_mi` is published next to it.
- **LGD is not capped.** Values above 1 (costs exceeding the balance) and below 0 (gains) are
  kept, and their shares are reported.
- **Resolved defaults** make up the LGD sample: the loan's first default followed by a
  credit-event exit (loss computed as above) or a code `01` payoff (loss 0). Defaults ending in
  `16` or `96` are excluded (no loss observable).
- **Still-open workouts** are defaults with no terminal record by the cut-off, including cured
  loans still active. They are excluded from the LGD sample, and their share is reported by
  default year. Freddie Mac also nulls actual loss for dispositions in the three months before
  the cut-off; those are treated as open too. Excluding cured-and-active loans (which will
  mostly have zero loss) biases LGD **up**; excluding long workouts biases it **down**. To limit
  the second effect, LGD is estimated only on defaults at least 36 months before the cut-off.
  If open workouts are still more than 10% of that sample, a sensitivity analysis assigns each
  open workout its segment's 90th-percentile LGD and reports the difference.

### D9. Days-past-due buckets and the RBI SMA mapping

| Freddie Mac status | Days past due | `dpd_bucket` | RBI class (`sma_class`) |
|---|---|---|---|
| `00` | 0-29 | `current` | `standard_or_sma_0` |
| `01` | 30-59 | `dpd_30` | `sma_1` (31-60 days) |
| `02` | 60-89 | `dpd_60` | `sma_2` (61-90 days) |
| `03` to `99` | 90+ | `dpd_90p` | `npa` (over 90 days) |
| `RA` | REO | `reo` | `npa` |
| `XX` | unknown | `unknown` | `unknown` |

RBI's SMA-0 (1 to 30 days overdue) **cannot be separated** in this data: status `00` covers both
fully current loans and loans up to 29 days late. The SMA view therefore shows
"Standard or SMA-0" as one class and says so. The one-day offsets at the boundaries (Freddie
Mac's 30 against RBI's 31, 90 against "over 90") come from the difference between the MBA
delinquency convention and RBI's day count and are stated, not corrected. The methods carry over
to Ind AS 109 and RBI practice; the numbers are US mortgage numbers and do not.

---

## 2. Samples

### P1. Scorecard samples (fixed now; a loan's vintage is its origination year)

| Sample label | Vintages | Role |
|---|---|---|
| `dev_train` | 1999-2015, about 70% of loans | Binning, feature selection, model fit |
| `dev_test` | 1999-2015, the other 30% | In-time holdout: model selection, the reference for the Gini drop |
| `gap` | 2016 | Not used by the scorecard (see below) |
| `oot` | 2017, 2018, 2019, 2022, 2023, 2024 | Out-of-time test, **scored once** |
| `covid` | 2020, 2021 | Scored once, reported descriptively, no pass or fail |
| `excluded` | 2025, plus any loan excluded by D6 or P2 | Window incomplete, indeterminate, or out of scope |

Why:
- **Development includes a downturn.** 1999-2015 covers the 2005-2008 vintages, which carry the
  credit-crisis signature (default-type exits of 5.7% to 9.0% against about 1% before and
  after), and the tighter post-2009 underwriting. A scorecard built only on benign years would
  never have seen a bad year.
- **The 70/30 split** is a fixed hash of the loan identifier (`dev_train` when the first two hex
  digits of `md5(loan_id || 'split-v1')` are below `b3`, which is 179/256 = 69.9%). It is
  reproducible, the same on every warehouse, and independent of any loan attribute.
- **Gap year 2016.** Development outcome windows run to the end of 2016. Leaving 2016 out means
  no out-of-time loan was originated while a development loan's outcome was still being
  observed.
- **Out-of-time is the most recent complete vintages**, because a scorecard is used on new
  applicants. It gives about 300,000 loans and about 1,300 twelve-month defaults (Appendix A),
  enough for calibration by grade. Results are also broken down into 2017-2019 (pre-COVID) and
  2022-2024 (post-COVID, higher rates), as secondary views.
- **2020 and 2021 are held out of the pass/fail tests.** Their outcome windows fall inside the
  forbearance period, where the default flag depends mainly on the D3 rule rather than on
  borrower credit quality, and they have few events (113 and 121). They are scored once with the
  out-of-time set and published separately.
- **2025** does not have 12 months of performance.

### P2. Scorecard population exclusions

- **HARP and other relief refinances** (`harp_flag`), 83,473 loans. They refinanced existing
  underwater Freddie Mac loans with limited re-underwriting, so they are not new credit
  decisions. They stay in every portfolio, LGD and ECL analysis.
- Loans excluded by D6 (indeterminate or window incomplete).

Exclusion counts by reason and sample are published.

### P3. Out-of-time scored once

The out-of-time and COVID samples are scored by one function, one time, after the champion
scorecard and (if run) the challenger are frozen. The call is logged with a timestamp and the
model's hash, and a test fails if that function has been called more than once for the same
model. If a bug is found after the out-of-time scoring, it is fixed, the rescoring is logged as
a deviation, and both sets of numbers are published.

### P4. Time windows for the loss models

| Model | Fitted on | Held out |
|---|---|---|
| Competing-risk hazard (L1) | loan-months with reporting month up to 2016-12, all vintages to 2016 | reporting months from 2017-01 |
| Behavioural 12-month PD (L2) | quarter-end reporting dates 1999-03 to 2015-12 (outcomes to 2016-12) | year-end dates 2016-12 to 2024-12 |
| LGD segment means (G1) | defaults dated up to 2010-12, at least 36 months before cut-off | defaults 2011-01 onwards (for the LGD model comparison only) |

The ECL itself is computed at every quarter-end. Dates inside the fitting window are labelled
**in-sample** wherever they are shown (for example the 2008 ECL history).

---

## 3. Scorecard method

### S-method. Features

Candidate features, all known at origination:

| Feature | Type | Expected direction of risk |
|---|---|---|
| `fico` (Classic FICO) | numeric | falls as the score rises |
| `ltv_pct`, `cltv_pct` | numeric | rises |
| `dti_pct` | numeric | rises |
| `mi_pct` | numeric | rises (MI coverage tracks LTV) |
| `rate_spread_pct` | numeric | rises |
| `original_upb` | numeric | none assumed; monotonic either way |
| `original_loan_term` | banded: up to 180, 181-240, over 240 months | rises with term |
| `loan_purpose`, `occupancy_status`, `property_type`, `number_of_units`, `channel`, `first_time_homebuyer`, `super_conforming_flag` | categorical | from data |

`rate_spread_pct` is the note rate minus the median note rate of all sample loans with the same
first-payment month and term band (up to 180 months, or over). The raw note rate is **not** a
candidate: its level mostly records the market rate of its year, so it would act as a vintage
marker and drift. The spread keeps the risk-pricing signal.

Excluded, with the reason:

| Field | Reason |
|---|---|
| `property_state`, `postal_code`, `msa_or_md` | **Fairness.** Geography can proxy for race and ethnicity, which the US Equal Credit Opportunity Act and Fair Housing Act protect. Kept for LGD, portfolio and segment reporting |
| `number_of_borrowers` | **Fairness.** A close proxy for marital status, a protected characteristic under ECOA. Its IV and the Gini with and without it are reported on `dev_test` as a sensitivity, never used in the model |
| `seller_name`, `servicer_name` | Institution, not borrower. The servicer is assigned after origination (leakage) |
| `property_valuation_method`, `special_eligibility_program` | Populated only for recent vintages, so their missingness identifies the era |
| `vantage_score_4_0` | Missing for 100% of loans |
| `amortization_type`, `interest_only_indicator` | No variation (all fixed-rate, none interest-only) |
| `prepayment_penalty_indicator` | 1,468 loans flagged; too rare to bin |
| `first_payment_date`, vintage | Time, not risk; would not generalise |
| Anything from the performance file (`eltv`, delinquency, modification) | Leakage: not known at origination |
| `harp_indicator`, `pre_harp_loan_sequence_number` | Population excluded (P2) |

Sentinel codes (FICO 9999; DTI, LTV, CLTV and MI 999; categorical `9` or `99`) become missing,
never numbers.

### S-method. Binning

- Fitted on `dev_train` only (`optbinning`, or hand-written if simpler).
- Every bin holds at least **5% of `dev_train`** and at least **20 defaults**; at most 8 bins.
- **Monotonic WoE** for every numeric feature, in the expected direction above. If the data
  cannot give a monotonic binning in the expected direction, the feature is **dropped, never
  flipped**. `original_upb` may go either way, but must be monotonic.
- Categories below 5% of `dev_train` are grouped into `other`.
- Missing values get their own bin. If that bin has fewer than 20 defaults, it takes the WoE of
  the highest-risk bin of that feature (conservative), and this is reported.
- WoE convention: `WoE = ln(share of non-defaults in bin / share of defaults in bin)`.

### S-method. Screening and model

- **IV screen**: drop features with IV below **0.02**. Features with IV above **0.5** are
  reviewed for leakage and documented. They are not dropped automatically.
- **Correlation**: where two WoE features have |Pearson correlation| above **0.7** on
  `dev_train`, keep the one with the higher IV (LTV, CLTV and MI are expected to collide).
- **Model**: unpenalised logistic regression of `default_12m` on the WoE features (statsmodels).
  Under the WoE convention every coefficient must be **negative**. Any feature with a positive
  coefficient, or p above 0.01, is removed, and the model is refitted until all pass. VIF must
  be below 5. At most 12 features.

### S-method. Points and grades

- **PDO scaling**: 600 points at odds of **50:1** (good to bad), **20 points to double the
  odds**. So `factor = 20 / ln 2 = 28.8539`, `offset = 600 - factor * ln 50 = 487.1228`, and
  `score = offset + factor * ln(odds_good)`.
- Points for attribute j of feature i: `round(-factor * beta_i * WoE_ij + (offset - factor * beta_0) / k)`,
  where k is the number of features. The score is the sum of the rounded points, and
  `pd_12m = 1 / (1 + exp((score - offset) / factor))` is computed from that integer score, so
  the published points table, the website calculator and the Excel workbook all give exactly the
  same PD.
- **Grades**: a fixed PD master scale, where each grade doubles the PD (about 20 points each):

| Grade | 12-month PD from | to below |
|---|---|---|
| A | 0 | 0.10% |
| B | 0.10% | 0.20% |
| C | 0.20% | 0.40% |
| D | 0.40% | 0.80% |
| E | 0.80% | 1.60% |
| F | 1.60% | 3.20% |
| G | 3.20% | 100% |

If a grade holds under 1% of `dev_train` loans or fewer than 20 `dev_train` defaults, it is
merged with its neighbour towards the middle of the scale. That decision is made on `dev_train`
only and recorded; the grade letters of the remaining grades do not change.

- **Reason codes**: the three features whose points fall furthest below that feature's
  maximum, per loan.

---

## 4. Pass rules

All intervals are 95%. Bootstrap intervals use 1,000 resamples, stratified by outcome, seed
`20260923`, percentile method. Rates use the Jeffreys interval for binomial proportions and the
Wilson interval where a rate is only described, not tested.

### S1. Monotonic WoE
Every numeric feature in the final model has monotonic WoE in its expected direction. PASS or FAIL.
Result: pending

### S2. Discrimination holds out of time
`relative Gini drop = (Gini_dev_test - Gini_oot) / Gini_dev_test`, on the point estimate.
**Green (PASS)** at or below 10%; **Amber (PASS with finding)** above 10% and at or below 25%;
**Red (FAIL)** above 25%. The comparison is with `dev_test`, not `dev_train`, so that in-sample
fitting optimism is not mistaken for decay. The bootstrap interval of the drop is published with
it, as are Gini, AUC and KS with intervals on every sample.
Result: pending

### S3. Rank ordering out of time
The realised default rate on `oot` does not decrease from grade A to grade G. Any inversion
where the two grades' intervals do not overlap is a FAIL; an inversion inside overlapping
intervals is Amber.
Result: pending

### S4. Calibration by grade
For each grade, the mean predicted `pd_12m` lies inside the Jeffreys 95% interval of that
grade's realised default rate. Tested on `dev_test` (S4a) and `oot` (S4b). PASS only if every
grade passes; a grade with fewer than 20 events reports "insufficient events" instead of pass or
fail.

Expectation, stated now: the development period includes the crisis, so its average default
rate (about 0.76%, Appendix A) is higher than the out-of-time sample's (about 0.43%). A
scorecard calibrated on development is therefore expected to **over-predict** out of time, and
S4b may fail for that reason alone. If it does, it is reported as a FAIL, with the
calibration-in-the-large ratio (realised over predicted) and its interval. The scorecard is
**not** recalibrated on out-of-time data. The provisioning PD comes from L2, which conditions on
the reporting date; it is not the scorecard's intercept.
Result S4a: pending
Result S4b: pending

### S5. Population stability
PSI of the score, `dev_train` against `oot`, on the ten `dev_train` score deciles (empty bins
take 0.0001). **Below 0.10 stable; 0.10 to 0.25 Amber; above 0.25 Red (FAIL)**. CSI for every
model feature on the same thresholds, reported and flagged, with no separate pass or fail. PSI of
each origination year against `dev_train`, descriptive. Expectation, stated now: post-2009
underwriting is tighter than 1999-2008, so the FICO and DTI distributions will have shifted and
a Red PSI is plausible. That would be a finding about the population, not a coding error, and it
would not trigger a model rebuild.
Result: pending

### R1-R8. Reconciliation (hard stop)

Nothing downstream is published until these pass. They are tests, not judgement calls.

| Rule | Check | Tolerance |
|---|---|---|
| R1 | Loans per vintage, `dim_loan` against the origination Parquet | exact |
| R2 | Loan-months per vintage, `fct_loan_month` against the performance Parquet | exact |
| R3 | Sum of `current_upb` per reporting month, mart against Parquet | $1 per month |
| R4 | Sum of Freddie Mac `actual_loss` per vintage, `fct_loss_events` against Parquet | $1 per vintage |
| R5 | `computed_loss` against Freddie Mac `actual_loss`, per loss event where `actual_loss` is populated | within $1 for at least 99.5% of events; every exception listed with its cause |
| R6 | `total_expenses` against the sum of its four components | within $1 for at least 99.5% of events |
| R7 | MetricFlow metrics against `metrics_monthly` | relative difference below 1e-9 |
| R8 | Every count in an artefact against the mart it came from; money and rates | counts exact; money $1; rates 1e-9 |

The Excel workbook recalculates to `ecl.json` totals within 0.01% (rounding only).
Result: pending

---

## 5. Challenger (LightGBM with SHAP)

Built on the same candidate features as the scorecard (raw values, not WoE), with the same
fairness and leakage exclusions, and with LightGBM monotone constraints matching the expected
directions for the numeric features. Hyperparameters are chosen by five-fold cross-validation on
`dev_train` only; `dev_test` is used once to confirm; `oot` is scored once, in the same call as
the champion.

C1. The challenger is **recommended for promotion** only if **all** of these hold:
1. The paired bootstrap 95% interval of `Gini_challenger - Gini_champion` on `oot` (the same
   1,000 resamples for both models) has its **lower bound above +0.02**. A higher point AUC is
   not enough.
2. On `oot`, its calibration by grade (S4b, with its PDs put on the same master scale) fails in
   no more grades than the champion's.
3. Its score PSI from `dev_train` to `oot` is at most 0.25.
4. SHAP reason codes can be produced for every loan and every monotone constraint holds.

Whatever the outcome, the scorecard remains the model used downstream in this release (grades,
hazard, ECL, calculator, workbook). Swapping models after seeing out-of-time results would be a
result-driven change. A challenger that passes C1 is recorded as a recommendation for the next
release.
Result: pending

---

## 6. Lifetime PD

### L1. Competing-risk hazard (term structure and prepayment)

A discrete-time multinomial logit on loan-months. Outcomes are {stay, default, prepay}. Default
is D1, first occurrence; prepayment is D5. Codes 16 and 96 and the data cut-off censor.

- **Risk set**: active loans not yet in default, `months_on_book` 1 or more, whatever their
  current delinquency. Excluding delinquent loans would remove almost every path to default.
- **Covariates**: scorecard grade (7 levels); loan-age band (`months_on_book` 1-12, 13-24,
  25-36, 37-60, 61-120, 121+, piecewise constant, which gives the seasoning curve); rate
  incentive band (current note rate minus the market rate, which is the median note rate of
  newly originated 30-year loans in that month: below -0.5, -0.5 to 0.5, 0.5 to 1.5, above 1.5
  percentage points). The incentive is there because prepayment is driven by refinancing, and
  without it every refinancing boom (2003, 2012, 2020-21) would be missed. Main effects only.
  Stretch: the macro covariate in E6.
- **Estimation**: counts aggregated in the warehouse by covariate cell, then fitted by maximum
  likelihood with frequency weights, which gives exactly the loan-level estimate.
- **Projection**: the rate incentive is held at its reporting-date value. Prepayment is a
  competing risk throughout, so a loan that prepays cannot default later. Lifetime PD is the sum
  of marginal default probabilities, never one minus the product of default-only survival.

L1a. Diagnostic: predicted against realised 12-month prepayment rate by grade at the held-out
year-ends. Described, not a pass rule. The model has no house-price or burnout effect on
prepayment, a stated limitation.
Result: pending

### L2. Behavioural 12-month PD (first year and SICR)

A logistic regression on loan-quarter rows (`fct_stage_inputs`) for loans not in default, target
`default_next_12m`. Covariates: grade; loan-age band; behaviour state (`clean`, `recent_dpd` = current
but 30+ days past due at some point in the previous 12 months, `dpd_30`, `dpd_60p` = 60-89 days
past due or 90+ and exempt under D3); `modified`. Stretch: the macro covariate in E6.

A month with status `XX` takes the `dpd_30` state (conservative; 0.02% of loan-months).
Forborne 90+ loans are pooled with `dpd_60p` because forbearance flags exist only from 2014, so
the fitting window holds too few forborne loans to estimate them separately. The 2020-12
backtest date shows whether that was too harsh.

### L3. Combining them

For a loan at a reporting date: in months 1 to 12 the marginal default probability is
`PD12 / 12` per month (the L2 PD spread evenly), and prepayment comes from L1. From month 13 on,
default and prepayment both come from L1, applied to survivors. The horizon is the remaining
contractual term.

---

## 7. IFRS 9 / Ind AS 109

### E1. Staging (at each quarter-end)

| Stage | Rule | Where it is computed |
|---|---|---|
| 3 | In default under D1 and not yet cured (D4) | dbt (`stage_floor`) |
| 2 | 30+ days past due (the IFRS 9 backstop) | dbt |
| 2 | Status `XX` (not available), treated conservatively | dbt |
| 2 | Forbearance or disaster flag active, or on a trial or repayment plan (qualitative indicator) | dbt |
| 2 | Cured within the last 6 months (probation) | dbt |
| 2 | **PD deterioration**: `PD12_now / PD12_ref >= 2.0` **and** `PD12_now - PD12_ref >= 0.20` percentage points | Python |
| 1 | None of the above | |

`PD12_ref` is L2 evaluated with the loan's own grade and **current** loan-age band, but with
behaviour state `clean`, `modified` false and (stretch) the macro value at origination. Using
the current age compares like with like, so ordinary seasoning never triggers a stage move by
itself. This follows IFRS 9 paragraph 5.5.9, which compares against the risk that was expected at initial
recognition for the same remaining period. The 2.0x relative threshold is common practice for
low-PD books; the 0.20 point absolute floor stops very low-PD loans from moving on noise.
No low-credit-risk exemption is used.

Stage = the maximum of the dbt stage floor and the Python PD-deterioration flag.

### E2. ECL

- **Stage 1**: 12-month ECL = sum over months 1 to 12 of marginal PD x LGD x EAD(t) x
  discount factor.
- **Stage 2**: the same sum over the remaining contractual term (lifetime ECL).
- **Stage 3**: PD = 1, ECL = LGD x current exposure. Time spent in default does not change the
  LGD (stated).
- **LGD** is the `lgd_economic` segment mean by origination LTV band (G1). The G2 model is used
  instead only if it passes G2.
- **Discounting** is monthly at the original note rate (the effective interest rate, also for
  modified loans that were not derecognised).
- **Outputs**: ECL by stage and grade, coverage ratio (ECL over exposure), stage mix and stage
  migration matrices, every quarter-end. Dates inside a fitting window are labelled in-sample.

### E3. ECL backtest

At each held-out year-end from 2016-12 to 2024-12, for Stage 1 and Stage 2 loans by grade:
predicted = mean `PD12`, realised = share with `default_next_12m`. Each grade gets a colour:
- **Green**: realised rate inside the binomial 95% interval around predicted.
- **Amber**: outside that, but inside the 95% interval of the Vasicek one-factor distribution
  with asset correlation 0.15. Mortgage defaults are correlated, so independent-binomial
  intervals are too narrow on their own.
- **Red**: outside both.

A date passes if it has no Red grade. **Overall PASS** if all seven non-COVID dates pass. The
dates 2019-12 and 2020-12, whose outcome windows cover the forbearance period, are shown but
excluded from the count, as decided now. If the backtest fails, the failure is reported with its
direction (cycle or ranking); the PD model is **not** refitted on held-out periods and no
management overlay is added to make it pass.
Result: pending

### E4. Pass rules for the loss engine
- E4a. Hand-worked loan: ECL = PD x LGD x EAD x discount factor within $0.01 (unit test).
- E4b. Staging edge cases unit-tested: 29 against 30 days past due, cure probation, a forborne
  90+ loan (Stage 2, not 3), a credit-event exit.
- E4c. Marginal default plus marginal prepay plus final survival sum to 1 for every grade (unit
  test, 1e-12).
Result: pending

### E5. What ECL here is not
It is not a regulatory or audited provision. The minimum version has no forward-looking
information (IFRS 9 requires it; the stretch scenarios in E6 add it). It covers US conforming
mortgages, not an Indian book.

### E6. Macro scenarios (stretch)

- **Source**: FHFA House Price Index, national, purchase-only, monthly, seasonally adjusted
  (public). It is downloaded only after approval. If not approved, E6 is dropped and E5 says so.
- **Covariate**: 12-month % change in the national index, lagged 3 months, added to L1 and L2.
- **Scenarios** (paths for the 12-month HPI change from the reporting date):
  - base: the median 12-month change over the index's full history, held flat
  - adverse: the realised path from January 2007 to December 2011, replayed from the reporting
    date, then back to base
  - upside: the 90th-percentile 12-month change for 24 months, then base
- **Weights**: base 60%, adverse 25%, upside 15%, fixed now. ECL is the probability-weighted
  average of the three scenario ECLs (not the ECL of an average scenario, which would miss the
  non-linearity). Staging uses the probability-weighted `PD12`. The ECL under 100% adverse is
  published as a sensitivity.

---

## 8. LGD

### G1. Segment LGD (minimum)
Mean `lgd_economic`, `lgd_gross_of_mi` and `lgd_undiscounted` with bootstrap intervals by:
origination LTV band (up to 60, 60-80, 80-90, 90-95, over 95), property state, disposition type,
default year, and overall. A segment with fewer than 50 resolved defaults is folded into `other`
and not reported alone. Open-workout share by default year is reported (D8).

### G2. LGD model (stretch)
Two stages: the probability of a positive loss (logistic), then severity given a loss
(fractional logit), on origination LTV band, MI %, loan-size band, occupancy, property type and
state group. It is fitted on defaults up to 2010-12 and compared on defaults from 2011-01 (P4).
It is used in ECL only if the paired bootstrap interval of `MAE_model - MAE_segment_mean` on the
held-out defaults lies **entirely below 0**. Otherwise G1 stays.
Result: pending

---

## 9. Basel IRB capital (stretch, illustrative)

- **Formula** (retail, residential mortgage):
  `K = LGD * N( G(PD) / sqrt(1 - R) + sqrt(R / (1 - R)) * G(0.999) ) - PD * LGD`, with asset
  correlation **R = 0.15**, no maturity adjustment, `RWA = 12.5 * K * EAD`, and a capital
  requirement of `K * EAD` (8% of RWA).
- **PD**: the long-run average by grade, which is the mean of the annual 12-month default rates
  of each grade over the development period (so it includes the crisis), floored at 0.05%.
- **LGD**: downturn LGD, which is the mean `lgd_gross_of_mi` of defaults dated 2008-01 to
  2011-12, by LTV band, floored at 5%. Gross of MI, to avoid any claim about whether MI is an
  eligible credit-risk mitigant.
- **Scope**: non-defaulted exposures at the latest reporting date. Defaulted exposures are shown
  with their EAD and are not given a K.
- **Stated limits**: illustrative only, not a regulatory calculation. There is no 1.06 scaling
  factor and no output floor against the standardised approach. US banks hold these loans under
  the standardised approach, and RBI has not implemented IRB for Indian banks. Capital is shown
  next to ECL to compare expected and unexpected loss, nothing more.

---

## 10. Decided now: what makes an analysis change or be dropped

| If | Then |
|---|---|
| Any R rule fails | Hard stop: nothing downstream is published until it is fixed |
| A final grade has fewer than 20 out-of-time defaults | S4b reports "insufficient events" for that grade; grades are never re-cut on out-of-time data |
| D1a above 10% | Add the modification-trigger sensitivity; the primary definition stays |
| S2 Red | Reported as a High finding. The scorecard still feeds grades downstream (no redesign in this release) |
| S4b fails | Reported. No recalibration on out-of-time data; ECL uses L2 |
| S5 Red | Reported as population drift. No rebuild |
| C1 passes | Recorded as a recommendation only (section 5) |
| G2 fails | ECL uses G1 segment means |
| Open workouts above 10% of the LGD sample | Add the 90th-percentile sensitivity (D8) |
| An LGD segment has fewer than 50 defaults | Folded into `other` |
| The HPI download is not approved | E6 is dropped; the ECL is stated to have no forward-looking information |
| An L1 or L2 cell fails to converge or has no events | Merge the grade with its neighbour for that model only; record it |
| E3 fails | Reported with its direction. No refit on held-out periods, no overlay |
| A bug is found after out-of-time scoring | Fix it, rescore, log a deviation, publish both results |

---

## 11. What these results will not establish

- **No reject inference.** The data holds only loans Freddie Mac bought: no declined applicants,
  no non-conforming or portfolio loans. The scorecard ranks approved conforming borrowers only.
- **Not Indian loans.** The methods map to Ind AS 109 and RBI SMA practice; the numbers do not.
- **Not causal.** Feature effects are associations. A point weight is not the effect of changing
  a borrower's attribute.
- **Not a production PD.** A 1999-2015 development window with a fixed master scale is neither
  fully point-in-time nor fully through-the-cycle, and S4 tests which way it leans.
- **Not a fair-lending review.** Excluding geography and number of borrowers removes obvious
  proxies. No disparate-impact test is possible, because the data has no protected attributes.
- **Not an audited provision or regulatory capital number** (E5, section 9).
- **The sample is a sample.** 50,000 loans per vintage give tight intervals on portfolio rates
  but wide ones on thin segments; every number is published with its n.

---

## Appendix A. Sizing aggregates looked at before writing

Computed with a DuckDB query over the Parquet files, using Freddie Mac's `loan_age` as the clock
(the dbt build uses `months_on_book`, D0, so final counts may differ slightly). Twelve-month
defaults per vintage (50,000 loans each; 49,995 in 2025, whose window is incomplete):

| Vintage | Naive (D2) | Primary (D1 + D3) | Primary, 24-month window |
|---|---|---|---|
| 1999 | 212 | 211 | 532 |
| 2000 | 413 | 412 | 833 |
| 2001 | 283 | 283 | 626 |
| 2002 | 291 | 291 | 537 |
| 2003 | 205 | 203 | 383 |
| 2004 | 358 | 353 | 730 |
| 2005 | 575 | 571 | 1,059 |
| 2006 | 869 | 862 | 1,708 |
| 2007 | 1,224 | 1,214 | 3,077 |
| 2008 | 945 | 939 | 2,229 |
| 2009 | 184 | 180 | 414 |
| 2010 | 176 | 171 | 431 |
| 2011 | 183 | 178 | 382 |
| 2012 | 182 | 176 | 364 |
| 2013 | 152 | 135 | 297 |
| 2014 | 180 | 153 | 332 |
| 2015 | 152 | 121 | 277 |
| 2016 | 155 | 100 | 296 |
| 2017 | 312 | 200 | 415 |
| 2018 | 198 | 160 | 371 |
| 2019 | 1,211 | 150 | 332 |
| 2020 | 649 | 113 | 225 |
| 2021 | 228 | 121 | 275 |
| 2022 | 418 | 273 | 718 |
| 2023 | 328 | 276 | 763 |
| 2024 | 302 | 240 | 516 |

Development 1999-2015: 6,453 primary defaults in 850,000 loans (0.76%) before the HARP
exclusion. Out-of-time: 1,299 in 300,000 (0.43%).

Flag coverage by reporting year: `borrower_assistance_plan` and `delinquency_due_to_disaster`
are empty before 2014 (as the user guide says). The estimated current LTV (`eltv`) is empty
before 2017, so it cannot be used in any model that is fitted on the crisis. It is carried in
the marts for description only.

---

## Deviations

None yet. Each entry gives the date, the rule, what changed, why, and the result under both the
original and the changed rule.
