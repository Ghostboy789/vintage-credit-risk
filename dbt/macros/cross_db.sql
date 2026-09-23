{#
  The handful of constructs that are not portable between BigQuery and DuckDB (CONTRACTS.md
  "Portability"). Everything else uses dbt-core's own cross-database macros (dbt.dateadd,
  dbt.datediff, dbt.date_trunc, dbt.safe_cast) so the models read the same on both adapters.
#}

{% macro hex_hash(expr) %}
  {#- Lowercase hex MD5, used for the reproducible dev_train/dev_test split (P1). -#}
  {%- if target.type == 'bigquery' -%}
    to_hex(md5({{ expr }}))
  {%- else -%}
    md5({{ expr }})
  {%- endif -%}
{% endmacro %}

{% macro median(expr) %}
  {#- dim_date.market_rate_pct (L1). BigQuery has no exact-median aggregate usable in a plain
      GROUP BY, so this uses APPROX_QUANTILES; DuckDB's median() is exact. The difference is
      stated in docs/RECONCILIATION.md, not hidden. -#}
  {%- if target.type == 'bigquery' -%}
    approx_quantiles({{ expr }}, 2)[offset(1)]
  {%- else -%}
    median({{ expr }})
  {%- endif -%}
{% endmacro %}

{% macro try_double(expr) %}
  {{ safe_cast(expr, 'float64', 'double') }}
{% endmacro %}

{% macro try_int(expr) %}
  {{ safe_cast(expr, 'int64', 'integer') }}
{% endmacro %}

{% macro safe_cast(expr, bq_type, other_type) %}
  {#- BigQuery has no TRY_CAST (uses SAFE_CAST); DuckDB has both, TRY_CAST is the DuckDB idiom.
      Used for net_sales_proceeds (D8) and the numeric delinquency-status check (D1/D9): a
      non-numeric value becomes null rather than failing the build. #}
  {%- if target.type == 'bigquery' -%}
    safe_cast({{ expr }} as {{ bq_type }})
  {%- else -%}
    try_cast({{ expr }} as {{ other_type }})
  {%- endif -%}
{% endmacro %}

{% macro int_sequence(n) %}
  {#- Rows 1..n. Used for the months-on-book spine in fct_vintage_curve. #}
  {%- if target.type == 'bigquery' -%}
    select mob from unnest(generate_array(1, {{ n }})) as mob
  {%- else -%}
    select mob from generate_series(1, {{ n }}) as t(mob)
  {%- endif -%}
{% endmacro %}

{% macro day_spine(start_date, end_date) %}
  {#- MetricFlow's required time-spine model (metricflow_time_spine) needs day granularity. #}
  {%- if target.type == 'bigquery' -%}
    select d as date_day
    from unnest(generate_date_array(date('{{ start_date }}'), date('{{ end_date }}'), interval 1 day)) as d
  {%- else -%}
    select cast(gs as date) as date_day
    from generate_series(date '{{ start_date }}', date '{{ end_date }}', interval '1 day') as t(gs)
  {%- endif -%}
{% endmacro %}

{% macro month_spine(start_date, end_date) %}
  {#- One row per first-of-month from start_date to end_date inclusive (dim_date). #}
  {%- if target.type == 'bigquery' -%}
    select date_trunc(d, month) as month
    from unnest(generate_date_array(date('{{ start_date }}'), date('{{ end_date }}'), interval 1 month)) as d
  {%- else -%}
    select cast(gs as date) as month
    from generate_series(date '{{ start_date }}', date '{{ end_date }}', interval '1 month') as t(gs)
  {%- endif -%}
{% endmacro %}
