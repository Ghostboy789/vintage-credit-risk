# PD models

The application scorecard (champion), its LightGBM challenger, and how they are validated.
Rules are defined in `VALIDATION_PLAN.md` (sections 2 to 5) and referenced here by ID; this file
says how the code in `models/pd/` implements them and where it had to interpret them.

**Status: engine built and tested on synthetic fixtures only. No result on the Freddie Mac data
exists yet.** Every pass rule in `VALIDATION_PLAN.md` is still `pending`. The results section
below is filled in when the engine is run on the real `fct_scorecard_base`.

## Running it

```
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

## Not in the artefact

The plan's secondary out-of-time breakdowns (2017-2019 and 2022-2024) have no place in the
`pd_models.json` contract, whose sample values are fixed. They need a contract change or a
separate table.

## Results

Pending: to be filled from the run on the real data, with every number's interval and the
PASS/FAIL next to each rule in `VALIDATION_PLAN.md`.

## What this does not establish

As `VALIDATION_PLAN.md` section 11: no reject inference (approved, conforming Freddie Mac loans
only); US loans, not Indian ones; associations, not causal effects; not a production PD (the
1999-2015 development PD is labelled as such wherever it is shown, and the provisioning PD is L2);
not a fair-lending review.
