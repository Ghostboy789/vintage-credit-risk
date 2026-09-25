{#
  Month-to-month transition matrix (analysis #3). The from-row is any active loan-month (no
  Zero Balance Code) whose status isn't `XX` (D9: unknown is never a from-state).
#}
with lm as (
    select * from {{ ref('fct_loan_month') }}
),

pairs as (
    select
        loan_id,
        period,
        vintage_year,
        dpd_bucket,
        zero_balance_code,
        forbearance_flag,
        current_upb,
        -- Look ahead over every record, including the terminal (exit) record and unknown-status
        -- months; filtering them out first would make every exit look like a missing record.
        lead(dpd_bucket) over (partition by loan_id order by period) as next_dpd_bucket,
        lead(exit_type) over (partition by loan_id order by period) as next_exit_type,
        lead(zero_balance_code) over (partition by loan_id order by period) as next_zero_balance_code,
        lead(period) over (partition by loan_id order by period) as next_period
    from lm
),

classified as (
    select
        period,
        vintage_year,
        dpd_bucket as from_bucket,
        forbearance_flag as from_forbearance,
        current_upb,
        case
            when next_period is null then 'missing'
            when next_zero_balance_code is not null then coalesce(next_exit_type, 'other_exit')
            else next_dpd_bucket
        end as to_state
    from pairs
    where zero_balance_code is null
      and dpd_bucket in ('current', 'dpd_30', 'dpd_60', 'dpd_90p', 'reo')
),

agg as (
    select
        period,
        vintage_year,
        from_bucket,
        from_forbearance,
        to_state,
        count(*) as n_loans,
        sum(current_upb) as upb
    from classified
    group by 1, 2, 3, 4, 5
)

select
    period,
    vintage_year,
    from_bucket,
    from_forbearance,
    to_state,
    n_loans,
    upb,
    cast(sum(n_loans) over (partition by period, vintage_year, from_bucket, from_forbearance) as {{ dbt.type_bigint() }})
        as n_from,
    cast(n_loans as {{ dbt.type_float() }})
        / sum(n_loans) over (partition by period, vintage_year, from_bucket, from_forbearance) as roll_rate
from agg
