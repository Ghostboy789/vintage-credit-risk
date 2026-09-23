{#
  Built from the loss engine's ecl_results model output, written once the ECL run on real data
  loads it into BigQuery. Excluded from the real "bq" build until that table exists
  (docs/RECONCILIATION.md); builds fine on "ci" against the synthetic fixture.
#}
select
    reporting_date,
    scenario,
    grade,
    stage,
    n_loans,
    ead,
    ecl,
    in_sample
from {{ source('model_outputs', 'ecl_results') }}
