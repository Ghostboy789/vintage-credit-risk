{#
  D8: the three LGD measures for every resolved primary default (resolution in
  credit_event_loss, paid_off).
#}
with def as (
    select * from {{ ref('int_default_events') }}
    where definition = 'primary'
      and resolution in ('credit_event_loss', 'paid_off')
),

orig as (
    select loan_id, ltv_pct, property_state, note_rate_pct
    from {{ ref('stg_freddie__origination') }}
),

terminal_perf as (
    select p.*
    from {{ ref('stg_freddie__performance') }} p
    inner join (
        select loan_id, max(period) as last_period
        from {{ ref('stg_freddie__performance') }}
        group by loan_id
    ) t on t.loan_id = p.loan_id and t.last_period = p.period
),

joined as (
    select
        d.loan_id,
        d.vintage_year,
        d.default_period,
        d.resolution,
        d.resolution_period as disposition_period,
        tp.zero_balance_code,
        o.ltv_pct,
        o.property_state,
        o.note_rate_pct,
        d.ead,
        coalesce(tp.zero_balance_removal_upb, 0) as removal_upb,
        coalesce(tp.net_sales_proceeds, 0) as net_sales_proceeds,
        coalesce(tp.mi_recoveries, 0) as mi_recoveries,
        coalesce(tp.non_mi_recoveries, 0) as non_mi_recoveries,
        coalesce(tp.legal_costs, 0) as legal_costs,
        coalesce(tp.maintenance_and_preservation_costs, 0) as maintenance_and_preservation_costs,
        coalesce(tp.taxes_and_insurance, 0) as taxes_and_insurance,
        coalesce(tp.miscellaneous_expenses, 0) as miscellaneous_expenses,
        coalesce(tp.total_expenses, 0) as total_expenses,
        coalesce(tp.delinquent_accrued_interest, 0) as delinquent_accrued_interest,
        tp.actual_loss as freddie_actual_loss,
        (
            (extract(year from d.resolution_period) - extract(year from d.default_period)) * 12
            + (extract(month from d.resolution_period) - extract(month from d.default_period))
        ) as months_to_resolution
    from def d
    left join orig o on o.loan_id = d.loan_id
    left join terminal_perf tp on tp.loan_id = d.loan_id
)

select
    loan_id,
    vintage_year,
    default_period,
    disposition_period,
    months_to_resolution,
    zero_balance_code,
    case zero_balance_code
        when 2 then 'third_party_sale'
        when 3 then 'short_sale_chargeoff'
        when 9 then 'reo_disposition'
        when 15 then 'whole_loan_sale'
        when 1 then 'paid_off'
    end as disposition_type,
    case
        when ltv_pct is null then 'missing'
        when ltv_pct <= 60 then 'le_60'
        when ltv_pct <= 80 then '60_80'
        when ltv_pct <= 90 then '80_90'
        when ltv_pct <= 95 then '90_95'
        else 'gt_95'
    end as ltv_band,
    property_state,
    note_rate_pct,
    ead,
    removal_upb,
    net_sales_proceeds,
    mi_recoveries,
    non_mi_recoveries,
    legal_costs,
    maintenance_and_preservation_costs,
    taxes_and_insurance,
    miscellaneous_expenses,
    total_expenses,
    delinquent_accrued_interest,
    freddie_actual_loss,
    case
        when resolution = 'paid_off' then 0.0
        else removal_upb + net_sales_proceeds + delinquent_accrued_interest + total_expenses
            + mi_recoveries + non_mi_recoveries
    end as computed_loss,
    case
        when resolution = 'paid_off' then ead
        else -(net_sales_proceeds + mi_recoveries + non_mi_recoveries + total_expenses)
    end as net_recovery,
    power(1 + note_rate_pct / 1200, -months_to_resolution) as discount_factor,
    case
        when resolution = 'paid_off' then 0.0
        else (
            ead - (-(net_sales_proceeds + mi_recoveries + non_mi_recoveries + total_expenses))
                * power(1 + note_rate_pct / 1200, -months_to_resolution)
        ) / ead
    end as lgd_economic,
    case
        when resolution = 'paid_off' then 0.0
        else (
            removal_upb + net_sales_proceeds + delinquent_accrued_interest + total_expenses
            + mi_recoveries + non_mi_recoveries
        ) / ead
    end as lgd_undiscounted,
    case
        when resolution = 'paid_off' then 0.0
        else (
            ead - (-(net_sales_proceeds + non_mi_recoveries + total_expenses))
                * power(1 + note_rate_pct / 1200, -months_to_resolution)
        ) / ead
    end as lgd_gross_of_mi,
    (
        {{ dbt.dateadd('month', -36, "cast('" ~ var('data_cutoff') ~ "' as date)") }} >= default_period
    ) as in_lgd_sample
from joined
