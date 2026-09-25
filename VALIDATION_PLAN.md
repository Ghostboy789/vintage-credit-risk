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

**What that did and did not leave blind** (added after an independent review, before any
result). The per-vintage default counts show the out-of-time default rate before any score
exists, so the **direction of S4b (calibration in the large) was known in advance**: the
scorecard will over-predict out of time. S4b is therefore not a blind test, and it is presented
as a known consequence of the design, not as a finding. The rank-ordering and discrimination
tests (S2, S3) stay blind: no score, grade or feature-level outcome was looked at. The
out-of-time window and the COVID rule in P1 were chosen with those counts visible. Appendix B
lists every query run on the real data before the freeze, with the scripts' hashes.

**Freeze.** The plan is frozen at the commit tagged `plan-freeze`. Edits before that tag, all
made before any result: `08cfa54` (the plan), `a955ea0` (how status `XX` is staged) and the
commits that apply the independent review's findings, up to and including the tagged commit.
Any later change goes in "Deviations". From the freeze until out-of-time scoring (P3), **no
ad-hoc query may compute an outcome (default, loss, prepayment or cure) on 2016 or later
vintages**. The pipelines this plan specifies (the dbt marts and their tests) compute them as
written, but their 2016+ outcome columns are not summarised or inspected before P3, and the
portfolio analytics that describe 2016+ vintages are produced after P3. Any exception is logged
as a deviation with its reason and output.

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

Defect settlements still default. Codes `02`, `03`, `09` and `15` trigger default even when the
exit is later settled as an underwriting or servicing defect (D8, `defect_settlement`): the
credit event happened, whoever bears the loss.

What does **not** count as default:
- **Loan modification** (`modification_flag` Y or P). Under EBA-style rules a distressed
  restructuring is an unlikeliness-to-pay default, but Freddie Mac modifications are almost
  always made on loans that are already 60 to 90+ days past due, so D1 catches them anyway.
  Loans modified before (or without) any primary default are reported (rule D1a). If they
  exceed 10% of primary defaults, a sensitivity definition that adds "first modification" as a
  trigger is added to the scorecard results, and the primary definition stays as it is.
- **Payment deferral** (`payment_deferral_flag`). Freddie Mac says deferrals are not
  modifications.
- **Zero Balance Codes `16` (reperforming loan securitisation) and `96` (repurchase for an
  underwriting or servicing defect before a credit event).** The loan leaves the data with no
  observable credit outcome. It is treated as **censored** at that month, not as a default and
  not as a prepayment.
- **Status `XX` (not available).** Treated as missing: neither a default trigger nor current.

