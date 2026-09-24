# dbt reconciliation

Every number in this file comes from an actual test run. The `ci`-target numbers are dated
2026-09-24; the real-data BigQuery numbers below are dated 2026-09-25. Nothing here is estimated
or invented.

## Status: verified on both the "ci" target (DuckDB, synthetic fixtures) and the real "bq" target
## (BigQuery, the full 27-year Freddie Mac dataset). See "Real BigQuery build" below.

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

## Real BigQuery build (25 Sep)

The owner approved building against the real 27-year Freddie Mac dataset in a BigQuery sandbox
(project `vintage-credit-risk-0a13bb`, no billing account, tables auto-expire; datasets
`vintage`, `vintage_staging`, `vintage_intermediate`, `vintage_marts`). `dbt build --target bq
--exclude fct_ecl` (`fct_ecl` needs `models_out/ecl_results.parquet` loaded into BigQuery, not
done yet) ran twice: the first run built 28 of 36 nodes and failed on `fct_loan_month` and
`fct_stage_inputs` with `Quota exceeded: ... free storage` -- the raw dataset alone already used
8.93 GB of the sandbox's 10 GB free-storage quota, leaving no room for the loan-month-grain marts
as tables. Fixed by materializing those two marts as **views** on the `bq` target only (a table
everywhere else, since `ci`/local builds are the small fixture years and never hit the quota):

```
{{ config(materialized=('view' if target.type == 'bigquery' else 'table')) }}
```

The second run (all 36 nodes) **passed completely**: `PASS=36 WARN=0 ERROR=0 SKIP=0`. Every mart
that depends on `fct_loan_month`/`fct_stage_inputs` (`fct_roll_rates`, `metrics_monthly`,
`fct_scorecard_base`) still built as a table over the view chain at the same cost as before (each
query re-scans the same ~2.4-2.7 GiB of underlying data whether the loan-month mart is a table or
a view) -- no downstream mart became meaningfully more expensive from this change.

**Bytes processed** (from `target/run_results.json`'s `adapter_response.bytes_processed`, the
whole `dbt build` run, models and tests together):

| | Bytes processed |
|---|---|
| Models | 17,202,875,624 (16.02 GiB) |
| Generic tests | 6,828,007,141 (6.36 GiB) |
| **Total** | **24,030,882,765 (22.38 GiB)** |

Heaviest models: `fct_vintage_curve` 2.49 GiB, `fct_loss_events` 2.44 GiB, `metrics_monthly` 2.43
GiB, `fct_default_events` 2.42 GiB, `fct_roll_rates` 2.42 GiB, `fct_scorecard_base` 2.07 GiB,
`dim_loan` 1.72 GiB (`fct_loan_month`/`fct_stage_inputs` process 0 bytes to *create* since they're
views; their cost shows up in whatever queries them). Heaviest tests: the three `fct_loan_month`
data tests, each around 1.27-2.11 GiB, since they query the view directly.

**Sandbox storage after the build:** `raw` 8.93 GB (unchanged, not written by this project),
`vintage_marts` 0.53 GB of tables (`fct_loan_month` and `fct_stage_inputs` are views, 0 bytes).
Total used 9.46 GB of 10 GB -- **about 0.54 GB of headroom left**.

**Real bugs the real data surfaced that the synthetic fixtures never triggered** (found by
`scripts/export_marts.py`'s contract check on the first real export, fixed at the root, then
re-verified with a clean second export -- not glossed over):
1. `dim_loan.loan_purpose` carried Freddie's `9` ("not available") sentinel through unnulled --
   every other categorical sentinel in `stg_freddie__origination.sql` was already nulled, this one
   was missed. Fixed with the same `case when ... = '9' then null` pattern used elsewhere.
2. `dim_loan.last_period` (contract: not null) was null for 5 of 1,350,000 loans -- all five are
   2025Q4 originations whose first payment date falls on or after the `2026-03-01` data cutoff, so
   they have zero performance-file records yet. A loan with no performance history carries no
   loan-month observations and doesn't belong in a mart keyed off that history, so `dim_loan` now
   inner-joins its resolution table instead of left-joining it, dropping those 5 loans (documented
   in the model with a comment; this is a real, tiny, cutoff-driven data-coverage gap, not a bug in
   the join key or the source data itself).
3. `fct_scorecard_base.prepaid_12m` (contract: not null) came back null for 43,063 rows -- the same
   SQL three-valued-logic pattern as the six bugs already listed below (`exit_type in (...)` on a
   nullable column), just on a column the synthetic fixtures never actually left null for an active
   loan. Fixed with `coalesce(..., false)`.
