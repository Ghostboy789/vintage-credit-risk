with orig as (
    select * from {{ ref('stg_freddie__origination') }}
),

res as (
    select * from {{ ref('int_loan_resolution') }}
),

rate_groups as (
    select
        loan_id,
        first_payment_date,
        note_rate_pct,
        case when original_loan_term <= 180 then 'short' else 'long' end as rate_term_group
    from orig
),

medians as (
    select
        first_payment_date,
        rate_term_group,
        {{ median('note_rate_pct') }} as median_rate
    from rate_groups
    group by first_payment_date, rate_term_group
)

select
    o.loan_id,
    o.vintage_year,
    o.vintage_quarter,
    o.first_payment_date,
    o.maturity_date,
    o.original_upb,
    o.original_loan_term,
    o.term_band,
    o.note_rate_pct,
    o.note_rate_pct - m.median_rate as rate_spread_pct,
    o.fico,
    case
        when o.fico is null then 'missing'
        when o.fico < 620 then 'lt_620'
        when o.fico < 660 then '620_659'
        when o.fico < 700 then '660_699'
        when o.fico < 740 then '700_739'
        when o.fico < 780 then '740_779'
        else 'ge_780'
    end as fico_band,
    o.ltv_pct,
    case
        when o.ltv_pct is null then 'missing'
        when o.ltv_pct <= 60 then 'le_60'
        when o.ltv_pct <= 80 then '60_80'
        when o.ltv_pct <= 90 then '80_90'
        when o.ltv_pct <= 95 then '90_95'
        else 'gt_95'
    end as ltv_band,
    o.cltv_pct,
    o.dti_pct,
    o.mi_pct,
    o.number_of_units,
    o.occupancy_status,
    o.channel,
    o.loan_purpose,
    o.property_type,
    o.property_state,
    o.first_time_homebuyer,
    o.number_of_borrowers,
    o.super_conforming,
    o.harp_flag,
    r.last_period,
    r.terminal_zero_balance_code,
    r.exit_type,
    r.defect_settlement_date
from orig o
left join rate_groups rg on rg.loan_id = o.loan_id
left join medians m
    on m.first_payment_date = rg.first_payment_date and m.rate_term_group = rg.rate_term_group
-- inner join: a handful of the newest originations (first payment right at the data cutoff)
-- have not reported a single performance month yet, so they have no last_period at all -- they
-- carry no loan-month observations, so they don't belong in a mart keyed off performance history
inner join res r on r.loan_id = o.loan_id