D1a. Numerator: loans whose first modification month comes before their first primary default
month, or that have a modification and no primary default at all. Denominator: loans with a
primary default. Reported overall and by scorecard sample (P1), with both counts. This catches
the case an independent review pointed out: a forborne loan that was 90+ but exempt under D3
and then modified was "90+ before modification" and yet never defaulted under D1. The ratio is
not a proportion (the numerator is not a subset of the denominator), so it is reported without
an interval.
Result: PASS, below the 10% trigger (run of 2026-09-25, scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`; out-of-time scored once, 2026-09-24T23:57:05Z). 2,185 loans modified before or without a primary
default, against 54,615 loans with a primary default at any time: 4.0% (a ratio, no interval).
By sample: `dev_train` 838 / 29,300 (2.9%), `dev_test` 362 / 12,710 (2.8%), `gap` 147 / 863
(17.0%), `oot` 407 / 5,475 (7.4%), `covid` 178 / 1,988 (9.0%), `excluded` 253 / 4,279 (5.9%).
The rule is on the overall ratio, so the modification-trigger sensitivity is not added.

### D2. Default sensitivity ("naive") definition

The same as D1 but without the D3 exemption. Both are built in `fct_default_events` (column
`definition`), and default counts per vintage are published under both, so anyone can see what
the forbearance rule changed.

The two definitions differ unevenly over time: the forbearance and disaster flags exist only
from 2014 (D3), so D3 removes about 2% of development-sample defaults but about a quarter of
the non-COVID out-of-time ones (Appendix A: 2017 has 312 naive against 200 primary, 2022 has
418 against 273). The development target and the out-of-time target are therefore not quite
the same variable. To show what that does, `fct_scorecard_base` also carries
`default_12m_naive`, and **S2 and S4b are also reported under D2** as secondary results. The
primary definition alone decides pass or fail.

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
The cure month itself is **not** in default (`in_default` is false from the cure month on). The
D4 cure rate (share of primary defaults that cure within 12 months of the default month, and
ever by the cut-off) is published by default year, separately from the roll-rate cure.

In roll rates, "cure" means something narrower: a month-to-month move from any past-due bucket
to `current`. The two are always labelled separately.

### D5. Prepayment and other exits

- **Prepayment**: Zero Balance Code `01` with no earlier default. Code `01` also covers maturity;
  it is labelled `matured` if `months_on_book` is at least the original term minus one, and
  `prepaid` otherwise. Partial prepayments (curtailments) are not prepayment events.
- **Credit-event exit**: Zero Balance Codes `02`, `03`, `09`, `15`. When the loan also has an
  Underwriting Defect and Major Servicing Defect Settlement Date, the exit is still a credit
  event and a default, but Freddie Mac reports no actual loss ("not applicable" in the user
  guide), so its resolution is `defect_settlement` (D8).
- **Other exit**: codes `16` and `96` (censored, D1).

### D6. Twelve-month outcome window (scorecard)

`default_12m` = 1 if the loan's first primary default (D1) happens at `months_on_book` 1 to 12.

- A loan that prepays inside the window without defaulting is a **non-default** (0). It did
  not default within 12 months. Dropping prepayers would distort the population towards loans
  that stay on book.
- A loan that leaves through code `16` or `96` inside the window without defaulting is
  **indeterminate** and is excluded (`exclusion_reason = indeterminate_exit`). These exits are
  not random (defect repurchases, code 96, lean towards riskier loans), so their counts are
  published by sample and by code.
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
`df = (1 + note_rate / 1200) ^ -(months from the default month to the disposition month)`, where
the disposition month is the month of the Zero Balance Effective Date on the terminal record
(the terminal reporting month if that date is missing):

| Measure | Formula | Used for |
|---|---|---|
| `lgd_economic` (primary) | `(ead - net_recovery * df) / ead` | ECL, reporting |
| `lgd_undiscounted` | `computed_loss / ead`, where `computed_loss` is the formula above | Reconciliation to Freddie Mac's `actual_loss` |
| `lgd_gross_of_mi` | as `lgd_economic`, with `mi_recoveries` left out of `net_recovery` | Basel (section 9), and to show what mortgage insurance is worth |

Decisions inside these formulas:
- **Discounting** is at the loan's original note rate, which is its effective interest rate.
  Because discounting at the contract rate already charges for the interest forgone during the
  workout, `lgd_economic` does not add delinquent accrued interest on top. All disposition cash
  flows are dated at the disposition month defined above. That is conservative for recoveries
  and slightly flattering for expenses, which really accrue during the workout (stated).
- **Paid-off defaults** (a defaulted loan that later exits with code `01`) have all three LGDs
  set to **0 by definition**, not by the formula. A code `01` payoff repays the balance with the
  interest owed, so there is no loss at the note rate; the formula with `net_recovery = ead`
  would instead give `1 - df` and charge the borrower's own interest as a loss.
- **Mortgage insurance** recoveries are netted in the primary measure. Under IFRS 9 (B5.5.55),
  credit enhancements that are part of the contract are included in expected loss; MI on these
  loans is. `lgd_gross_of_mi` is published next to it.
- **LGD is not capped.** Values above 1 (costs exceeding the balance) and below 0 (gains) are
  kept, and their shares are reported.
- **Every primary default gets one resolution** (`fct_default_events.resolution`), first that
  applies:

  | Resolution | Condition | In the LGD sample |
  |---|---|---|
  | `defect_settlement` | Terminal code `02`, `03`, `09` or `15`, and the loan has an Underwriting Defect Settlement Date on any record | No: Freddie Mac reports no actual loss ("not applicable"); the loss was settled with the seller or servicer |
  | `credit_event_loss` | Terminal code `02`, `03`, `09` or `15` with actual loss populated | Yes (loss as above) |
  | `paid_off` | Terminal code `01` | Yes (LGD 0) |
  | `other_exit` | Terminal code `16` or `96` | No: no loss observable |
  | `cured_active` | No terminal record, and cured (D4) | No |
  | `open` | Anything else: no terminal record and not cured, or a credit-event exit whose actual loss is still null under Freddie Mac's three-month rule | No |

  An independent review's aggregate count (Appendix B) found about 1,470 credit-event exits
  with a permanently null actual loss, every one with a settlement date, against 47 nulls from
  the three-month rule. Without the `defect_settlement` class they would be counted as open
  workouts. The settlement date is carried into the marts, and the share of defaults by
  resolution is published by default year.
- **The LGD sample is biased, in both directions, and both are measured.** Excluding
  cured-and-active loans and code `16` exits (reperforming-loan sales, which leave after a cure
  or modification and will mostly have little or no loss) biases LGD **up**. Excluding long
  workouts biases it **down**; to limit that, LGD is estimated only on defaults at least 36
  months before the cut-off. Published by default year: the share of primary defaults in each
  resolution. Two sensitivities are pre-registered: (a) **zero-loss exclusions**, always
  run: `cured_active` and `other_exit` with code `16` enter the sample with LGD 0; (b) **open
  workouts**, run if `open` defaults are more than 10% of the 36-month sample (otherwise
  published as not needed, with the share): each is given its LTV-band segment's
  90th-percentile `lgd_economic`. Each reports the overall
  `lgd_economic` and its difference from the primary estimate. Neither replaces the primary
  estimate. `defect_settlement` and code `96` stay out of both (their loss is borne by
  someone else or unobservable).

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
| `covid` | Any 2017-2024 loan whose outcome window touches the COVID period (below) | Scored once, reported descriptively, no pass or fail |
| `oot` | The other 2017-2024 loans | Out-of-time test, **scored once** |
| `excluded` | 2025, plus any loan excluded by D6 or P2 | Window incomplete, indeterminate, or out of scope |

**The COVID rule is loan-level.** A loan is `covid` if its outcome window (months on book 1 to
12, D6) overlaps the `covid` economic period, 2020-03 to 2021-12: that is, if its first
payment date is between 2019-04 and 2021-12 inclusive. The order of assignment is: `excluded`,
then `dev_train`/`dev_test` (vintages 1999-2015), then `gap` (2016), then `covid`, then `oot`.
So almost every 2019, 2020 and 2021 loan is `covid`; a few early-2019 originations (first
payment by 2019-03) and late-2021 originations with a first payment in 2022 are `oot`. A rule
by vintage alone would have put the 2019 vintage in the out-of-time test, although its windows
fall almost entirely in the forbearance period and it is the vintage most changed by D3 (1,211
naive against 150 primary defaults, Appendix A). That would also have contradicted E3, which
already leaves the 2019-12 backtest date out for the same reason. A pooled view of all 2017-2024
loans (`oot` plus `covid`) is published as a secondary view only.

Why:
- **Development includes a downturn.** 1999-2015 covers the 2005-2008 vintages, which carry the
  credit-crisis signature (default-type exits of 5.7% to 9.0% against about 1% before and
  after), and the tighter post-2009 underwriting. A scorecard built only on benign years would
  never have seen a bad year.
- **The 70/30 split** is a fixed hash of the loan identifier (`dev_train` when the first two hex
  digits of `md5(loan_id || 'split-v1')` are below `b3`, which is 179/256 = 69.9%). It is
  reproducible, the same on every warehouse, and independent of any loan attribute.
- **Gap year 2016.** Development outcome windows run to early 2017: a December 2015
  origination usually makes its first payment in February 2016, so its window ends in January
  2017. Leaving 2016 out means that out-of-time loans were originated at most a month or so
  before the last development outcomes were observed, not during them.
- **Out-of-time is the most recent complete vintages**, because a scorecard is used on new
  applicants. Under the loan-level COVID rule it is essentially the 2017, 2018, 2022, 2023 and
  2024 vintages: about 250,000 loans and about 1,150 twelve-month primary defaults (0.46%,
  Appendix A, before HARP exclusions), enough for calibration by grade. Results are also broken
  down into 2017-2019 (pre-COVID) and 2022-2024 (post-COVID, higher rates), as secondary views.
- **COVID-window loans are held out of the pass/fail tests.** Their outcome windows touch the
  forbearance period, where the default flag depends mainly on the D3 rule rather than on
  borrower credit quality, and they have few events (Appendix A: 150, 113 and 121 for the 2019,
  2020 and 2021 vintages). They are scored once with the out-of-time set and published
  separately.
- **2025** does not have 12 months of performance.

### P2. Scorecard population exclusions

- **HARP and other relief refinances** (`harp_flag`), 83,473 loans. They refinanced existing
  underwater Freddie Mac loans with limited re-underwriting, so they are not new credit
  decisions. They stay in every portfolio, LGD and ECL analysis.
- Loans excluded by D6 (indeterminate or window incomplete).

Exclusion counts by reason and by the sample the loan would otherwise have joined are published,
with indeterminate exits split by code (`16`, `96`).

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
| LGD segment means used in ECL (G1) | every resolved primary default in the LGD sample (default at least 36 months before the cut-off, so up to 2023-03) | none |
| LGD comparison, G1 against G2 | defaults dated up to 2010-12 | defaults 2011-01 to 2023-03 (for the G2 test only) |

The ECL itself is computed at every quarter-end. Dates inside the fitting window are labelled
**in-sample** wherever they are shown (for example the 2008 ECL history). Because the G1 LGDs
used in ECL are estimated on defaults up to 2023-03, every ECL date uses LGDs that include
later information; that is stated next to the ECL history.

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
marker and drift. The spread keeps the risk-pricing signal. Stated limit: the median uses every
loan with the same first-payment month, including loans priced a few weeks after the applicant.
A lender would use the previous month's median. The difference is a few weeks of rate movement,
it uses no outcome, and it is kept for simplicity.

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

Two kept candidates are treated consistently with the exclusions above, and the reason is stated:
- `first_time_homebuyer` correlates with age, which ECOA protects. It is kept because it is a
  property of the transaction that conforming-loan pricing itself uses, and its link to age is
  much looser than `number_of_borrowers`' link to marital status. It gets the same sensitivity:
  its IV, and the `dev_test` Gini with and without it, are published.
- `super_conforming` exists only from 2008, like the era-marker fields that are excluded. It is
  kept because it is not missing before 2008: the product (loans above the national limit in
  high-cost areas) was only created in 2008, so the blank flag before then correctly means "not
  super-conforming". It can still act partly as an era marker, which its CSI will show.

### S-method. Binning

- Fitted on `dev_train` only, with **`optbinning` 1.0.0** (`OptimalBinning`, one engine for
  every feature; no hand-written binning). Pinned parameters for every feature:
  `solver="cp"`, `prebinning_method="cart"`, `max_n_prebins=20`, `min_prebin_size=0.05`,
  `min_bin_size=0.05`, `max_n_bins=8`, `min_bin_n_event=20`, `split_digits=4`,
  `time_limit=600`, everything else at its default.
- Numeric features (`dtype="numerical"`): `monotonic_trend` is `"descending"` (default rate falls
  as the value rises) for `fico`, `"ascending"` for `ltv_pct`, `cltv_pct`, `dti_pct`, `mi_pct`
  and `rate_spread_pct`, and `"auto_asc_desc"` for `original_upb`. Categorical features
  (`dtype="categorical"`, including `term_band`, `number_of_units` and `super_conforming` as
  strings): `cat_cutoff=0.05` (categories under 5% of `dev_train` are grouped into `other`),
  `monotonic_trend=None`.
- A feature is **dropped, never flipped**, if the solver status is neither `OPTIMAL` nor
  `FEASIBLE`, if it returns a single non-missing bin, or if the WoE of its non-missing bins is not monotonic in the
  expected direction (checked after fitting, S1).
- Missing values get their own bin (optbinning's missing bin). If that bin has fewer than 20
  defaults, it takes the WoE of the highest-risk bin of that feature (conservative), and this is
  reported.
- WoE convention: `WoE = ln(share of non-defaults in bin / share of defaults in bin)` (the
  opposite sign to optbinning's own; it is converted once, in one function).

### S-method. Screening and model

The steps run in this order, each on `dev_train`. Wherever a tie has to be broken, the feature
listed earlier in the candidate table above is kept (the order is `fico`, `ltv_pct`,
`cltv_pct`, `dti_pct`, `mi_pct`, `rate_spread_pct`, `original_upb`, `term_band`,
`loan_purpose`, `occupancy_status`, `property_type`, `number_of_units`, `channel`,
`first_time_homebuyer`, `super_conforming`).

1. **Binning** as above; features that fail are dropped.
2. **IV screen**: drop features with IV below **0.02**. Features with IV above **0.5** are
   reviewed for leakage and documented. They are not dropped automatically.
3. **Correlation screen**: compute |Pearson correlation| of the WoE-transformed features
   (missing bins included). Take the pairs above **0.7** in descending order of correlation;
   for each pair where both features are still in, drop the one with the lower IV (LTV, CLTV
   and MI are expected to collide).
4. **Model**: unpenalised logistic regression of `default_12m` on the remaining WoE features
   (statsmodels `Logit`, Newton method, `maxiter=100`). Under the WoE convention every
   coefficient must be **negative**.
5. **Elimination, one feature per refit**, first rule that applies: (a) a positive coefficient:
   drop the feature with the largest positive coefficient; (b) p above **0.01**: drop the
   highest p; (c) VIF of **5 or more** (computed on the WoE design with a constant): drop the
   highest VIF; (d) more than **12** features: drop the smallest absolute z statistic. Refit
   and repeat until none applies.

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
merged with its neighbour towards the middle of the scale (grade D). Mechanically: grades are
checked in the order A, G, B, F, C, E, D, and counts are recomputed after every merge. A failing
grade merges into its surviving neighbour nearer D, which keeps its own letter and widens its PD
band; the failing letter disappears. If D itself fails, it merges into the surviving neighbour
with more `dev_train` loans (C on a tie), and that neighbour keeps its letter. Merges repeat
until every surviving grade passes or one grade is left. That decision is made on `dev_train`
only and recorded; the letters of the surviving grades do not change.

- **Reason codes**: the three features whose points fall furthest below that feature's
  maximum, per loan (ties broken by the candidate order above).
- **The scorecard PD is a development-period PD.** Development includes the crisis, so its
  PD is expected to be well above recent default rates (about 0.76% against 0.46%, Appendix A).
  Wherever the scorecard PD is shown on its own (the website calculator, the Excel workbook,
  the points table), it is labelled "12-month PD, 1999-2015 development average" and the S4b
  result is linked next to it. The provisioning PD is L2, not this.

---

## 4. Pass rules

All intervals are 95%. Each published number names its method (`ci_method` in CONTRACTS.md).
The methods, fixed now:

| Quantity | Interval |
|---|---|
| Default rates in a pass rule (S3, S4, E3 realised rates) | Jeffreys (`jeffreys_95`) |
| Described rates of loans (vintage cumulative default rates, sample default rates, cure rates) | Wilson (`wilson_95`) |
| Rates over loan-months (roll rates, CPR, monthly default rate) | Wilson on loan-months (`wilson_95_loan_months`). A loan contributes many months, so these intervals are too narrow; that is stated wherever they are shown |
| AUC, Gini, KS, the S2 Gini drop and C1's paired Gini difference | Bootstrap: 1,000 resamples of **loans**, stratified by the 12-month outcome, seed `20260923`, percentile. C1 uses the same resamples for both models |
| S4b calibration in the large (realised over mean predicted PD) | The Jeffreys interval of the realised rate, divided by the mean predicted PD (the PDs are treated as fixed) |
| PSI and CSI | Bootstrap: 1,000 resamples of loans, drawn separately from each of the two samples, bin edges held fixed, percentile |
| LGD means (G1, downturn LGD, sensitivities) and G2's MAE difference | Bootstrap: 1,000 resamples of resolved defaults (loans), not stratified, percentile |
| ECL and coverage | Parameter uncertainty only: 1,000 draws of the L1 and L2 coefficients from their estimated normal sampling distributions, and of the G1 segment means from their bootstrap, with the portfolio at the reporting date held fixed; percentile (`parameter_draws_1000`). It does not cover the macro scenarios or model choice. L1 is fitted on grouped loan-month counts, whose covariance treats loan-months as independent, so the interval is too narrow; that is stated |
| Basel long-run PD by grade | t interval of the mean of the annual rates (section 9) |
| Population counts and sums (loans, balances) | None: `none: population count, not an estimate` |

Every bootstrap resamples loans, never loan-months.

### S1. Monotonic WoE
Every numeric feature in the final model has monotonic WoE in its expected direction. PASS or FAIL.
Result: PASS (run of 2026-09-25, scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`; out-of-time scored once, 2026-09-24T23:57:05Z). The numeric model features `fico`, `ltv_pct`, `dti_pct` and
`rate_spread_pct` all have monotonic WoE in their expected direction.

