{#
  Typed, renamed monthly performance file, one row per loan per reporting month, unioned across
  every vintage year. Sentinel codes become null here. `current_loan_delinquency_status` and
  `zero_balance_code` are kept exactly as reported: D9's bucket mapping and D1/D5's default and
  exit rules read the raw codes, not a pre-judged category.
#}
with unioned as (
  {% for year in var('vintage_years') %}
  select *
  from {{ source('raw', 'perf_' ~ year) }}
  {% if not loop.last %}union all{% endif %}
  {% endfor %}
)

select
    loan_id,
    period,
    current_actual_upb as current_upb,
    current_interest_bearing_upb,
    current_non_interest_bearing_upb,
    current_interest_rate as current_rate_pct,
    current_loan_delinquency_status as dpd_status_raw,
    modification_flag,
    zero_balance_code,
    zero_balance_effective_date,
    zero_balance_removal_upb,
    case when eltv = 999 then null else eltv end as eltv_pct,
    coalesce(borrower_assistance_plan = 'F', false)
        or coalesce(delinquency_due_to_disaster = 'Y', false) as forbearance_flag,
    borrower_assistance_plan as assistance_plan,
    coalesce(payment_deferral_flag in ('C', 'P'), false) as payment_deferral,
    underwriting_defect_settlement_date,
    delinquent_accrued_interest,
    mi_recoveries,
    non_mi_recoveries,
    legal_costs,
    maintenance_and_preservation_costs,
    taxes_and_insurance,
    miscellaneous_expenses,
    total_expenses,
    actual_loss,
    {{ try_double('net_sales_proceeds') }} as net_sales_proceeds,
    remaining_months_to_legal_maturity
from unioned
