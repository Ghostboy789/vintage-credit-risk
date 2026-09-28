# Validation issues

The issue ledger for the PD scorecard and the loss/ECL engine. It combines the findings of the
independent review of 2026-09-28 (V-01 to V-13) with every pass rule that did not pass on the
real data (V-14 to V-18) and two documentation slips found while writing this ledger (V-19,
V-20). The report that goes with it is `docs/VALIDATION_REPORT.md`.

Every number below is read from the committed artefacts; `tests/test_validation_docs.py` checks
that each one is there. Evidence gives the artefact and key. Intervals are 95%.

**Severity.** High: the result cannot be relied on for its stated use without a fix. Medium: the
result stands, but the evidence is weaker than it looks or is described inconsistently. Low:
presentation, bookkeeping, or a disclosed limit with small effect.

**Status.** Fixed (commit named), Open, or Closed (no change needed, reason given).

## Summary

| ID | Severity | Finding | Status |
|---|---|---|---|
| V-01 | High | The site showed only in-time calibration and left out the three main caveats | Fixed (ab76eef) |
| V-02 | Medium | S5 label claimed the applicant population is stable | Fixed (ab76eef) |
| V-03 | Medium | E3 backtest PASS carries little information and is biased | Wording fixed (ab76eef); base-path backtest open |
| V-04 | Medium | Several FINDINGS.md claims were stronger than the evidence | Fixed (ab76eef) |
| V-05 | High | Stage 2 is driven by a house-price definition gap; the effect is not measured | Open |
| V-06 | Medium | The historical ECL series uses hindsight in LGD and the adverse path | Partly fixed (ab76eef); rerun open |
| V-07 | Medium | Some intervals treat repeated loan observations as independent | Open |
| V-08 | Medium | The ECL interval method is described two ways, and the interval is far too narrow | Open |
| V-09 | Medium | Channel code `T` marks the crisis era and stays in the scorecard | Open (next release) |
| V-10 | Low | An unsupported "2020 vintage is all retail" claim | Closed |
| V-11 | Low | Three different R3 figures | Open |
| V-12 | Low | The 2017-2019 out-of-time window is mostly 2017-18 | Open |
| V-13 | Low | Cured-loan PD is extrapolated; the D8a LGD effect is not carried into ECL | Open |
| V-14 | High | S4b FAIL: the PD is not calibrated out of time | Open (by design, no recalibration on out-of-time data) |
| V-15 | Medium | S2 AMBER: out-of-time Gini drop at the edge of Red | Open |
| V-16 | Low | S4a FAIL: one grade misses in time | Open (disclosed) |
| V-17 | Low | C1 FAIL: the challenger is not promoted | Closed (the rule worked as intended) |
| V-18 | Low | R1 FAIL: five loans short in the mart loan count | Open (explained) |
| V-19 | Low | LOSS_AND_ECL.md rounds two scenario interval bounds wrongly | Open |
| V-20 | Low | The E3 evidence string in the artefact omits the over-prediction count | Open |

No loss-engine pass rule failed: E3, E4a, E4b, E4c (`ecl.json`), R5, R6 and G2 (`lgd_ead.json`)
all pass. The weaknesses on the loss side are in V-03, V-05, V-06, V-08 and V-13.

## Entries

### V-01 · High · Fixed (ab76eef)
- **Finding.** The Scorecard page's PD ladder used `dev_test` rows only. The out-of-time
  calibration failure (S4b) appeared only as a badge. The site's "not established" list left out
  the three caveats that matter most: the PD is not calibrated out of time, the ECL intervals are
  too narrow, and the backtest is biased.
- **Evidence.** `pd_models.json` `calibration` (sample `oot`); `pass_rules` S4b.
- **Remediation.** Done: the ladder shows out-of-time calibration; the three caveats are on the
  Methods page; every `parameter_draws_1000` interval is labelled as parameter uncertainty only.

### V-02 · Medium · Fixed (ab76eef)
- **Finding.** The S5 label read "Applicant population is stable". Only the score PSI is green:
  CSI is red for `channel` (2.75) and `dti_pct` (0.654), and origination-year PSI is red for
  2010-2012 (0.420 to 0.593).
- **Evidence.** `monitoring.json` `csi`, `score_psi`.
- **Remediation.** Done: relabelled to name the score PSI and the feature drift.

### V-03 · Medium · Wording fixed (ab76eef); base-path backtest open
- **Finding.** E3 passes with no Red cell, but 4 of the 49 counted grade-dates are Green and 45
  Amber, and the model over-predicts in 48 of 49 (pooled predicted 0.766% against realised
  0.529%, 2,008,959 loan-dates). The Amber band is a Vasicek quantile with rho 0.15 that ignores
  sample size, so the test has little power. The predicted PD is probability-weighted and puts
  25% on a replay of the 2007-11 house-price path at every date, which builds part of the
  over-prediction into the test.
