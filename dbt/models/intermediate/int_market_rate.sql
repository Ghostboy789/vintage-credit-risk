{#
  L1: the median note rate of long-term (>240 month) loans by first-payment month, carried
  forward when a month has none (dim_date.market_rate_pct / market_rate_carried_forward).
#}
with spine as (
    {{ month_spine('1999-01-01', var('data_cutoff')) }}
),

long_term_loans as (
    select first_payment_date as month, note_rate_pct
    from {{ ref('stg_freddie__origination') }}
    where term_band = 'gt_240'
),

raw_rate as (
    select
        s.month,
        {{ median('l.note_rate_pct') }} as raw_market_rate_pct
    from spine s
    left join long_term_loans l on l.month = s.month
    group by s.month
)

select
    month,
    raw_market_rate_pct,
    last_value(raw_market_rate_pct ignore nulls) over (
        order by month rows between unbounded preceding and current row
    ) as market_rate_pct,
    (
        raw_market_rate_pct is null
        and last_value(raw_market_rate_pct ignore nulls) over (
            order by month rows between unbounded preceding and current row
        ) is not null
    ) as market_rate_carried_forward
from raw_rate
