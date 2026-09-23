select
    loan_id,
    definition,
    vintage_year,
    default_period,
    default_months_on_book,
    default_trigger,
    ead,
    forbearance_before_default,
    cure_period,
    resolution,
    resolution_period,
    defect_settlement_date
from {{ ref('int_default_events') }}
