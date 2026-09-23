"""Sizing query run before the validation plan was written (aggregates only).

Kept exactly as run, except that the data path is read from VINTAGE_DATA_ROOT and the imports
are split. Run from the repo root: python -m scripts.presizing.q1
"""
# ruff: noqa

import os

import duckdb

from config import VINTAGE_DATA_ROOT
con = duckdb.connect()
con.execute(f"SET temp_directory='{os.environ['VINTAGE_DUCKDB_TEMP']}'")
P = (VINTAGE_DATA_ROOT / "data" / "parquet").as_posix()
con.execute(f"CREATE VIEW perf AS SELECT *, CAST(regexp_extract(filename, 'perf_(\d{{4}})', 1) AS INT) AS vintage FROM read_parquet('{P}/perf_*.parquet', filename=true)")
print(con.execute("SELECT min(period), max(period), min(loan_age), max(loan_age) FROM perf").fetchall())
print("loan_age at first record distribution:")
print(con.execute("SELECT fa, count(*) FROM (SELECT loan_id, min(loan_age) fa FROM perf GROUP BY 1) GROUP BY 1 ORDER BY 2 DESC LIMIT 6").fetchall())
print("flag/eltv coverage by period year:")
for r in con.execute("""SELECT year(period) y,
  round(avg(CASE WHEN eltv IS NOT NULL AND eltv<>999 THEN 1 ELSE 0 END),3) eltv_ok,
  round(avg(CASE WHEN borrower_assistance_plan IS NOT NULL AND borrower_assistance_plan NOT IN ('7','9','') THEN 1 ELSE 0 END),4) bap,
  round(avg(CASE WHEN delinquency_due_to_disaster='Y' THEN 1 ELSE 0 END),4) dis,
  round(avg(CASE WHEN payment_deferral_flag='Y' THEN 1 ELSE 0 END),4) pdf,
  round(avg(CASE WHEN modification_flag='Y' THEN 1 ELSE 0 END),4) mod
  FROM perf GROUP BY 1 ORDER BY 1""").fetchall(): print(r)
print("distinct bap values:", con.execute("SELECT borrower_assistance_plan, count(*) FROM perf GROUP BY 1").fetchall())
print("distinct deferral values:", con.execute("SELECT payment_deferral_flag, count(*) FROM perf GROUP BY 1").fetchall())
print("distinct mod values:", con.execute("SELECT modification_flag, count(*) FROM perf GROUP BY 1").fetchall())
