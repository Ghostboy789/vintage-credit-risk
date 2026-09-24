{#
  Typed, renamed origination file, one row per loan, unioned across every vintage year in
  var('vintage_years'). Sentinel codes (CONTRACTS.md "Missing values") become null here, once,
  so no mart has to repeat the check. vintage_year is the sample file's year (CONTRACTS.md
  "Vintage": also the loan identifier's year, e.g. F07Q3... = 2007).
#}
with unioned as (
  {% for year in var('vintage_years') %}
  select *, {{ year }} as vintage_year
  from {{ source('raw', 'orig_' ~ year) }}
  {% if not loop.last %}union all{% endif %}
  {% endfor %}
)

select
    loan_id,
    vintage_year,
    cast(vintage_year as {{ dbt.type_string() }}) || 'Q' || substr(loan_id, 5, 1) as vintage_quarter,
    first_payment_date,
    maturity_date,
    original_upb,
    original_loan_term,
    case
        when original_loan_term <= 180 then 'le_180'
        when original_loan_term <= 240 then '181_240'
        else 'gt_240'
    end as term_band,
    original_interest_rate as note_rate_pct,
    case when classic_fico = 9999 then null else classic_fico end as fico,
    case when ltv = 999 then null else ltv end as ltv_pct,
    case when cltv = 999 then null else cltv end as cltv_pct,
    case when dti = 999 then null else dti end as dti_pct,
    case when mi_percent = 999 then null else mi_percent end as mi_pct,
    number_of_units,
    case when occupancy_status = '9' then null else occupancy_status end as occupancy_status,
    case when channel = '9' then null else channel end as channel,
    case when loan_purpose = '9' then null else loan_purpose end as loan_purpose,
    case when property_type = '99' then null else property_type end as property_type,
    property_state,
    case
        when first_time_homebuyer_indicator = '9' then null
        else first_time_homebuyer_indicator
    end as first_time_homebuyer,
    case when number_of_borrowers = 99 then null else number_of_borrowers end as number_of_borrowers,
    coalesce(super_conforming_flag = 'Y', false) as super_conforming,
    coalesce(harp_indicator = 'Y', false) or pre_harp_loan_sequence_number is not null as harp_flag
from unioned
