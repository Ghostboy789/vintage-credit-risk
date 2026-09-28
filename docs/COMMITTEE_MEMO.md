# Credit committee memo: Vintage PD scorecard and ECL

**Decision requested: note the models as a research benchmark; do not approve them for
origination decisions, staging or provisioning.** The scorecard ranks risk out of time but is not
calibrated, and the ECL rests on a staging rule driven mostly by a national house-price covariate.

All intervals are 95%. Sources: `artefacts/*.json`; details in `docs/VALIDATION_REPORT.md` and the
issue ledger `docs/VALIDATION_ISSUES.md`.

## Headline numbers

| Measure | Result | Rule |
|---|---|---|
| Out-of-time Gini (2017-2024 originations, n 258,337) | 0.5336 [0.5055, 0.5625], down from 0.7109 in time | S2 AMBER |
| Out-of-time calibration by grade | Six of seven grades fail; overall ratio 1.076 [1.007, 1.148] | S4b FAIL |
| Score stability (PSI) | 0.0446 [0.0426, 0.0467]; but `channel` and DTI drift red | S5 PASS |
| Challenger (LightGBM) | Gini gain -0.0124 [-0.0249, -0.0001]; not promoted | C1 FAIL |
| ECL at 2026-03, probability-weighted | $272.4m [269.6, 275.0] on $80.0bn exposure | - |
| ECL range across single scenarios | $235.7m (upside) to $320.4m (adverse) | - |
| ECL backtest | No Red cell, but over-predicts in 48 of 49 grade-dates | E3 PASS |

Scorecard rules: four PASS, one AMBER, three FAIL. Loss-engine rules: all seven PASS.
Reconciliation: one FAIL (five loans).

## What the portfolio shows

- **Vintages.** The crisis vintages drive historical losses: the 2007 vintage reached a cumulative
  default rate of 14.41% [14.11, 14.72] by 72 months on book (n 50,000).
- **Segments.** Loss rate rises with origination LTV, from 0.11% [0.10, 0.12] of original balance
  at LTV up to 60 (n 321,605) to 1.05% [0.98, 1.12] above 95 (n 45,712).
- **Current book.** At 2026-03, stage 2 holds $124.3m of the ECL and 46,668 loans; 89.7%
  [89.4, 90.0] of those loans are there through the PD rule alone, not delinquency.

## Policy the evidence supports

Only one, and weakly: price or cap high-LTV origination. The LTV gradient is large and its
intervals are tight, but it is univariate, mortgage insurance is not netted, and it is not a
causal estimate. The scorecard should not set cut-offs until it is recalibrated.

## Limits, stated plainly

- The ECL interval covers parameter uncertainty only, about ±1%. The single-scenario range,
  $235.7m to $320.4m, is many times wider and is the better guide to uncertainty.
- The stage-2 rule is driven mostly by national house-price growth, not borrower behaviour:
  without it, stage 2 at 2026-03 holds 15,039 loans instead of 46,668 and the ECL is $228.2m, not
  $272.4m (point estimates). Defining it the same way on both sides moves far fewer loans
  (42,440 remain). This alone rules out using the ECL.
- The backtest pass comes from a wide band; the model over-predicts in benign years (pooled
  0.766% predicted against 0.529% realised) and reacted late in 2008.
- US conforming mortgages only, no reject inference, one out-of-time period. Not an audited or
  regulatory figure.

## Next steps

Redesign the stage-2 rule (one house-price definition on both sides, and a decision on whether a
house-price move alone should trigger stage 2); recalibrate the PD on recent vintages;
remap the `channel` era code; publish the scenario range beside every ECL figure.