### S2. Discrimination holds out of time
`relative Gini drop = (Gini_dev_test - Gini_oot) / Gini_dev_test`, on the point estimate.
**Green (PASS)** at or below 10%; **Amber (PASS with finding)** above 10% and at or below 25%;
**Red (FAIL)** above 25%. The comparison is with `dev_test`, not `dev_train`, so that in-sample
fitting optimism is not mistaken for decay. The bootstrap interval of the drop is published with
it, as are Gini, AUC and KS with intervals on every sample. Secondary, not pass or fail: the same
drop with `default_12m_naive` (D2) as the outcome on both samples, and the pooled
`oot` plus `covid` view.
Result: AMBER, PASS with finding (run of 2026-09-25, scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`; out-of-time scored once, 2026-09-24T23:57:05Z). Gini `dev_test` 0.7109 [0.6855, 0.7354], `oot` 0.5336
[0.5055, 0.5625]; relative drop 0.2494 [0.2010, 0.2951], absolute drop 0.1773 [0.1390, 0.2127]
(bootstrap_1000). The point estimate is 0.0006 below the Red line and its interval crosses it.
Secondary: under D2 on both samples the drop is 0.2711 [0.2268, 0.3162] (Red on that
definition); pooled `oot` plus `covid` Gini 0.4995 [0.4717, 0.5288], a relative drop of 0.297
(point only; the drop's bootstrap was run for `oot` only); 2017-2019 vintages Gini 0.5054
[0.4441, 0.5727], 2022-2024 vintages 0.5327 [0.4995, 0.5679].

### S3. Rank ordering out of time
The realised default rate on `oot` does not decrease from grade A to grade G. Only **adjacent**
surviving grades are compared (A with B, B with C and so on, after any merge), each with its
Jeffreys 95% interval. An inversion (the riskier grade has the lower realised rate) where the two
intervals do not overlap is a FAIL; an inversion inside overlapping intervals is Amber. A grade
with no `oot` loans is skipped and the comparison runs to the next grade.
Result: PASS (run of 2026-09-25, scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`; out-of-time scored once, 2026-09-24T23:57:05Z). Realised `oot` default rates (Jeffreys): A 0.0008 [0.0006, 0.0010]
n 102,921; B 0.0019 [0.0015, 0.0023] n 57,575; C 0.0043 [0.0037, 0.0049] n 45,140; D 0.0071
[0.0062, 0.0082] n 28,098; E 0.0105 [0.0090, 0.0121] n 15,944; F 0.0164 [0.0136, 0.0197] n 6,645;
G 0.0184 [0.0132, 0.0249] n 2,014. No inversion; no grade was merged on `dev_train`.