- **Evidence.** `ecl.json` `backtest` (non-COVID rows), `pass_rules` E3, `scenarios.weights`.
- **Remediation.** Done: the site badge, FINDINGS.md and the plan's result line now say the pass
  rests on a wide band. Open: a secondary backtest of the base-path (or realised house-price)
  PD12 against realised defaults. See V-20 for the artefact evidence string.

### V-04 · Medium · Fixed (ab76eef)
- **Finding.** FINDINGS.md overstated four claims: a prepayment benchmark that was not cited, the
  forbearance gap called a pure measurement artefact (and the 2017 vintage not named), a rounded
  "6-8x" crisis multiple, and LTV called the "strongest" loss driver when only LTV band and state
  were measured. LOSS_AND_ECL.md called COVID-era ECL over-provisioning without saying the
  realised defaults are counted under the forbearance-exempt definition.
- **Evidence.** `portfolio.json` `loss_drivers`, `default_definition_effect`.
- **Remediation.** Done: each claim softened or qualified in ab76eef.

### V-05 · High · Open
- **Finding.** The stage-2 PD rule compares `PD12_now`, which uses the mean house-price change
  over the next 12 months under each scenario, with `PD12_ref`, which uses the spot value at the
  first payment month. The two sides use different definitions of the same covariate. The PD rule
  alone puts 89.7% [89.4, 90.0] of stage-2 loans there at 2026-03 (41,855 of 46,668) and 92.7% at
  2023-03. Stage 2 is $124.3m of the $272.4m ECL at 2026-03 and $127.3m of $210.3m at 2023-03. How
  much of this the definition gap explains has not been measured.
- **Evidence.** `ecl.json` `stage2_drivers` (reason `pd_deterioration`), `by_date` (stage 2),
  `scenario_totals` (scenario `final`).
- **Remediation.** Rerun staging with `PD12_ref` on the same forward-mean definition, and again
  with the covariate removed from the reference. Report the change in stage-2 share and in ECL,
  and log both as deviations and sensitivities. Until then the SICR rule is not fit for any
  production use.

### V-06 · Medium · Partly fixed (ab76eef); rerun open
- **Finding.** The historical ECL series uses hindsight twice: the G2 LGD model is fitted on
  defaults to 2023-03 and applied at 2006-2011 dates, and the adverse scenario at 2007 dates is
  the path that actually followed. The narrative read the series as what the model would have
  provisioned at the time.
- **Evidence.** `ecl.json` `by_date` (`in_sample`), `lgd_ead.json` `lgd_model`.
- **Remediation.** Done: both hindsight sources are stated on the site. Open: rerun two dates
  (2007-06, 2008-12) with LGD fitted only on data available at each date.

### V-07 · Medium · Open
- **Finding.** Roll and cure rates use Wilson intervals on loan-month transitions (for example
  30 days past due, all periods: 37.8% [37.7, 37.9], n 899,910 transitions), which treats a
  loan's repeated months as independent. L1 discloses the same assumption; L2 is fitted on
  loan-quarters and does not.
- **Evidence.** `portfolio.json` `roll_cure_rates`.
- **Remediation.** Loan-cluster bootstrap, or label these intervals "treats transitions as
  independent; too narrow".

### V-08 · Medium · Open
- **Finding.** LOSS_AND_ECL.md "Intervals" says the draws include the LTV-band LGD means; its
  Results section says LGD is not drawn because G2 passed. The interval also leaves out scenario,
  staging, model and LGD uncertainty: $272.4m [269.6, 275.0] at 2026-03 is about ±1%, while the
  single-scenario totals alone run from $235.7m (upside) to $320.4m (adverse).
- **Evidence.** `ecl.json` `scenario_totals` at 2026-03.
- **Remediation.** Correct the Intervals paragraph. Publish the scenario range next to every
  headline ECL as the more honest spread.

### V-09 · Medium · Open (next release)
- **Finding.** Freddie Mac codes third-party loans `T` only in vintages to 2008, and in no
  out-of-time loan. The scorecard gives `T` its riskiest channel WoE, so part of `channel`'s weight
  records the crisis era. Its CSI is 2.75 (red) and it is the fourth SHAP feature of the
  challenger; it is a likely contributor to the S2 Amber (V-15), not tested causally.
- **Evidence.** `monitoring.json` `csi` (channel); `pd_models.json` `points_table` (channel),
  `challenger.shap_global`.
- **Remediation.** Map `T` to broker/correspondent or drop `channel` before the next fit, and
  report that model's out-of-time results as a new, separately pre-registered model.

### V-10 · Low · Closed
- **Finding.** A "2020 vintage is 100% retail channel" claim circulated during development. The
  scorecard mart does not support it.
- **Evidence.** A search of the committed docs, site source and Power BI files finds no copy of
  the claim.
- **Remediation.** None needed; nothing published carries it.

### V-11 · Low · Open
- **Finding.** FINDINGS.md section 6 and RECONCILIATION.md quote different R3 balance
  differences, and neither matches the artefact's largest per-month difference ($0.064). All pass.
- **Evidence.** `portfolio.json` `pass_rules` R3.
- **Remediation.** Use one figure and name what it measures (per-month maximum or whole-sum
  difference).

