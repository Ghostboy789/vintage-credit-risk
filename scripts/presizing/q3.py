"""Sizing query run before the validation plan was written (aggregates only).

Kept exactly as run, except that the data path is read from VINTAGE_DATA_ROOT and the imports
are split. Run from the repo root: python -m scripts.presizing.q3
"""
# ruff: noqa

import duckdb

from config import VINTAGE_DATA_ROOT
con = duckdb.connect()
P = (VINTAGE_DATA_ROOT / "data" / "parquet").as_posix()
con.execute(f"CREATE VIEW o AS SELECT * FROM read_parquet('{P}/orig_*.parquet')")
for c in ["substr(loan_id,1,1)","amortization_type","interest_only_indicator","prepayment_penalty_indicator","special_eligibility_program","property_valuation_method","harp_indicator","(pre_harp_loan_sequence_number IS NOT NULL)","super_conforming_flag","channel","loan_purpose","occupancy_status","property_type","number_of_borrowers","first_time_homebuyer_indicator","original_loan_term<=180","length(loan_id)"]:
    print(c, con.execute(f"SELECT {c} v, count(*) FROM o GROUP BY 1 ORDER BY 2 DESC LIMIT 8").fetchall())
print(con.execute("SELECT min(mi_percent), max(mi_percent), sum((mi_percent=999)::INT), sum((number_of_units=99)::INT) FROM o").fetchall())
print(con.execute("SELECT year(first_payment_date) y, count(*) FROM o WHERE substr(loan_id,2,2)='07' GROUP BY 1 ORDER BY 1").fetchall())