### S4. Calibration by grade
For each grade, the mean predicted `pd_12m` lies inside the Jeffreys 95% interval of that
grade's realised default rate. Tested on `dev_test` (S4a) and `oot` (S4b). PASS only if every
grade passes; a grade with fewer than 20 events reports "insufficient events" instead of pass or
fail.

Expectation, stated now, and **known in advance** from the Appendix A counts (so S4b is not
blind): the development period includes the crisis, so its average default rate (about 0.76%)
is higher than the out-of-time sample's (about 0.46% for the 2017, 2018 and 2022-2024
vintages). A scorecard calibrated on development is therefore expected to **over-predict** out
of time, and S4b may fail for that reason alone. If it does, it is reported as a FAIL. The
calibration-in-the-large ratio (realised over mean predicted PD) and its interval (section 4
table) are published for `dev_test`, `oot` and `covid` under both D1 and D2 (D2 secondary). The
scorecard is **not** recalibrated on out-of-time data. The provisioning PD comes from L2, which
conditions on the reporting date; it is not the scorecard's intercept.
Result S4a: FAIL (run of 2026-09-25, scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`; out-of-time scored once, 2026-09-24T23:57:05Z). Six grades pass; grade C fails: mean PD 0.0028 against a realised
0.0022 [0.0017, 0.0027], n 33,480. Calibration in the large on `dev_test`: realised over mean
PD 0.975 [0.912, 1.041].
Result S4b: FAIL. Six of seven grades fail; only E passes. The scorecard under-predicts the
low-risk grades (A: mean PD 0.0005, realised 0.0008 [0.0006, 0.0010]; B 0.0014 vs 0.0019
[0.0015, 0.0023]; C 0.0028 vs 0.0043 [0.0037, 0.0049]; D 0.0055 vs 0.0071 [0.0062, 0.0082]) and
over-predicts the high-risk ones (F 0.0221 vs 0.0164 [0.0136, 0.0197]; G 0.0448 vs 0.0184
[0.0132, 0.0249]); E 0.0111 vs 0.0105 [0.0090, 0.0121] passes. Calibration in the large on
`oot`: 1.076 [1.007, 1.148] (D2: 1.526 [1.444, 1.612]). The over-prediction expected above did
not happen overall; the expectation rested on Appendix A counts that overstate the development
default rate (see Deviations, 2026-09-25, item 4).

### S5. Population stability
PSI of the score, `dev_train` against `oot`, on the ten `dev_train` score deciles (empty bins
take 0.0001). **Below 0.10 stable; 0.10 to 0.25 Amber; above 0.25 Red (FAIL)**. Decile edges
are `numpy.quantile(dev_train_scores, [0.1, ..., 0.9], method="inverted_cdf")`; the bins are
`score <= e1`, `e1 < score <= e2`, ..., `score > e9`. Scores are integers, so edges can
repeat; repeated edges are dropped and PSI is computed on the remaining bins, whose number is
published. CSI for every model feature, on that feature's final scorecard bins (the missing bin
included), on the same thresholds, reported and flagged, with no separate pass or fail. PSI of
each origination year against `dev_train`, descriptive. Expectation, stated now: post-2009
underwriting is tighter than 1999-2008, so the FICO and DTI distributions will have shifted and
a Red PSI is plausible. That would be a finding about the population, not a coding error, and it
would not trigger a model rebuild.
Result: PASS, green (run of 2026-09-25, scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`; out-of-time scored once, 2026-09-24T23:57:05Z). Score PSI `dev_train` against `oot` 0.0446 [0.0426, 0.0467] on 10
bins. CSI (flagged, no pass or fail): `fico` 0.062 green, `ltv_pct` 0.199 amber, `dti_pct` 0.654
red, `rate_spread_pct` 0.117 amber, `term_band` 0.182 amber, `property_type` 0.115 amber,
`channel` 2.750 red (Freddie Mac's `T`, third party not specified, covers 31% of `dev_train`
and no out-of-time loan; see `docs/PD_MODELS.md`). PSI by origination year is red for 2010,
2011 and 2012 (0.42 to 0.59) and amber for seven other years.

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
Each rule's result (rows checked, rows outside tolerance, largest difference) is published:
R1-R4, R7 and R8 in `portfolio.json`, R5 and R6 in `lgd_ead.json`.
Result: pending

