# Model validation report: PD scorecard and IFRS 9 / Ind AS 109 loss engine

**Models.** Application PD scorecard `scorecard-5abfae854ca0` (WoE logistic, seven grades A-G) and
its LightGBM challenger; the loss engine (realised LGD and EAD, the G2 two-stage LGD model, L1
competing-risk hazard, L2 behavioural 12-month PD, E1 staging, E2 lifetime ECL with three
house-price scenarios, illustrative Basel IRB capital).
**Data.** Freddie Mac Single-Family Loan-Level Dataset, sample files, performance to 2026-03.
**Sources.** `artefacts/*.json` as committed; `VALIDATION_PLAN.md` (frozen before any result);
`docs/PD_MODELS.md`, `docs/LOSS_AND_ECL.md`, `docs/RECONCILIATION.md`; the independent review of
2026-09-28. Issues are numbered as in `docs/VALIDATION_ISSUES.md`.

All intervals are 95%. Every number here is read from the artefacts;
`tests/test_validation_docs.py` checks each one.

## 1. Decision

**Fit for publication as a research and portfolio project. Not fit for use as a production
origination PD, SICR rule or provisioning model.**

The pre-registration held. The out-of-time sample was scored once (`pd_models.json`
`oot_scoring`), the pass rules were not edited after the plan was frozen, and every failure is
reported as a failure. Of the eight scorecard rules, four pass (D1a, S1, S3, S5), one is Amber
(S2) and three fail (S4a, S4b, C1). All seven loss-engine rules pass (E3, E4a-c, R5, R6, G2), and
one of the six reconciliation rules fails (R1, five loans).

Three results block production use:
1. The scorecard PD is not calibrated out of time: six of seven grades fail (V-14).
2. Stage 2 is driven mostly by a mismatch in how the house-price covariate is defined on the two
   sides of the SICR test, and the size of that effect is not measured (V-05).
3. The ECL interval covers parameter uncertainty only and is far too narrow; the scenario range
   is the more honest spread (V-08).

## 2. Scope

In scope: the scorecard and challenger (S1-S5, C1, D1a), LGD/EAD (R5, R6, G1, G2), lifetime PD
(L1-L3), staging and ECL (E1-E4), the backtest (E3), capital (illustrative) and the
reconciliation of the marts to raw data (R1-R8).

Out of scope: the website and Power BI presentation layers (checked only for wording, V-01 and
V-02), code review line by line, and reproducibility from a clean environment.

## 3. Conceptual soundness

- **Default definition.** Primary default (D1) is 90+ days past due or a credit event, with COVID
  forbearance exempted (D3). The choice matters: under the naive definition the out-of-time
  calibration ratio is 1.526 [1.444, 1.612] against 1.076 [1.007, 1.148] under D1, and the COVID
  sample's ratio is 5.94 against 0.753. The exemption is a definitional choice about what counts
  as default, and results under D1 should be read that way. Modifications before or without a
  primary default are 4.0% of primary defaults (D1a PASS).
- **Scorecard design.** WoE binning is monotonic in the expected direction for all four numeric
  features (S1 PASS). `number_of_borrowers` is excluded as a marital-status proxy although it has
  information value; that cost is measured and disclosed.
- **Era marker.** Channel code `T` exists only in vintages to 2008 and gets the riskiest channel
  WoE. The scorecard partly learns the crisis era through it (V-09).
- **SICR.** The rule (PD12 ratio of at least 2.0 and an absolute rise of at least 0.20 points, plus
  a 30-days-past-due backstop and forbearance flags) is standard in form. Its inputs are not
  consistent: the current PD uses a forward mean of house-price growth and the reference PD a spot
  value (V-05). This is the main conceptual weakness.
- **Scenarios.** Three national house-price paths weighted 60/25/15, with the adverse path a
  replay of 2007-11. This is a historical replay, not a forecast, and it adds hindsight at
  historical dates (V-06).
- **Cured loans.** Re-default risk after a cure is extrapolated from an L2 model fitted without
  cured loans (V-13).

## 4. Data

- Reconciliation passes R2-R8. R1 fails by 5 loans out of 1,350,000, a documented join exclusion
  (V-18).
- Development default rate (`dev_train`, 1999-2015 vintages) 0.39% [0.37, 0.41]; out of time
  (2017-2024 outside the COVID window) 0.35% [0.32, 0.37], n 258,337.
- Pre-registration discipline held; one pre-freeze sizing query on development vintages only is
  disclosed in the plan's Deviations.
- Only purchased, conforming, fixed-rate first-lien loans: there is no reject inference, and the
  population is US.

## 5. Out-of-time performance

| Sample | Gini [95%] | n loans |
|---|---|---|
| `dev_test` (in time) | 0.7109 [0.6855, 0.7354] | 231,384 |
| `oot` (2017-2024, outside COVID) | 0.5336 [0.5055, 0.5625] | 258,337 |
| `oot`, 2017-2019 vintages | 0.5054 [0.4441, 0.5727] | 100,909 |
| `oot`, 2022-2024 vintages | 0.5327 [0.4995, 0.5679] | 149,487 |
| `covid` | 0.3191 [0.2455, 0.3883] | 138,385 |

- **S2 AMBER.** Relative Gini drop 0.2494 [0.2010, 0.2951], just below Red; the interval crosses
  it (V-15).
