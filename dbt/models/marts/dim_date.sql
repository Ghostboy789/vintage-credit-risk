select
    month,
    extract(year from month) as year,
    extract(quarter from month) as quarter,
    cast(extract(year from month) as {{ dbt.type_string() }}) || 'Q' || cast(extract(quarter from month) as {{ dbt.type_string() }})
        as year_quarter,
    (extract(month from month) in (3, 6, 9, 12)) as is_quarter_end,
    case
        when month <= date '2006-12-01' then 'pre_crisis'
        when month <= date '2011-12-01' then 'crisis'
        when month <= date '2020-02-01' then 'recovery'
        when month <= date '2021-12-01' then 'covid'
        else 'recent'
    end as economic_period,
    market_rate_pct,
    market_rate_carried_forward
from {{ ref('int_market_rate') }}