---

## 5. Challenger (LightGBM with SHAP)

Built on the same candidate features as the scorecard (raw values, not WoE), with the same
fairness and leakage exclusions, and with LightGBM monotone constraints matching the expected
directions for the numeric features. Hyperparameters are chosen by five-fold cross-validation on
`dev_train` only; `dev_test` is used once to confirm; `oot` is scored once, in the same call as
the champion.

Fixed now: folds stratified by outcome, shuffled with seed `20260923`; objective `binary`,
`learning_rate=0.05`, `feature_fraction=0.8`, `bagging_fraction=0.8`, `bagging_freq=1`,
`seed=20260923`, `deterministic=true`, up to 2,000 rounds with early stopping after 50 rounds
without improvement in fold AUC; grid `num_leaves` in {15, 31}, `min_child_samples` in {200,
1000}, `lambda_l2` in {0, 10}. The chosen setting has the highest mean fold AUC; ties go to
fewer leaves, then more `min_child_samples`, then more `lambda_l2`. The final model is refitted
on all of `dev_train` with the mean best round count. **Confirm step**: the challenger's
`dev_test` AUC must be no more than 0.02 below its mean fold AUC. If it is lower, the challenger
is not re-tuned; it is frozen as it is, still scored on `oot` in the same call, all its results
are published, and C1 is recorded as FAIL (overfit at the confirm step) whatever the `oot`
numbers.

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
Result: FAIL, not recommended for promotion (run of 2026-09-25, scorecard `scorecard-5abfae854ca0`, challenger `lgbm-3482af42e41c`; out-of-time scored once, 2026-09-24T23:57:05Z). Confirm step passed (`dev_test` AUC
0.8688 against a mean fold AUC of 0.8720). Criterion 1 not met: the `oot` Gini gain is -0.0124
[-0.0249, -0.0001] (paired bootstrap_1000), so the challenger is worse out of time. Criteria 2
(calibration fails in 6 grades, the same as the champion), 3 (score PSI 0.0429) and 4 (SHAP for
every `oot` and `covid` loan, every monotone constraint holds) are met. The scorecard stays the
model used downstream.

