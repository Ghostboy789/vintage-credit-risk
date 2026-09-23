{#
  Required by the dbt Semantic Layer / MetricFlow: a day-granularity date spine to aggregate
  metrics up to (metric_time__month and so on). Not a CONTRACTS.md mart.
#}
{{ day_spine('1999-01-01', var('data_cutoff')) }}
