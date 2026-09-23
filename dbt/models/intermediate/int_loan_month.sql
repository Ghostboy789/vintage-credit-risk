{#
  One row per loan per reporting month: days-past-due bucket, SMA mapping, the D1(+D3) primary
  default trigger, D4 cure, D5 exit type, and the running "in_default" episode state.

  in_default needs sequential state (a re-default reopens the episode; a cure closes it), which
  a plain window function can't express directly and BigQuery has no recursive CTE for. The
  trick used below is standard run-length encoding: collapse each loan's trigger/cure-candidate
  months into an alternating T/C event sequence (a "first of its run" test via LAG, defaulting
  the virtual starting state to "cured"), then carry the last event type forward with
  last_value(... ignore nulls). This needs no recursion and is portable.
#}

with perf as (
    select * from {{ ref('stg_freddie__performance') }}
),

orig as (
    select loan_id, vintage_year, first_payment_date, original_loan_term
    from {{ ref('stg_freddie__origination') }}
),

rates as (
    select * from {{ ref('int_market_rate') }}
),

base as (
    select
        p.loan_id,
        p.period,
        o.vintage_year,
        (
            (extract(year from p.period) - extract(year from o.first_payment_date)) * 12
            + (extract(month from p.period) - extract(month from o.first_payment_date))
            + 1
        ) as months_on_book,
        p.current_upb,
        p.current_interest_bearing_upb as interest_bearing_upb,
        p.current_non_interest_bearing_upb as non_interest_bearing_upb,
        p.current_rate_pct,
        p.dpd_status_raw,
        p.forbearance_flag,
        p.assistance_plan,
        p.payment_deferral,
        p.eltv_pct,
        p.zero_balance_code,
        p.zero_balance_effective_date,
        p.zero_balance_removal_upb,
        p.remaining_months_to_legal_maturity,
        coalesce(p.modification_flag in ('Y', 'P'), false) as modified,
        o.original_loan_term,
        r.market_rate_pct,
        case
            when p.dpd_status_raw = '00' then 'current'
            when p.dpd_status_raw = '01' then 'dpd_30'
            when p.dpd_status_raw = '02' then 'dpd_60'
            when p.dpd_status_raw = 'RA' then 'reo'
            when p.dpd_status_raw = 'XX' then 'unknown'
            when p.dpd_status_raw is not null
                and {{ try_int('p.dpd_status_raw') }} is not null
                and {{ try_int('p.dpd_status_raw') }} >= 3
                then 'dpd_90p'
            else 'unknown'
        end as dpd_bucket,
        (
            p.dpd_status_raw is not null
            and {{ try_int('p.dpd_status_raw') }} is not null
            and {{ try_int('p.dpd_status_raw') }} >= 3
        ) as is_dpd90_raw,
        (coalesce(p.dpd_status_raw in ('01', 'RA'), false)
            or ({{ try_int('p.dpd_status_raw') }} is not null and {{ try_int('p.dpd_status_raw') }} >= 1)
        ) as is_dpd30_or_ra
    from perf p
    inner join orig o on o.loan_id = p.loan_id
    left join rates r on r.month = p.period
),

flags as (
    select
        *,
        case
            when dpd_bucket = 'current' then 'standard_or_sma_0'
            when dpd_bucket = 'dpd_30' then 'sma_1'
            when dpd_bucket = 'dpd_60' then 'sma_2'
            when dpd_bucket in ('dpd_90p', 'reo') then 'npa'
            else 'unknown'
        end as sma_class,
        (is_dpd90_raw and forbearance_flag) as default_exempt,
        coalesce(
            (is_dpd90_raw and not forbearance_flag)
            or dpd_status_raw = 'RA'
            or zero_balance_code in (2, 3, 9, 15),
            false
        ) as default_trigger,
        (coalesce(dpd_status_raw = '00', false) and zero_balance_code is null) as is_current_month,
        market_rate_pct - current_rate_pct as neg_rate_incentive_pct
    from base
),

runs as (
    -- Length of the current run of consecutive "current" months ending at this row
    -- (classic gaps-and-islands: a row_number difference is constant within one run).
    select
        *,
        row_number() over (partition by loan_id order by period)
            - row_number() over (partition by loan_id, is_current_month order by period) as run_key
    from flags
),

run_len as (
    select
        *,
        case when is_current_month
            then row_number() over (partition by loan_id, run_key order by period)
        end as current_run_length
    from runs
),

events as (
    select
        *,
        (is_current_month and current_run_length = 3) as is_cure_candidate,
        case
            when default_trigger then 'T'
            when is_current_month and current_run_length = 3 then 'C'
        end as event_type
    from run_len
),

meaningful as (
    select
        *,
        last_value(event_type ignore nulls) over (
            partition by loan_id order by period
            rows between unbounded preceding and 1 preceding
        ) as prev_event_type
    from events
),

resolved as (
    select
        *,
        (event_type is not null
            and event_type <> coalesce(prev_event_type, 'C')
        ) as is_meaningful_event,
        case
            when event_type is not null and event_type <> coalesce(prev_event_type, 'C')
                then event_type
        end as meaningful_event_type
    from meaningful
),

carried as (
    select
        *,
        last_value(meaningful_event_type ignore nulls) over (
            partition by loan_id order by period
            rows between unbounded preceding and current row
        ) as last_meaningful_type
    from resolved
),

with_default_history as (
    select
        *,
        (coalesce(last_meaningful_type, 'C') = 'T') as in_default,
        (event_type = 'C' and is_meaningful_event) as is_cure_month,
        min(case when default_trigger then period end) over (partition by loan_id) as first_default_period_ever,
        coalesce(max(case when is_dpd30_or_ra then 1 else 0 end) over (
            partition by loan_id order by period
            rows between 12 preceding and 1 preceding
        ), 0) = 1 as recent_dpd30_12m,
        coalesce(max(case when forbearance_flag then 1 else 0 end) over (
            partition by loan_id order by period
            rows between 12 preceding and 1 preceding
        ), 0) = 1 as forbearance_12m_before,
        last_value(case when current_upb > 0 then current_upb end ignore nulls) over (
            partition by loan_id order by period
            rows between unbounded preceding and 1 preceding
        ) as last_positive_upb_before
    from carried
),

exit_info as (
    select
        *,
        coalesce(period = first_default_period_ever, false) as is_first_default_month,
        case
            when zero_balance_code = 1 and months_on_book >= original_loan_term - 1 then 'matured'
            when zero_balance_code = 1 then 'prepaid'
            when zero_balance_code in (2, 3, 9, 15) then 'credit_event'
            when zero_balance_code in (16, 96) then 'other_exit'
        end as exit_type,
        lag(zero_balance_code) over (partition by loan_id order by period) as prev_zero_balance_code,
        lag(period) over (partition by loan_id order by period) as prev_period,
        lag(first_default_period_ever is not null and period >= first_default_period_ever)
            over (partition by loan_id order by period) as prev_had_first_default
    from with_default_history
)

select
    loan_id,
    period,
    vintage_year,
    months_on_book,
    case
        when months_on_book <= 0 then 'pre'
        when months_on_book <= 12 then '1_12'
        when months_on_book <= 24 then '13_24'
        when months_on_book <= 36 then '25_36'
        when months_on_book <= 60 then '37_60'
        when months_on_book <= 120 then '61_120'
        else '121p'
    end as age_band,
    current_upb,
    interest_bearing_upb,
    non_interest_bearing_upb,
    current_rate_pct,
    (current_rate_pct - market_rate_pct) as rate_incentive_pct,
    dpd_status_raw,
    dpd_bucket,
    sma_class,
    forbearance_flag,
    assistance_plan,
    payment_deferral,
    eltv_pct,
    is_dpd90_raw,
    default_exempt,
    default_trigger,
    is_first_default_month,
    in_default,
    is_cure_month,
    (prev_period is not null and prev_zero_balance_code is null and coalesce(prev_had_first_default, false) = false)
        as at_risk_at_start,
    recent_dpd30_12m,
    forbearance_12m_before,
    last_positive_upb_before,
    modified,
    zero_balance_code,
    exit_type,
    zero_balance_removal_upb as removal_upb,
    remaining_months_to_legal_maturity
from exit_info
