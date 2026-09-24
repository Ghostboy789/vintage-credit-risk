{#
  Cumulative default and loss curves by months on book, per origination quarter (analysis #2).
#}
with loan_month as (
    select * from {{ ref('int_loan_month') }}
),

loans as (
    select loan_id, vintage_year, vintage_quarter, original_upb, first_payment_date
    from {{ ref('dim_loan') }}
),

defaults as (
    select loan_id, vintage_year, default_months_on_book
    from {{ ref('int_default_events') }}
    where definition = 'primary'
),

losses as (
    -- Which months-on-book, for the loan, the disposition (net loss) landed at.
    select
        l.vintage_quarter,
        lm.months_on_book,
        sum(le.computed_loss) as net_loss
    from {{ ref('int_loss_events') }} le
    inner join loans l on l.loan_id = le.loan_id
    inner join loan_month lm on lm.loan_id = le.loan_id and lm.period = le.disposition_period
    where le.disposition_type != 'paid_off'
    group by 1, 2
),

cohort as (
    select
        vintage_year,
        vintage_quarter,
        count(*) as n_loans,
        sum(original_upb) as original_upb_total,
        max(first_payment_date) as max_first_payment_date
    from loans
    group by 1, 2
),

max_mob as (
    select vintage_quarter, max(months_on_book) as max_mob
    from loan_month lm
    inner join loans l on l.loan_id = lm.loan_id
    group by 1
),

mob_seq as (
    {{ int_sequence(400) }}
),

spine as (
    select c.vintage_year, c.vintage_quarter, s.mob as months_on_book
    from cohort c
    inner join max_mob m on m.vintage_quarter = c.vintage_quarter
    cross join mob_seq s
    where s.mob <= m.max_mob
),

at_risk_and_defaults as (
    select
        l.vintage_quarter,
        lm.months_on_book,
        count(distinct lm.loan_id) as n_at_risk
    from loan_month lm
    inner join loans l on l.loan_id = lm.loan_id
    left join defaults d on d.loan_id = lm.loan_id
    where d.default_months_on_book is null or d.default_months_on_book >= lm.months_on_book
    group by 1, 2
),

n_defaults as (
    select l.vintage_quarter, d.default_months_on_book as months_on_book, count(*) as n_defaults
    from defaults d
    inner join loans l on l.loan_id = d.loan_id
    group by 1, 2
),

n_prepaid as (
    select l.vintage_quarter, lm.months_on_book, count(*) as n_prepaid
    from loan_month lm
    inner join loans l on l.loan_id = lm.loan_id
    where lm.exit_type = 'prepaid'
    group by 1, 2
),

upb_by_mob as (
    select l.vintage_quarter, lm.months_on_book, sum(lm.current_upb) as upb_outstanding
    from loan_month lm
    inner join loans l on l.loan_id = lm.loan_id
    group by 1, 2
),

joined as (
    select
        sp.vintage_year,
        sp.vintage_quarter,
        sp.months_on_book,
        c.n_loans,
        c.original_upb_total,
        coalesce(ar.n_at_risk, 0) as n_at_risk,
        coalesce(nd.n_defaults, 0) as n_defaults,
        coalesce(np.n_prepaid, 0) as n_prepaid,
        coalesce(lo.net_loss, 0) as net_loss,
        coalesce(ub.upb_outstanding, 0) as upb_outstanding,
        (
            {{ dbt.dateadd('month', 'sp.months_on_book - 1', 'c.max_first_payment_date') }}
            <= cast('{{ var("data_cutoff") }}' as date)
        ) as fully_observed
    from spine sp
    inner join cohort c on c.vintage_quarter = sp.vintage_quarter
    left join at_risk_and_defaults ar
        on ar.vintage_quarter = sp.vintage_quarter and ar.months_on_book = sp.months_on_book
    left join n_defaults nd
        on nd.vintage_quarter = sp.vintage_quarter and nd.months_on_book = sp.months_on_book
    left join n_prepaid np
        on np.vintage_quarter = sp.vintage_quarter and np.months_on_book = sp.months_on_book
    left join losses lo
        on lo.vintage_quarter = sp.vintage_quarter and lo.months_on_book = sp.months_on_book
    left join upb_by_mob ub
        on ub.vintage_quarter = sp.vintage_quarter and ub.months_on_book = sp.months_on_book
)

select
    vintage_year,
    vintage_quarter,
    months_on_book,
    n_loans,
    original_upb_total,
    n_at_risk,
    n_defaults,
    cast(sum(n_defaults) over (
        partition by vintage_quarter order by months_on_book
        rows between unbounded preceding and current row
    ) as {{ dbt.type_bigint() }}) as cum_defaults,
    sum(n_defaults) over (
        partition by vintage_quarter order by months_on_book
        rows between unbounded preceding and current row
    ) / cast(n_loans as {{ dbt.type_float() }}) as cum_default_rate,
    n_prepaid,
    cast(sum(n_prepaid) over (
        partition by vintage_quarter order by months_on_book
        rows between unbounded preceding and current row
    ) as {{ dbt.type_bigint() }}) as cum_prepaid,
    net_loss,
    sum(net_loss) over (
        partition by vintage_quarter order by months_on_book
        rows between unbounded preceding and current row
    ) as cum_net_loss,
    sum(net_loss) over (
        partition by vintage_quarter order by months_on_book
        rows between unbounded preceding and current row
    ) / original_upb_total as cum_loss_rate,
    upb_outstanding,
    fully_observed
from joined
