"""Sizing query run before the validation plan was written (aggregates only).

Kept exactly as run, except that the data path is read from VINTAGE_DATA_ROOT and the imports
are split. Run from the repo root: python -m scripts.presizing.q2
"""
# ruff: noqa

import os

import duckdb

from config import VINTAGE_DATA_ROOT
con = duckdb.connect()
con.execute(f"SET temp_directory='{os.environ['VINTAGE_DUCKDB_TEMP']}'")
P = (VINTAGE_DATA_ROOT / "data" / "parquet").as_posix()
con.execute(f"""CREATE TABLE lm AS SELECT CAST(regexp_extract(filename, 'perf_(\d{{4}})', 1) AS INT) AS vintage, loan_id, loan_age,
 current_loan_delinquency_status s, zero_balance_code z,
 (borrower_assistance_plan='F' OR delinquency_due_to_disaster='Y') AS forb
 FROM read_parquet('{P}/perf_*.parquet', filename=true)""")
q = """
WITH ev AS (
 SELECT vintage, loan_id,
  min(CASE WHEN s='RA' OR (s NOT IN ('XX','RA') AND CAST(s AS INT)>=3) OR z IN (2,3,9,15) THEN loan_age END) d_naive,
  min(CASE WHEN s='RA' OR z IN (2,3,9,15) OR (s NOT IN ('XX','RA') AND CAST(s AS INT)>=3 AND NOT coalesce(forb,false)) THEN loan_age END) d_adj,
  min(CASE WHEN z IN (1) THEN loan_age END) prepay_age,
  min(CASE WHEN z IN (16,96) THEN loan_age END) other_age,
  max(loan_age) last_age, max(z) anyz
 FROM lm GROUP BY 1,2)
SELECT vintage, count(*) n,
 sum((d_naive<=12)::INT) d12_naive, sum((d_adj<=12)::INT) d12_adj, sum((d_adj<=24)::INT) d24_adj,
 sum((d_adj IS NULL OR d_adj>12) AND anyz IS NULL AND last_age<12)::INT censored12,
 sum((prepay_age<=12 AND (d_adj IS NULL OR d_adj>prepay_age))::INT) prepaid12,
 sum((other_age<=12 AND (d_adj IS NULL OR d_adj>other_age))::INT) other12
FROM ev GROUP BY 1 ORDER BY 1"""
for r in con.execute(q).fetchall(): print(r)