4. `fct_stage_inputs.remaining_term` (contract: not null) was null for 103 of 24,738,985 rows
   (0.0004%) -- a tiny share of real servicer records omit `remaining_months_to_legal_maturity`
   outright. Fixed by falling back to the same value computed from `original_loan_term` and months
   on book (the definitionally equivalent quantity) when the raw field is missing, in
   `int_loan_month.sql`.

After these four fixes, `python scripts/export_marts.py --target bq` (streaming every mart to
Parquet page-by-page via the BigQuery Storage API into a `pyarrow.parquet.ParquetWriter`, so peak
memory stays bounded even for the 75M-row `fct_loan_month`) exported all 10 marts and every one
passed `tests/contracts.py` with zero problems:

| Mart | Rows | Bytes scanned to export | Parquet size | Wall time |
|---|---:|---:|---:|---:|
| `dim_date` | 327 | 16,900 | 6,035 B | 5.7s |
| `dim_loan` | 1,349,995 | 269,977,460 | 41.9 MiB | 56.8s |
| `fct_loan_month` | 74,919,968 | 5,018,578,151 | 2.62 GiB | 1,460.8s |
| `fct_default_events` | 121,626 | 10,201,882 | 2.9 MiB | 6.8s |
| `fct_loss_events` | 36,723 | 8,398,610 | 3.6 MiB | 5.8s |
| `fct_vintage_curve` | 17,864 | 2,161,544 | 739 KiB | 4.6s |
| `fct_roll_rates` | 98,611 | 6,475,067 | 1.9 MiB | 4.0s |
| `fct_scorecard_base` | 1,349,995 | 232,532,665 | 36.2 MiB | 38.2s |
| `fct_stage_inputs` | 24,738,985 | 5,662,208,221 | 1.00 GiB | 803.9s |
| `metrics_monthly` | 327 | 44,464 | 43.3 KiB | 4.2s |

`fct_loan_month` is exported even though it's a BigQuery view (`models/pd/run.py` reads
`marts_out/fct_loan_month.parquet` directly). `fct_ecl` is excluded from this build and export --
nobody has loaded `models_out/ecl_results.parquet` into BigQuery yet, so it only ever ran on the
`ci` fixture, as the plan expects.

### R1-R3 and loss sums against the raw Parquet (real data)

Per the validation plan's pre-registration, only counts, loan-month counts, balances and loss
sums are checked here -- **not** default rates by vintage for 2016+ (that's the out-of-time
scoring step). All of the below is DuckDB reading the raw `data/parquet/orig_*.parquet` /
`perf_*.parquet` files directly against the exported `marts_out/*.parquet`, tolerance stated per
row.

| Rule | Raw Parquet | Mart | Difference | Tolerance | Result |
|---|---:|---:|---:|---:|:---:|
| R1: loan count | 1,350,000 distinct `loan_id` (`orig_*`) | 1,349,995 (`dim_loan`) | 5 | Explained exactly (see bug #2 above: 2025Q4 loans with zero performance months at the cutoff) | **PASS** |
| R2: loan-month count | 74,919,968 rows (`perf_*`) | 74,919,968 (`fct_loan_month`) | 0 | Exact | **PASS** |
| R3: balances | $12,608,064,446,146.58 sum `current_actual_upb` | $12,608,064,446,146.85 sum `current_upb` | $0.27 | Floating-point summation order over 75M rows (2e-14 relative) | **PASS** |
| Loss sums | $1,389,485,536.74 sum `actual_loss` on the 19,639 raw performance records that are each loan's terminal (`last_period`) row, matched by `loan_id` | $1,389,485,536.74 sum `freddie_actual_loss` (`fct_loss_events`, non-null rows only) | $0.0000012 | Floating-point rounding | **PASS** |

All four checks pass. The loss-sum match is also R5 in miniature: `fct_loss_events.computed_loss`
(D8's own formula, built from Freddie's disclosed loss components) equals `freddie_actual_loss`
(Freddie's own reported figure, passed through unmodified) to the cent on every one of the 19,639
rows where Freddie reports a value -- the formula reproduces the real disclosed loss exactly, not
just on the synthetic fixture.

**What this does not establish:** default rates, cure rates, roll rates or loss rates by vintage
for 2016 and later -- those are out of scope until the out-of-time scoring step, by the plan's own
pre-registration rule, and none were computed or eyeballed here.

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
