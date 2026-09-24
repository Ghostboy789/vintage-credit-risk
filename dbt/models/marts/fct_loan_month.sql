{#
  View on BigQuery: as a table this mart alone exceeds the sandbox's free storage quota
  (it's the loan-month grain across the full 27-year panel); a table everywhere else,
  since local/CI builds are on the small fixture years and don't hit that limit.
#}
{{ config(materialized=('view' if target.type == 'bigquery' else 'table')) }}

select
    loan_id,
    period,
    vintage_year,
    months_on_book,
    age_band,
    current_upb,
    interest_bearing_upb,
    non_interest_bearing_upb,
    current_rate_pct,
    rate_incentive_pct,
    dpd_status_raw,
    dpd_bucket,
    sma_class,
    forbearance_flag,
    assistance_plan,
    payment_deferral,
    modified,
    eltv_pct,
    default_exempt,
    default_trigger,
    is_first_default_month,
    in_default,
    is_cure_month,
    at_risk_at_start,
    recent_dpd30_12m,
    zero_balance_code,
    exit_type,
    removal_upb
from {{ ref('int_loan_month') }}