### V-12 · Low · Open
- **Finding.** The "2017-2019" out-of-time window (n 100,909) holds few 2019 loans, because most
  of that vintage falls in the COVID sample. Its calibration ratio, 0.680 [0.592, 0.778], is
  essentially a 2017-18 result.
- **Evidence.** `pd_models.json` `calibration_in_the_large` (sample `oot_2017_2019`).
- **Remediation.** Rename the window or state its composition wherever it is quoted.

### V-13 · Low · Open
- **Finding.** Cured loans (5,966 loans, $15.1m of ECL at 2026-03) get an L2 PD fitted without
  cured loans, so their re-default risk is an extrapolation (disclosed). Adding the zero-loss
  exclusions (D8a) lowers overall LGD from 0.249 [0.246, 0.252] to 0.197 [0.195, 0.200]; that
  sensitivity is not carried into ECL.
- **Evidence.** `ecl.json` `cured_population`; `lgd_ead.json` `lgd_segments` (overall),
  `sensitivities` (`zero_loss_exclusions`).
- **Remediation.** Report ECL under the D8a LGD as a sensitivity; estimate a re-default hazard
  for cured loans.

### V-14 · High · Open (by design)
- **Finding.** S4b FAIL. Out of time, six of seven grades fail calibration and only E passes. The
  failure is one of slope, not level: overall the ratio is 1.076 [1.007, 1.148], but grades A to D
  are under-predicted (A: mean PD 0.05%, realised 0.08% [0.06, 0.10]) and F and G over-predicted
  (G: mean PD 4.48%, realised 1.84% [1.32, 2.49]). The two windows pull in opposite directions:
  2017-2019 ratio 0.680 [0.592, 0.778], 2022-2024 ratio 1.326 [1.229, 1.428].
- **Evidence.** `pd_models.json` `pass_rules` S4b, `calibration` (sample `oot`),
  `calibration_in_the_large`.
- **Remediation.** None in this release: the plan forbids recalibrating on out-of-time data, and
  provisioning uses L2, not the scorecard PD. A production candidate needs a recalibration on
  recent vintages or a PIT/TTC layer, tested on a later period.

### V-15 · Medium · Open
- **Finding.** S2 AMBER. The out-of-time Gini is 0.5336 [0.5055, 0.5625] against 0.7109
  [0.6855, 0.7354] on `dev_test`, a relative drop of 0.2494 [0.2010, 0.2951]. The point estimate
  sits just under the Red line and the interval crosses it. Under the naive default definition
  the drop is 0.2711 and Red.
- **Evidence.** `pd_models.json` `gini_drop`, `discrimination`, `pass_rules` S2.
- **Remediation.** Treat as a finding, not as evidence of stability. Address V-09 and the
  `dti_pct` shift in the next fit; monitor Gini by quarter.

### V-16 · Low · Open (disclosed)
- **Finding.** S4a FAIL. In time, grade C's mean PD (0.28%) sits just above the upper bound of
  its realised rate, 0.22% [0.17, 0.27] (n 33,480). The other six grades pass. With seven grades
  each tested at 95%, one marginal miss is within chance, but the rule has no multiplicity
  allowance and the FAIL stands.
- **Evidence.** `pd_models.json` `pass_rules` S4a.
- **Remediation.** None; a future plan could pre-register a multiplicity allowance.

### V-17 · Low · Closed
- **Finding.** C1 FAIL. The LightGBM challenger is better in time but worse out of time: its
  out-of-time Gini gain is -0.0124 [-0.0249, -0.0001], against a required lower bound above +0.02.
- **Evidence.** `pd_models.json` `challenger`, `pass_rules` C1.
- **Remediation.** None: the rule did its job and the scorecard stays the model used downstream.

### V-18 · Low · Open (explained)
- **Finding.** R1 FAIL. Of 1,350,000 raw loans, the loan-count check finds one cell outside
  tolerance with a difference of 5 loans (tolerance 0). The cause is documented in
  RECONCILIATION.md and the FAIL is reported, not tuned away.
- **Evidence.** `portfolio.json` `pass_rules` R1, `reconciliation`.
- **Remediation.** Add a data-lineage control that reports excluded loans by reason at each join.

### V-19 · Low · Open
- **Finding.** LOSS_AND_ECL.md "Headline, 2026-03" rounds the upper bound of the base scenario and
  the lower bound of the upside scenario 0.1 too high. The artefact values are base $261.5m
  [259.0, 263.9] and upside $235.7m [233.2, 238.1].
- **Evidence.** `ecl.json` `scenario_totals` at 2026-03.
- **Remediation.** Correct the two bounds.

### V-20 · Low · Open
- **Finding.** The E3 evidence string in `ecl.json` lists only "no Red" by date. It does not carry
  the over-prediction count (48 of 49) that the docs and site now state (V-03).
- **Evidence.** `ecl.json` `pass_rules` E3.
- **Remediation.** Add the Green/Amber counts and the over-prediction count to the evidence string
  at the next loss run. No rerun is needed for the numbers themselves.