---

## 6. Lifetime PD

### L1. Competing-risk hazard (term structure and prepayment)

A discrete-time multinomial logit on loan-months. Outcomes are {stay, default, prepay}. Default
is D1, first occurrence; prepayment is D5. Codes 16 and 96 and the data cut-off censor.

- **Risk set**: active loans that have not yet had their first default, `months_on_book` 1 or
  more, whatever their
  current delinquency. Excluding delinquent loans would remove almost every path to default.
- **Covariates**: scorecard grade (7 levels); loan-age band (`months_on_book` 1-12, 13-24,
  25-36, 37-60, 61-120, 121+, piecewise constant, which gives the seasoning curve); rate
  incentive band (current note rate minus the market rate: below -0.5, -0.5 to 0.5, 0.5 to 1.5,
  above 1.5 percentage points). The incentive is there because prepayment is driven by
  refinancing, and without it every refinancing boom (2003, 2012, 2020-21) would be missed.
  Main effects only. Stretch: the macro covariate in E6.
- **Market rate** (`dim_date.market_rate_pct`): the median `note_rate_pct` of sample loans with
  an original term over 240 months whose **first payment month** is that month. First payment
  usually comes about two months after the note rate is locked, so this lags the market by about
  two months (stated). The sample has no loans with a first payment after early 2026, so for any
  month with no such loan the last available value is **carried forward**
  (`market_rate_carried_forward` marks those months, and their count is published). Months
  before the first available value (the start of 1999) have no market rate; their loan-months
  take the middle incentive band (-0.5 to 0.5), and their count is reported.
- **Estimation**: counts aggregated in the warehouse by covariate cell, then fitted by maximum
  likelihood with frequency weights, which gives exactly the loan-level estimate.
- **Projection**: the rate incentive is held at its reporting-date value. Prepayment is a
  competing risk throughout, so a loan that prepays cannot default later. Lifetime PD is the sum
  of marginal default probabilities, never one minus the product of default-only survival.

L1a. Diagnostic: predicted against realised 12-month prepayment rate by grade at the held-out
year-ends (2016-12 to 2024-12, `prepaid_next_12m`), published in `ecl.json`. Described, not a
pass rule. The model has no house-price or burnout effect on
prepayment, a stated limitation.
Result: pending

### L2. Behavioural 12-month PD (first year and SICR)

A logistic regression on loan-quarter rows (`fct_stage_inputs`) for loans that have **never
had a primary default** by the reporting date, target `default_next_12m` (the loan's first
primary default within the next 12 months).

**Cured loans are outside the model population.** A loan that defaulted and then cured (D4) is
not in default, but it can no longer have a *first* default, so `default_next_12m` is null for
it and it is left out of the L2 fit and the E3 backtest. It still sits in the book, in stage 2
while on cure probation and in stage 1 or 2 after that, and it still needs an ECL. It gets the
L2 PD for its current grade, age band and behaviour state, which extrapolates the model to a
population it was not fitted on (re-default risk after a cure is likely higher). The number of
these loans, their exposure and their ECL are published at every reporting date
(`fct_stage_inputs.defaulted_before`), so the size of the extrapolation is visible.

