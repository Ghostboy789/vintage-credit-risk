with lm as (
    select * from {{ ref('fct_loan_month') }}
),

losses as (
    select disposition_period as period, sum(computed_loss) as net_loss
    from {{ ref('fct_loss_events') }}
    where disposition_type != 'paid_off'
    group by 1
),

per_month as (
    select
        period,
        count(case when zero_balance_code is null then 1 end) as n_active_loans,
        coalesce(sum(case when zero_balance_code is null then current_upb end), 0) as total_upb,
        count(case when zero_balance_code is null and dpd_bucket in ('dpd_30', 'dpd_60', 'dpd_90p', 'reo')
            then 1 end) as n_dpd30p,
        coalesce(sum(case when zero_balance_code is null and dpd_bucket in ('dpd_30', 'dpd_60', 'dpd_90p', 'reo')
            then current_upb end), 0) as upb_dpd30p,
        count(case when zero_balance_code is null and dpd_bucket in ('dpd_90p', 'reo') then 1 end) as n_dpd90p,
        coalesce(sum(case when zero_balance_code is null and dpd_bucket in ('dpd_90p', 'reo')
            then current_upb end), 0) as upb_dpd90p,
        count(case when at_risk_at_start then 1 end) as n_at_risk_start,
        count(case when is_first_default_month then 1 end) as n_new_defaults,
        count(case when exit_type = 'prepaid' then 1 end) as n_prepaid,
        coalesce(sum(case when exit_type = 'prepaid' then removal_upb end), 0) as upb_prepaid,
        count(case when exit_type = 'credit_event' then 1 end) as n_credit_event_exits
    from lm
    group by 1
)

select
    p.period,
    p.n_active_loans,
    p.total_upb,
    p.n_dpd30p,
    p.upb_dpd30p,
    p.n_dpd90p,
    p.upb_dpd90p,
    p.n_at_risk_start,
    p.n_new_defaults,
    p.n_prepaid,
    p.upb_prepaid,
    p.n_credit_event_exits,
    coalesce(l.net_loss, 0) as net_loss,
    case when p.total_upb > 0 then p.upb_dpd30p / p.total_upb end as delinquency_rate_30p,
    case when p.total_upb > 0 then p.upb_dpd90p / p.total_upb end as delinquency_rate_90p,
    case when p.n_at_risk_start > 0 then cast(p.n_new_defaults as {{ dbt.type_float() }}) / p.n_at_risk_start end as default_rate,
    case when p.total_upb > 0 then coalesce(l.net_loss, 0) / p.total_upb end as loss_rate
from per_month p
left join losses l on l.period = p.period
