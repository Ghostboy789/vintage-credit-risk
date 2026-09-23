{#
  D1 (primary) and D2 (naive) default events, one row per loan per definition, first occurrence
  only. Naive reuses the primary's cure/resolution (documented simplification, matching the
  synthetic fixtures: those fields are only used downstream for definition='primary', so a
  second full episode state machine isn't built just to carry unused columns).
#}
with lm as (
    select * from {{ ref('int_loan_month') }}
),

res as (
    select * from {{ ref('int_loan_resolution') }}
),

first_cure as (
    select loan_id, min(period) as first_cure_period
    from lm
    where is_cure_month
    group by loan_id
),

primary_events as (
    select
        l.loan_id,
        'primary' as definition,
        l.vintage_year,
        l.period as default_period,
        l.months_on_book as default_months_on_book,
        case
            when l.zero_balance_code in (2, 3, 9, 15) then 'credit_event_zbc'
            when l.dpd_status_raw = 'RA' then 'reo'
            else 'dpd90'
        end as default_trigger,
        coalesce(
            case when l.current_upb > 0 then l.current_upb end,
            l.removal_upb,
            l.last_positive_upb_before
        ) as ead,
        l.forbearance_12m_before as forbearance_before_default,
        fc.first_cure_period as cure_period,
        r.resolution,
        r.resolution_period,
        r.defect_settlement_date
    from lm l
    left join first_cure fc on fc.loan_id = l.loan_id
    left join res r on r.loan_id = l.loan_id
    where l.is_first_default_month
),

naive_events as (
    select
        l.loan_id,
        'naive' as definition,
        l.vintage_year,
        l.period as default_period,
        l.months_on_book as default_months_on_book,
        case
            when l.zero_balance_code in (2, 3, 9, 15) then 'credit_event_zbc'
            when l.dpd_status_raw = 'RA' then 'reo'
            else 'dpd90'
        end as default_trigger,
        coalesce(
            case when l.current_upb > 0 then l.current_upb end,
            l.removal_upb,
            l.last_positive_upb_before
        ) as ead,
        l.forbearance_12m_before as forbearance_before_default,
        cast(null as date) as cure_period,
        r.resolution,
        r.resolution_period,
        r.defect_settlement_date
    from lm l
    left join res r on r.loan_id = l.loan_id
    where (l.is_dpd90_raw or l.dpd_status_raw = 'RA' or l.zero_balance_code in (2, 3, 9, 15))
    qualify row_number() over (partition by l.loan_id order by l.period) = 1
)

select * from primary_events
union all
select * from naive_events