Covariates: grade; loan-age band; behaviour state (`clean`, `recent_dpd` = current but 30+ days
past due at some point in the previous 12 months, `dpd_30`, `dpd_60p` = 60-89 days past due or
90+ and exempt under D3); `modified`. Stretch: the macro covariate in E6.

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

- **No probation from stage 2 to stage 1.** A loan returns to stage 1 at the first reporting
  date where no stage 2 rule holds. The only probation is the six months after a cure (stage 3
  to 2). The cure month itself is not in default (D4).
- **What the PD rule adds.** In the minimum build (no macro covariate) L2's inputs are grade,
  age band, behaviour state and `modified`, and with the reference at the same grade and age,
  the ratio test reduces in practice to "30+ days past due in the last 12 months, or modified".
  Most of that is already caught by the dbt rules. The share of stage 2 loans that are there
  only because of the PD rule is published at every reporting date, next to the share from each
  dbt rule.

### E2. ECL

- **Stage 1**: 12-month ECL = sum over months 1 to 12 of marginal PD x LGD x EAD(t) x
  discount factor.
- **Stage 2**: the same sum over the remaining contractual term (lifetime ECL).
- **Stage 3**: PD = 1, ECL = LGD x current exposure. Time spent in default does not change the
  LGD (stated).
- **LGD** is the `lgd_economic` segment mean by origination LTV band (G1), estimated on every
  resolved primary default in the LGD sample (P4). The G2 model is used instead only if it
  passes G2.
- **Discounting** is monthly at the original note rate (the effective interest rate, also for
  modified loans that were not derecognised).
- **Outputs**: ECL by stage and grade, coverage ratio (ECL over exposure), stage mix and stage
  migration matrices, every quarter-end. Dates inside a fitting window are labelled in-sample.

### E3. ECL backtest

At each held-out year-end from 2016-12 to 2024-12, for Stage 1 and Stage 2 loans by grade:
predicted = mean `PD12`, realised = share with `default_next_12m` (the L2 population: loans
with no earlier primary default). Each grade gets a colour:
- **Green**: realised rate inside the binomial interval around predicted: the 2.5% and 97.5%
  quantiles of `Binomial(n, predicted) / n`.
- **Amber**: outside that, but inside the 2.5% and 97.5% quantiles of the Vasicek one-factor
  distribution of the default rate, `P(rate <= x) = N((sqrt(1 - rho) * G(x) - G(PD)) / sqrt(rho))`
  with `PD` = predicted and `rho` = 0.15. This is the infinitely granular limit and ignores `n`
  (stated); mortgage defaults are correlated, so independent-binomial intervals are too narrow
  on their own.
- **Red**: outside both.

The realised rate is also published with its Jeffreys interval.

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
and not reported alone. The share of primary defaults in each resolution (D8) is reported by
default year, and the two LGD sensitivities in D8 are published next to the overall estimate.

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
- **PD**: the long-run average by grade. For each year-end reporting date from 1999-12 to
  2015-12 (17 dates, so it includes the crisis), the annual rate of a grade is the share of
  its `fct_stage_inputs` rows with `default_next_12m` true, among rows where it is not null
  (loans with no earlier primary default). The long-run PD is the simple mean of those annual
  rates (each year weighted equally; a year with no loans in the grade is skipped), floored at
  0.05%. Its interval is the t interval of that mean over the years used.
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
| The C1 challenger fails its `dev_test` confirm step | No re-tuning; it is still scored once with the champion and C1 is recorded as FAIL (section 5) |
| A binning fails (solver status, a single bin, or non-monotonic WoE) | The feature is dropped, never flipped (section 3) |
| A grade fails the size rule on `dev_train` | Merged by the mechanical rule in section 3 |
| A published cell would describe fewer than 10 loans | Merged or suppressed, and the output says which (section 12) |
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

## 12. Publication rules

The repository and its outputs are public. The data licence position is recorded in
`docs/DATA_LICENCE.md`; these rules follow from it and bind every published output (artefact
JSON, dashboard data file, website, workbook, README, report and this plan):
- **Aggregates only.** No loan-level row and no loan identifier is ever published or committed.
  The loan-level marts and model outputs stay under `VINTAGE_DATA_ROOT`, outside the
  repository. Fixtures are synthetic.
- **At least 10 loans per cell.** No published table cell, chart point or artefact value may
  describe fewer than 10 loans (for a rate, the loans in its denominator; for a loan-month rate,
  the distinct loans behind it). A smaller cell is merged into a neighbouring segment or
  suppressed, and the output says which: a suppressed value is null with a stated reason, and
  every artefact counts its suppressed cells.
- **Non-commercial**, and **Freddie Mac is credited** as the source wherever results are shown.

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
exclusion. The out-of-time sample as first written (2017-2019 and 2022-2024 by vintage): 1,299
in 300,000 (0.43%). Under the loan-level COVID rule in P1 it is essentially the 2017, 2018 and
2022-2024 vintages: 1,149 in 250,000 (0.46%), plus a few early-2019 and late-2021 loans. That
last figure is arithmetic on this table; no new query was run for it.

Flag coverage by reporting year: `borrower_assistance_plan` and `delinquency_due_to_disaster`
are empty before 2014 (as the user guide says). The estimated current LTV (`eltv`) is empty
before 2017, so it cannot be used in any model that is fitted on the crisis. It is carried in
the marts for description only.

