{#
  P1/P2/D6: one row per loan at origination with its 12-month outcome and sample label.
#}
with loans as (
    select * from {{ ref('dim_loan') }}
),

lm_last as (
    select lm.loan_id, lm.months_on_book as last_months_on_book
    from {{ ref('int_loan_month') }} lm
    inner join loans l on l.loan_id = lm.loan_id and l.last_period = lm.period
),

def_primary as (
    select loan_id, default_months_on_book
    from {{ ref('int_default_events') }}
    where definition = 'primary'
),

def_naive as (
    select loan_id, default_months_on_book as naive_default_mob
    from {{ ref('int_default_events') }}
    where definition = 'naive'
),

base as (
    select
        l.loan_id,
        l.vintage_year,
        l.vintage_quarter,
        l.first_payment_date,
        l.harp_flag,
        l.terminal_zero_balance_code,
        l.exit_type,
        ll.last_months_on_book,
        dp.default_months_on_book as default_mob_primary,
        dn.naive_default_mob,
        l.fico,
        l.ltv_pct,
        l.cltv_pct,
        l.dti_pct,
        l.mi_pct,
        l.rate_spread_pct,
        l.note_rate_pct,
        l.original_upb,
        l.original_loan_term,
        l.term_band,
        l.loan_purpose,
        l.occupancy_status,
        l.property_type,
        l.number_of_units,
        l.channel,
        l.first_time_homebuyer,
        l.super_conforming,
        l.number_of_borrowers,
        l.property_state,
        {{ hex_hash("l.loan_id || 'split-v1'") }} as split_hash
    from loans l
    left join lm_last ll on ll.loan_id = l.loan_id
    left join def_primary dp on dp.loan_id = l.loan_id
    left join def_naive dn on dn.loan_id = l.loan_id
),

exclusions as (
    select
        *,
        case
            when harp_flag then 'harp'
            when vintage_year = 2025 then 'window_incomplete'
            when terminal_zero_balance_code is null and coalesce(last_months_on_book, 0) < 12
                then 'window_incomplete'
            when terminal_zero_balance_code in (16, 96)
                and coalesce(last_months_on_book, 0) <= 12
                and default_mob_primary is null
                then 'indeterminate_exit'
        end as exclusion_reason
    from base
)

select
    loan_id,
    vintage_year,
    vintage_quarter,
    case
        when exclusion_reason is not null then 'excluded'
        when vintage_year between 1999 and 2015 then
            case when substr(split_hash, 1, 2) < 'b3' then 'dev_train' else 'dev_test' end
        when vintage_year = 2016 then 'gap'
        when first_payment_date between date '2019-04-01' and date '2021-12-01' then 'covid'
        when vintage_year between 2017 and 2024 then 'oot'
        else 'excluded'
    end as sample,
    exclusion_reason,
    case
        when exclusion_reason is not null then null
        when default_mob_primary between 1 and 12 then 1
        else 0
    end as default_12m,
    case
        when exclusion_reason is not null then null
        when naive_default_mob between 1 and 12 then 1
        else 0
    end as default_12m_naive,
    default_mob_primary as default_months_on_book,
    (
        exit_type in ('prepaid', 'matured')
        and coalesce(last_months_on_book, 999) <= 12
        and (default_mob_primary is null or default_mob_primary > last_months_on_book)
    ) as prepaid_12m,
    fico,
    ltv_pct,
    cltv_pct,
    dti_pct,
    mi_pct,
    rate_spread_pct,
    note_rate_pct,
    original_upb,
    original_loan_term,
    term_band,
    loan_purpose,
    occupancy_status,
    property_type,
    number_of_units,
    channel,
    first_time_homebuyer,
    super_conforming,
    number_of_borrowers,
    property_state
from exclusions
