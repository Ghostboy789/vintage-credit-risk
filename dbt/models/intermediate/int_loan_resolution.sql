{#
  D8's resolution table, one row per loan (not per definition -- the terminal outcome doesn't
  depend on which default definition found the loan). Feeds int_default_events.resolution and
  int_loss_events.
#}
with lm as (
    select * from {{ ref('int_loan_month') }}
),

perf as (
    select * from {{ ref('stg_freddie__performance') }}
),

terminal_period as (
    select loan_id, max(period) as last_period
    from lm
    group by loan_id
),

terminal_lm as (
    select
        l.loan_id,
        l.period as last_period,
        l.zero_balance_code as terminal_zero_balance_code,
        l.exit_type,
        l.in_default as terminal_in_default
    from lm l
    inner join terminal_period t on t.loan_id = l.loan_id and t.last_period = l.period
),

terminal_perf as (
    select
        p.loan_id,
        p.zero_balance_effective_date,
        p.actual_loss
    from perf p
    inner join terminal_period t on t.loan_id = p.loan_id and t.last_period = p.period
),

settlement as (
    select loan_id, min(underwriting_defect_settlement_date) as defect_settlement_date
    from perf
    where underwriting_defect_settlement_date is not null
    group by loan_id
),

ever_defaulted as (
    select loan_id, max(case when is_first_default_month then 1 else 0 end) as ever_defaulted
    from lm
    group by loan_id
)

select
    tl.loan_id,
    tl.last_period,
    tl.terminal_zero_balance_code,
    tl.exit_type,
    s.defect_settlement_date,
    case
        when tl.terminal_zero_balance_code in (2, 3, 9, 15) and s.defect_settlement_date is not null
            then 'defect_settlement'
        when tl.terminal_zero_balance_code in (2, 3, 9, 15) and tp.actual_loss is not null
            then 'credit_event_loss'
        when tl.terminal_zero_balance_code = 1 then 'paid_off'
        when tl.terminal_zero_balance_code in (16, 96) then 'other_exit'
        when tl.terminal_zero_balance_code is null
            and coalesce(ed.ever_defaulted, 0) = 1
            and tl.terminal_in_default = false
            then 'cured_active'
        else 'open'
    end as resolution,
    case
        when tl.terminal_zero_balance_code in (1, 2, 3, 9, 15, 16, 96)
            then coalesce(tp.zero_balance_effective_date, tl.last_period)
    end as resolution_period,
    tp.actual_loss as freddie_actual_loss
from terminal_lm tl
left join terminal_perf tp on tp.loan_id = tl.loan_id
left join settlement s on s.loan_id = tl.loan_id
left join ever_defaulted ed on ed.loan_id = tl.loan_id