---

## Appendix B. Every query on the real data before the freeze

| Query | What it computed | Outcome information |
|---|---|---|
| `scripts/presizing/q1.py` | Period and loan-age ranges; flag, ELTV, deferral and modification coverage by reporting year; distinct flag values | None |
| `scripts/presizing/q2.py` | Per vintage: loans, 12-month defaults under D2 and D1 + D3, 24-month defaults under D1 + D3, loans censored before 12 months, 12-month prepayments, 12-month code 16/96 exits (Appendix A) | Yes: default and prepayment counts for every vintage, including 2016+ |
| `scripts/presizing/q3.py` | Distinct values and counts of origination fields (amortisation, interest-only, HARP, channel and so on); sentinel counts | None |
| `docs/DATA_PROFILE.md` (its own script, `scripts/profile_data.py`) | How loans end by vintage, delinquency distribution, loss-field and flag coverage | Yes: exit types by vintage |
| An independent review of this plan (three aggregate queries) | Credit-event exits (codes 02, 03, 09, 15) by code and by year: counts with a null actual loss, null net sales proceeds and null removal UPB, and whether an underwriting defect settlement date is set; the last reporting month | Exit counts only; no default rates, scores or losses |

The three `q` scripts are committed as they were run, except that the data path is read from
`VINTAGE_DATA_ROOT` and the imports are split. Their output is in
`scripts/presizing/outputs.txt` (re-run on 2026-09-24, before the freeze, with the same result
as before the plan was written; counts from 1 to 9 replaced by `<10`, section 12). SHA-256 of the
committed files (LF line endings):

| File | SHA-256 |
|---|---|
| `scripts/presizing/q1.py` | `47f2de85020d972427e879ab6a06d5ea5ba4112055aa23cc2be78c1f32518ccf` |
| `scripts/presizing/q2.py` | `e9622b29e5238201580cd3c6d0b41121e762aa19058f16f76dd4d33b6d67b8a6` |
| `scripts/presizing/q3.py` | `55dd73eba5d5dd7a20012c8856d0590bbd18b7e047b5d4a31e70c87fa47ae92d` |
| `scripts/presizing/outputs.txt` | `dc5ff05077656d3a93abdbaefbc08d997d9b7a880b84fd4be5cffde3169247a9` |

---

## Deviations

Each entry gives the date, the rule, what changed, why, and the result under both the
original and the changed rule.

### 2026-09-25, the scorecard run on the real data

No rule was changed and nothing was rescored: the out-of-time and COVID samples were scored once
(2026-09-24T23:57:05Z, one line in the scoring log). Every binning solver ended `OPTIMAL`, so the
600-second limit was never reached. The entries below record interpretations and a correction.

1. **Section 4, bootstrap intervals that exclude their estimate.** A percentile bootstrap
   interval can miss its own point estimate for a statistic that resampling biases (PSI near
   zero, sometimes KS). The contract does not allow a published interval that excludes its
   value. Handling: the value is published, `ci_low` and `ci_high` are null, and the computed
   percentile bounds and the reason are written in `ci_method`; nothing is recomputed with
   another method. Result under the original and the changed rule: identical on the real data,
   because no published AUC, Gini, KS, Gini drop, PSI or CSI interval excluded its estimate
   (zero cases in `pd_models.json` and `monitoring.json`).
2. **S-method Binning, WoE sign remark.** The plan says the WoE convention is "the opposite
   sign to optbinning's own". In optbinning 1.0.0 the binning table already uses
   ln(non-default share / default share), the plan's formula, so no sign change is applied. The
   code follows the formula (computed once, and tested equal to optbinning's table). A factual
   correction to a remark; no effect on any result.
3. **Cases the plan does not define** (engine interpretations, documented in
   `docs/PD_MODELS.md`): S3 and S4 report `INSUFFICIENT` when too few grades or events remain
   (no primary `oot` grade had fewer than 20 defaults, so this did not arise for S3, S4a or S4b);
   D1a above 10% would be reported AMBER (it was 4.0%); a category unseen in `dev_train` is
   scored in the grouped rare-category bin, else the missing bin (no out-of-time category was
   unseen); a reason-code slot is empty when the feature is already at its maximum points; the
   fairness Gini with and without a feature uses a logistic refit's unrounded linear predictor;
   PSI by origination year uses every loan of that year in the scorecard population; the
   2017-2019 and 2022-2024 out-of-time views filter `oot` by vintage year, so the 7,941
   `oot` loans of the 2021 vintage (first payment in 2022) are in neither window. Results were
   not computed under any alternative.
4. **Appendix A overstates the development default rate, so the S4 expectation was wrong.**
   Appendix A counted defaults by Freddie Mac's `loan_age`, which restarts at a modification's
   first payment date (the reason D0 does not use it), so a modified loan that defaulted years
   later could count as a 12-month default. Under D0 the development rate is 0.39% (`dev_train`
   2,101 of 539,519 loans, Wilson 95% [0.37%, 0.41%]), not about 0.76%. The difference was found
   when the development binning was first run, and checked with one aggregate query on the
   raw Parquet for three development vintages only (no 2016+ vintage): 12-month primary
   defaults by `loan_age` against months on book, before the HARP exclusion, were 571 against
   186 (2005), 1,214 against 556 (2007) and 121 against 59 (2015). The S4b sentence "expected
   to over-predict out of time" therefore rested on inflated counts; S4b is still reported
   exactly as the rule says (FAIL), and the out-of-time sample holds fewer defaults than sized.
   No rule, threshold or sample changed.

