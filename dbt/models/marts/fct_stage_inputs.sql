{#
  E1/L2: one row per loan per quarter-end reporting date, for loans on book at month end.
#}
with lm as (
    select * from {{ ref('int_loan_month') }}
),

dates as (
    select month from {{ ref('dim_date') }} where is_quarter_end
),

snapshot as (
    select lm.*, d.month as reporting_date
    from lm
    inner join dates d on d.month = lm.period
    where lm.zero_balance_code is null
),

cure_recent as (
    select
        loan_id,
        period,
        max(case when is_cure_month then 1 else 0 end) over (
            partition by loan_id order by period rows between 5 preceding and current row
        ) = 1 as cure_in_last_6m
    from lm
),

def as (
    select loan_id, default_period
    from {{ ref('int_default_events') }}
    where definition = 'primary'
),

joined as (
    select
        s.loan_id,
        s.reporting_date,
        s.vintage_year,
        s.months_on_book,
        s.age_band,
        s.remaining_months_to_legal_maturity as remaining_term,
        s.current_upb,
        s.interest_bearing_upb,
        s.non_interest_bearing_upb,
        o.note_rate_pct,
        s.current_rate_pct,
        s.rate_incentive_pct,
        s.dpd_bucket,
        s.default_exempt,
        s.forbearance_flag,
        s.assistance_plan,
        s.in_default,
        s.recent_dpd30_12m,
        s.modified,
        s.eltv_pct,
        dl.ltv_band,
        dl.property_state,
        dl.exit_type,
        dl.last_period,
        (cr.cure_in_last_6m and not s.in_default) as cured_within_6m,
        d.default_period
    from snapshot s
    left join {{ ref('stg_freddie__origination') }} o on o.loan_id = s.loan_id
    left join {{ ref('dim_loan') }} dl on dl.loan_id = s.loan_id
    left join cure_recent cr on cr.loan_id = s.loan_id and cr.period = s.reporting_date
    left join def d on d.loan_id = s.loan_id
),

with_state as (
    select
        *,
        case
            when in_default then 'default'
            when dpd_bucket = 'dpd_60' or (dpd_bucket = 'dpd_90p' and default_exempt) then 'dpd_60p'
            when dpd_bucket = 'dpd_30' or dpd_bucket = 'unknown' then 'dpd_30'
            when recent_dpd30_12m then 'recent_dpd'
            else 'clean'
        end as behaviour_state,
        case
            when in_default then 3
            when dpd_bucket in ('dpd_30', 'dpd_60', 'dpd_90p') then 2
            when dpd_bucket = 'unknown' then 2
            when forbearance_flag or assistance_plan in ('T', 'R') then 2
            when cured_within_6m then 2
            else 1
        end as stage_floor,
        case
            when in_default then 'default'
            when dpd_bucket in ('dpd_30', 'dpd_60', 'dpd_90p') then 'dpd30_backstop'
            when dpd_bucket = 'unknown' then 'unknown_status'
            when forbearance_flag then 'forbearance'
            when assistance_plan in ('T', 'R') then 'assistance_plan'
            when cured_within_6m then 'cure_probation'
        end as stage_floor_reason,
        (default_period is not null and default_period <= reporting_date) as defaulted_before,
        {{ dbt.dateadd('month', 12, 'reporting_date') }} as window_end,
        cast('{{ var("data_cutoff") }}' as date) as cutoff
    from joined
)

select
    loan_id,
    reporting_date,
    vintage_year,
    months_on_book,
    age_band,
    remaining_term,
    current_upb,
    interest_bearing_upb,
    non_interest_bearing_upb,
    note_rate_pct,
    current_rate_pct,
    rate_incentive_pct,
    dpd_bucket,
    forbearance_flag,
    assistance_plan,
    in_default,
    cured_within_6m,
    recent_dpd30_12m,
    modified,
    behaviour_state,
    stage_floor,
    stage_floor_reason,
    ltv_band,
    eltv_pct,
    property_state,
    defaulted_before,
    case
        when defaulted_before then null
        when window_end > cutoff then null
        else (default_period is not null and default_period > reporting_date and default_period <= window_end)
    end as default_next_12m,
    case
        when window_end > cutoff then null
        else (exit_type in ('prepaid', 'matured') and last_period > reporting_date and last_period <= window_end)
    end as prepaid_next_12m
from with_state
