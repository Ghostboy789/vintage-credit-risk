# dbt reconciliation

Every number in this file comes from an actual test run, dated 2026-09-24. Nothing here is
estimated or invented.

## Status: verified on the "ci" target (DuckDB, synthetic fixtures). Real-data ("bq") run is
## blocked -- see "Real BigQuery build" below.

## R1-R8, on the CI build

R1-R8 are hard-stop tests (VALIDATION_PLAN.md section 4): nothing downstream is published until
they pass. `tests/test_dbt.py` builds the whole project on the `ci` target (DuckDB, the four
synthetic fixture vintages 2005/2007/2019/2022) and checks:

| Rule | What | Result on ci |
|---|---|---|
| R1/R2 | Loan and loan-month counts, mart against the extractor's own Parquet | Same source data on both sides by construction (the ci target reads the extractor's Parquet directly via `external_location`); `test_mart_has_rows_and_unique_keys` confirms every mart is non-empty with unique keys |
| R3 | Sum of `current_upb` per month, mart against Parquet | Same source; `test_no_negative_balances` additionally confirms no balance is negative |
| R4-R6 | Loss-field reconciliation (`fct_loss_events` against Freddie's `actual_loss`) | Not separately re-derived outside dbt in this project; `int_loss_events.sql`'s `computed_loss` formula is D8's own formula, so this is really a unit-style check that the formula was implemented correctly, done in `tests/test_dbt.py` and by hand against the fixture's known loss rows (see "Spot checks" below) |
| R7 | MetricFlow metrics against `metrics_monthly` | `test_metrics_match_metrics_monthly` recomputes `active_loans`, `total_upb`, `delinquency_rate_30p`'s numerator, `delinquency_rate_90p`'s numerator, `default_rate`'s numerator and denominator directly in SQL from the same measure expressions used in `models/semantic/_semantic.yml`, and checks every value against `metrics_monthly` for every month in the ci build: **all match, 0 mismatches**, across 206 months |
| R8 | Every artefact count against its mart | Not run here -- no artefact producer has run yet (portfolio.json etc. are produced by later steps in this project) |

`test_exported_marts_pass_contracts` exports every mart from the ci build through
`scripts/export_marts.py`'s DuckDB path and checks each one against `tests/contracts.py`: types,
keys, enums, nullability. All 11 marts pass with zero problems.

Bugs this caught before they reached a downstream consumer (fixed, not worked around):
- Six places where a boolean built from `x = 'value'` or `x IN (...)` on a nullable raw field
  (e.g. `super_conforming`, `forbearance_flag`, `default_trigger`, `is_first_default_month`)
  silently produced NULL instead of FALSE when the raw field was itself NULL -- SQL's
  three-valued logic, not a typo, but CONTRACTS.md marks all of these not-null. Fixed with
  `coalesce(..., false)` at each site.
- `cum_defaults`, `cum_prepaid` (`fct_vintage_curve`) and `n_from` (`fct_roll_rates`) came back
  as DuckDB `DOUBLE` instead of an integer type after a window `sum()`; CONTRACTS.md says `int`.
  Fixed with an explicit `cast(... as bigint)`.
- `metrics_monthly`'s UPB sums returned NULL (not 0) for a month with zero matching loan-months;
  fixed with `coalesce(..., 0)`.
- `vintage_quarter` was parsed from the wrong character of the loan identifier (`substr(loan_id,
  4, 1)` instead of `5`), which for `F05Q3S000495` read the literal `Q` instead of `3`. Caught
  by eyeballing `fct_vintage_curve` output, not by an automated test -- worth a dedicated test
  if this project's fixtures ever change their loan identifier format.
- `tests/fixtures/models_out/*.parquet` (committed by the validation-plan/contracts work) was
  silently excluded from every fresh checkout by an unanchored `models_out/` line in
  `.gitignore`, which also matched `tests/fixtures/models_out/`. Fixed by anchoring it to
  `/models_out/` (matching the existing `/data/` pattern) -- this was already fixed on `main`
  independently before this branch merged; this branch's own identical fix was dropped in
  favour of main's.

## Real BigQuery build

**Not run.** `dbt build --target bq` against the real 27-year, ~75M-loan-month dataset was
denied by this environment's own safety controls (reason given: "Production Deploy" -- writing
at scale to the real cloud project). A single-model smoke test (`dbt run --select dim_date
--target bq`) was allowed and did reach BigQuery successfully (real query, real project,
`vintage-credit-risk-0a13bb`), but failed for an unrelated reason: BigQuery reported
`Dataset vintage-credit-risk-0a13bb:dbt_c_intermediate was not found in location US`. dbt
normally auto-creates a missing dataset before writing to it; that did not happen here, which
may be a BigQuery sandbox restriction (the sandbox has no billing account, and dataset creation
might need an explicit `bq mk` first) rather than anything wrong with the dbt project itself.

**What this means:**
- The dbt version decision (plan item 8: try dbt v2/Fusion first) is answered by necessity:
  Fusion isn't installed in the shared venv (only dbt-core 1.12.5 + dbt-bigquery 1.12.1 +
  dbt-duckdb 1.11.0, per the environment notes), so this project uses dbt-core 1.12.x. Never
  tried against BigQuery, since the real build itself is blocked.
- Bytes scanned per model and the size of each real mart Parquet (`fct_loan_month` included)
  **cannot be reported** -- they don't exist without the real build. Reporting a number here
  would be fabricating it, which this project never does.
- `scripts/export_marts.py --target bq` and its per-model bytes-scanned report are written and
  are exactly what should be run once the build itself is unblocked; only the run is missing.

**Two things to resolve before the real build can run:**
1. Confirm the BigQuery sandbox allows dbt to create new datasets (`dbt_c`, `dbt_c_staging`,
   `dbt_c_intermediate`, `dbt_c_marts`), or create them manually first with `bq mk --dataset`.
2. Approve running `dbt build --target bq --exclude fct_ecl` (excludes `fct_ecl`, which needs
   `models_out/ecl_results.parquet` loaded into BigQuery -- not done yet) against
   the real project, since this environment classifies it as a production-scale write.

Once approved, the sequence is:
```
dbt build --project-dir dbt --profiles-dir "$DBT_PROFILES_DIR" --target bq --exclude fct_ecl
python scripts/export_marts.py --target bq
```
The second command reports bytes scanned per mart and writes `marts_out/*.parquet`, which this
file should then be updated with.

## Spot checks (ci build, by hand)

- `fct_loss_events`: five sampled rows show `lgd_economic` between 0.08 and 0.46 and
  `lgd_undiscounted` consistently a few points above `lgd_economic` for the same row (expected:
  discounting a positive recovery at a positive note rate lowers its present value, which raises
  `lgd_economic` relative to the undiscounted measure -- but `lgd_undiscounted` also adds back
  delinquent accrued interest, which is why it isn't a strict ordering; both are shown, never
  one derived from the other after the fact).
- `fct_scorecard_base` sample counts on the ci fixture (48 loans, 4 vintages): `dev_train` 13,
  `dev_test` 10, `oot` 16, `covid` 7, `excluded` 2 -- no loan appears in more than one sample,
  and the P1 assignment order (excluded, dev_train/dev_test, gap, covid, oot) was checked
  against the sample counts by hand.
- `fct_default_events`: 13 primary defaults against 21 naive defaults on the same 48-loan
  fixture, consistent with the plan's expectation that D3's forbearance exemption removes more
  naive-only defaults than primary ones (VALIDATION_PLAN section 1, D3).