- **S3 PASS.** The realised out-of-time default rate rises through every grade, from A 0.08%
  [0.06, 0.10] to G 1.84% [1.32, 2.49]. Ranking survives; the spread does not.
- **C1 FAIL.** The challenger's out-of-time Gini is 0.5212 [0.4934, 0.5509]; its paired gain over
  the scorecard is -0.0124 [-0.0249, -0.0001]. It is not promoted (V-17).

The scorecard still ranks risk out of time, but with materially less separation than in
development. This does not establish how it ranks applicants Freddie Mac did not buy.

## 6. Calibration

Calibration in the large (realised over mean predicted PD):

| Sample | Ratio [95%] |
|---|---|
| `dev_test` | 0.975 [0.912, 1.041] |
| `oot` | 1.076 [1.007, 1.148] |
| `oot`, 2017-2019 | 0.680 [0.592, 0.778] |
| `oot`, 2022-2024 | 1.326 [1.229, 1.428] |
| `covid` | 0.753 [0.663, 0.853] |

- **S4a FAIL** (in time): grade C only, a marginal miss (V-16).
- **S4b FAIL** (out of time): six of seven grades. The level is close overall; the slope is wrong.
  Low grades are under-predicted and high grades over-predicted (G: mean PD 4.48% against realised
  1.84% [1.32, 2.49]). The two windows err in opposite directions, so one recalibration would not
  fix both (V-14, V-12).

The scorecard PD should not be used as a point-in-time PD. Provisioning uses L2, not the
scorecard PD, which limits the damage to the ECL.

## 7. Stability

- **S5 PASS** on the score: PSI `dev_train` to `oot` 0.0446 [0.0426, 0.0467].
- The inputs are not stable. CSI is red for `channel` (2.75) and `dti_pct` (0.654), and amber for
  `ltv_pct` (0.199), `term_band` (0.182), `rate_spread_pct` (0.117) and `property_type` (0.115).
  Origination-year PSI is red for 2010-2012 (0.420 to 0.593). A green score PSI here hides
  offsetting feature shifts (V-02).

## 8. LGD, EAD and ECL

- **LGD.** Realised economic LGD 0.249 [0.246, 0.252], n 35,688 resolved primary defaults. R5 and
  R6 reconcile every event to within $1. G2 passes (MAE difference -0.0134 [-0.0150, -0.0116] on
  16,168 held-out defaults), so ECL uses the two-stage model. Adding the zero-loss exclusions
  lowers LGD to 0.197 [0.195, 0.200]; this is not carried into ECL (V-13).
- **EAD.** Mean EAD at default $171,862 [170,894, 172,761], n 54,615; no CCF applied.
- **ECL at 2026-03.** $272.4m [269.6, 275.0] on exposure of $80.0bn (342,587 loans). Stage 1
  $41.0m (292,874 loans), stage 2 $124.3m (46,668), stage 3 $107.1m (3,045); stage figures are
  point estimates. Single scenarios: base $261.5m [259.0, 263.9], adverse $320.4m [316.9, 323.8],
  upside $235.7m [233.2, 238.1]. The interval is parameter uncertainty only (V-08).
- **Stage-2 driver.** The PD rule alone places 89.7% [89.4, 90.0] of stage-2 loans at 2026-03 and
  92.7% at 2023-03 (V-05).
- **Backtest (E3 PASS, biased).** No Red cell; 4 Green and 45 Amber of 49 counted grade-dates;
  over-prediction in 48 of 49; pooled predicted 0.766% against realised 0.529% on 2,008,959
  loan-dates. The pass reflects a wide band, not calibration (V-03, V-20).
- **Mechanics (E4a-c PASS).** Hand-worked loans match to the cent; staging edge cases behave as
  specified; marginal default, prepayment and survival sum to 1 over 30 years.
- **Capital (illustrative).** Non-defaulted exposure $79.27bn: RWA $31.45bn and capital $2.516bn
  against a stage 1-2 ECL of $165.3m [162.6, 167.9]. No regulatory scaling or output floor.

The ECL is likely conservative outside a crisis (the backtest over-predicts) and it rose late
into 2008 (V-06). It is not an audited or regulatory provision.

## 9. Limitations

- Intervals: ECL intervals exclude scenario, staging, model and LGD uncertainty (V-08); roll and
  cure rate intervals treat loan-months as independent (V-07).
- Hindsight in the historical ECL series (V-06).
- No reject inference; US conforming mortgages only. The methods map to Ind AS 109; the numbers
  do not transfer.
- One out-of-time period; no benchmark model beyond the challenger.
- Macro scenarios are one national index with fixed weights, not an economic forecast.
- LGD uses origination attributes only; current LTV and MI counterparty risk are not modelled.

## 10. What a production candidate would need

1. A recalibrated PD on recent vintages, or a PIT/TTC layer, validated on a later period (V-14).
2. A redesigned SICR rule with consistent covariates, tested for stability and false positives
   against realised 12-month defaults (V-05).
3. A re-default hazard for cured loans; current-LTV LGD; MI counterparty risk (V-13).
4. `channel` remapped or dropped, refitted and pre-registered as a new model (V-09).
5. Loan-cluster intervals throughout and an overlay framework for model and scenario uncertainty
   (V-07, V-08).
6. Governed macro scenarios from an independent forecast; regional house-price indices.
7. Ongoing monitoring with triggers: CSI, S4 by quarter, and a base-path E3 backtest (V-03).
8. Independent code review, clean-environment reproducibility and data-lineage controls (V-18).
