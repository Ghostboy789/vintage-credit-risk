"""Compute the aggregate numbers behind docs/DATA_PROFILE.md, straight from data/parquet/ with
DuckDB -- nothing here is estimated or hand-typed. Prints one labelled block per query; the
DATA_PROFILE.md numbers are copy-pasted from this script's own output, not from memory.

Only ever prints counts, percentages and distinct-value distributions (never a loan id or a
single loan's row) -- this project's data licence permits aggregates only.
"""

import os
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import VINTAGE_DATA_ROOT  # noqa: E402

ORIG_GLOB = str(VINTAGE_DATA_ROOT / "data" / "parquet" / "orig_*.parquet")
PERF_GLOB = str(VINTAGE_DATA_ROOT / "data" / "parquet" / "perf_*.parquet")

# Zero Balance Code enumerations per Freddie Mac's General User Guide, Release 47 (July 2026),
# "Interpreting the Data -- Zero Balance Codes". Actual Loss is calculated only for 02/03/09/15,
# so those four are treated here as the "default-type" codes. The column is typed BIGINT (see
# extract/build_parquet.py), so codes come back as plain ints (1, 9, ...), not zero-padded text.
ZERO_BALANCE_LABELS = {
    1: "Prepaid or Matured (Voluntary Payoff)",
    2: "Third Party Sale",
    3: "Short Sale or Charge Off",
    9: "REO Disposition",
    15: "Whole Loan sales",
    16: "Reperforming loan securitizations",
    96: "Confirmed Underwriting Defect or Major Servicing Defect prior to credit event",
}
DEFAULT_TYPE_CODES = (2, 3, 9, 15)


def q(con, sql, params=None):
    return con.execute(sql, params or []).fetchall()


def section(title):
    print(f"\n=== {title} ===")


def main():
    con = duckdb.connect()
    if os.environ.get("VINTAGE_DUCKDB_TEMP"):
        con.execute(f"SET temp_directory = '{os.environ['VINTAGE_DUCKDB_TEMP']}'")

    section("Loans and loan-months per origination vintage year")
    rows = q(con, f"""
        SELECT
          regexp_extract(filename, 'orig_(\\d{{4}})', 1) AS vintage_year,
          count(*) AS loans,
          count(DISTINCT loan_id) AS distinct_loans
        FROM read_parquet('{ORIG_GLOB}', filename=true)
        GROUP BY 1 ORDER BY 1
    """)
    for vintage_year, loans, distinct_loans in rows:
        print(f"{vintage_year}: {loans:,} loans ({distinct_loans:,} distinct loan_id)")

    rows = q(con, f"""
        SELECT
          regexp_extract(filename, 'perf_(\\d{{4}})', 1) AS vintage_year,
          count(*) AS loan_months
        FROM read_parquet('{PERF_GLOB}', filename=true)
        GROUP BY 1 ORDER BY 1
    """)
    for vintage_year, loan_months in rows:
        print(f"{vintage_year}: {loan_months:,} loan-months")

    section("Loan outcome per vintage: prepay / default-type / other zero-balance / still active")
    outcome_by_year = q(con, f"""
        WITH terminal AS (
          SELECT
            regexp_extract(filename, 'perf_(\\d{{4}})', 1) AS vintage_year,
            loan_id,
            arg_max(zero_balance_code, period) FILTER (WHERE zero_balance_code IS NOT NULL)
              AS terminal_code
          FROM read_parquet('{PERF_GLOB}', filename=true)
          GROUP BY 1, 2
        )
        SELECT
          vintage_year,
          count(*) FILTER (WHERE terminal_code IS NULL) AS still_active,
          count(*) FILTER (WHERE terminal_code = 1) AS prepaid_or_matured,
          count(*) FILTER (WHERE terminal_code IN {DEFAULT_TYPE_CODES}) AS default_type,
          count(*) FILTER (
            WHERE terminal_code IS NOT NULL AND terminal_code NOT IN (1, 2, 3, 9, 15)
          ) AS other_removal,
          count(*) AS total_loans
        FROM terminal
        GROUP BY 1 ORDER BY 1
    """)
    for row in outcome_by_year:
        y, active, prepay, default_type, other, total = row
        print(
            f"{y}: {total:,} loans -- active {active:,} ({active/total:.1%}), "
            f"prepaid/matured {prepay:,} ({prepay/total:.1%}), "
            f"default-type (02/03/09/15) {default_type:,} ({default_type/total:.1%}), "
            f"other removal {other:,} ({other/total:.1%})"
        )

    section("Zero Balance Code distribution (all vintages, terminal record per loan)")
    zb_dist = q(con, f"""
        WITH terminal AS (
          SELECT loan_id,
                 arg_max(zero_balance_code, period) FILTER (WHERE zero_balance_code IS NOT NULL)
                   AS terminal_code
          FROM read_parquet('{PERF_GLOB}')
          GROUP BY 1
        )
        SELECT terminal_code, count(*) AS n
        FROM terminal
        WHERE terminal_code IS NOT NULL
        GROUP BY 1 ORDER BY n DESC
    """)
    for code, n in zb_dist:
        label = ZERO_BALANCE_LABELS.get(code, "NOT in the documented enumeration")
        print(f"  {code:02d}: {n:,} loans -- {label}")

    section("Current Loan Delinquency Status: raw code distribution (all loan-months)")
    dq_dist = q(con, f"""
        SELECT current_loan_delinquency_status, count(*) AS n
        FROM read_parquet('{PERF_GLOB}')
        GROUP BY 1 ORDER BY n DESC
        LIMIT 20
    """)
    total_perf_rows = q(con, f"SELECT count(*) FROM read_parquet('{PERF_GLOB}')")[0][0]
    for code, n in dq_dist:
        print(f"  {code!r}: {n:,} ({n/total_perf_rows:.2%})")

    section("Current Loan Delinquency Status: bucketed (00=current, 01=30-59, 02=60-89, "
            "numeric>=03=90+, RA=REO acquisition, XX=not available)")
    dq_bucket = q(con, f"""
        SELECT
          CASE
            WHEN current_loan_delinquency_status = '00' THEN 'current'
            WHEN current_loan_delinquency_status = '01' THEN '30-59 days'
            WHEN current_loan_delinquency_status = '02' THEN '60-89 days'
            WHEN current_loan_delinquency_status = 'RA' THEN 'REO acquisition'
            WHEN current_loan_delinquency_status = 'XX' THEN 'not available'
            WHEN try_cast(current_loan_delinquency_status AS INT) >= 3 THEN '90+ days'
            ELSE 'other/unexpected: ' || current_loan_delinquency_status
          END AS bucket,
          count(*) AS n
        FROM read_parquet('{PERF_GLOB}')
        GROUP BY 1 ORDER BY n DESC
    """)
    for bucket, n in dq_bucket:
        print(f"  {bucket}: {n:,} ({n/total_perf_rows:.2%})")

    section("Loss-related field coverage (% of all loan-months that are non-null)")
    loss_cols = [
        "mi_recoveries", "non_mi_recoveries", "total_expenses", "legal_costs",
        "maintenance_and_preservation_costs", "taxes_and_insurance",
        "miscellaneous_expenses", "actual_loss", "cumulative_modification_costs",
        "zero_balance_removal_upb", "delinquent_accrued_interest",
        "bankruptcy_cramdown_costs",
    ]
    select_list = ", ".join(f"count({c}) AS {c}" for c in loss_cols)
    row = q(con, f"SELECT {select_list} FROM read_parquet('{PERF_GLOB}')")[0]
    for col, non_null in zip(loss_cols, row):
        print(f"  {col}: {non_null:,} / {total_perf_rows:,} ({non_null/total_perf_rows:.3%})")

    section("Net Sales Proceeds: filled, and whether values are numeric or a non-numeric code")
    nsp = q(con, rf"""
        SELECT
          count(*) FILTER (WHERE net_sales_proceeds IS NOT NULL) AS filled,
          count(*) FILTER (
            WHERE net_sales_proceeds IS NOT NULL
              AND net_sales_proceeds !~ '^-?[0-9]+(\.[0-9]+)?$'
          ) AS non_numeric,
          count(*) FILTER (
            WHERE net_sales_proceeds ~ '^-?[0-9]+(\.[0-9]+)?$'
              AND try_cast(net_sales_proceeds AS DOUBLE) < 0
          ) AS negative,
          count(*) FILTER (
            WHERE net_sales_proceeds ~ '^-?[0-9]+(\.[0-9]+)?$'
              AND try_cast(net_sales_proceeds AS DOUBLE) = 0
          ) AS zero,
          count(*) FILTER (
            WHERE net_sales_proceeds ~ '^-?[0-9]+(\.[0-9]+)?$'
              AND try_cast(net_sales_proceeds AS DOUBLE) > 0
          ) AS positive
        FROM read_parquet('{PERF_GLOB}')
    """)[0]
    filled, non_numeric, negative, zero, positive = nsp
    print(f"  filled: {filled:,} / {total_perf_rows:,} ({filled/total_perf_rows:.3%})")
    print(f"  non-numeric codes among filled: {non_numeric:,}")
    print(f"  numeric, negative: {negative:,}  zero: {zero:,}  positive: {positive:,}")

    section("Original UPB and Current Non-Interest Bearing UPB: do they ever carry cents?")
    upb = q(con, f"""
        SELECT
          sum(CASE WHEN original_upb <> floor(original_upb) THEN 1 ELSE 0 END) AS orig_has_cents,
          sum(CASE WHEN original_upb % 1000 <> 0 THEN 1 ELSE 0 END) AS orig_not_multiple_of_1000,
          count(*) AS orig_total,
          min(original_upb) AS orig_min, max(original_upb) AS orig_max
        FROM read_parquet('{ORIG_GLOB}')
    """)[0]
    print(f"  original_upb: has_cents={upb[0]:,}/{upb[2]:,}, "
          f"not_multiple_of_$1000={upb[1]:,}, range=${upb[3]:,.0f}-${upb[4]:,.0f}")
    cnib = q(con, f"""
        SELECT
          sum(CASE WHEN current_non_interest_bearing_upb <> floor(current_non_interest_bearing_upb)
              THEN 1 ELSE 0 END) AS has_cents,
          count(*) FILTER (WHERE current_non_interest_bearing_upb IS NOT NULL) AS non_null,
          count(*) AS total
        FROM read_parquet('{PERF_GLOB}')
    """)[0]
    print(f"  current_non_interest_bearing_upb: has_cents={cnib[0]:,}, "
          f"non_null={cnib[1]:,}/{cnib[2]:,}")

    section("Forbearance / disaster / assistance flag coverage, 2020-2021 vs all years")
    for label, year_filter in [("2020-2021", "strftime(period, '%Y') IN ('2020', '2021')"),
                                ("all years", "TRUE")]:
        row = q(con, f"""
            SELECT
              count(*) AS total,
              count(payment_deferral_flag) AS deferral_filled,
              count(delinquency_due_to_disaster) AS disaster_filled,
              count(borrower_assistance_plan) AS assistance_filled
            FROM read_parquet('{PERF_GLOB}')
            WHERE {year_filter}
        """)[0]
        total, deferral, disaster, assistance = row
        print(f"  [{label}] total loan-months={total:,}: "
              f"payment_deferral_flag filled={deferral:,} ({deferral/total:.3%}), "
              f"delinquency_due_to_disaster filled={disaster:,} ({disaster/total:.3%}), "
              f"borrower_assistance_plan filled={assistance:,} ({assistance/total:.3%})")

    section("Borrower Assistance Plan value distribution, 2020-2021")
    bap = q(con, """
        SELECT borrower_assistance_plan, count(*) AS n
        FROM read_parquet(?)
        WHERE strftime(period, '%Y') IN ('2020', '2021') AND borrower_assistance_plan IS NOT NULL
        GROUP BY 1 ORDER BY n DESC
    """, [PERF_GLOB])
    for val, n in bap:
        print(f"  {val!r}: {n:,}")

    section("Missing credit scores, DTI, LTV/CLTV at origination (sentinel codes per the "
            "official glossary: FICO/VantageScore 9999, DTI/LTV/CLTV 999 = Not Available)")
    miss = q(con, f"""
        SELECT
          count(*) AS total,
          count(*) FILTER (WHERE classic_fico = 9999) AS fico_na,
          count(*) FILTER (WHERE vantage_score_4_0 = 9999) AS vantage_na,
          count(*) FILTER (WHERE dti = 999) AS dti_na,
          count(*) FILTER (WHERE ltv = 999) AS ltv_na,
          count(*) FILTER (WHERE cltv = 999) AS cltv_na,
          count(*) FILTER (WHERE classic_fico IS NULL) AS fico_null,
          count(*) FILTER (WHERE dti IS NULL) AS dti_null,
          count(*) FILTER (WHERE ltv IS NULL) AS ltv_null
        FROM read_parquet('{ORIG_GLOB}')
    """)[0]
    total = miss[0]
    labels = ["fico_na(9999)", "vantage_na(9999)", "dti_na(999)", "ltv_na(999)", "cltv_na(999)",
              "fico_null", "dti_null", "ltv_null"]
    for label, n in zip(labels, miss[1:]):
        print(f"  {label}: {n:,} / {total:,} ({n/total:.3%})")

    con.close()


if __name__ == "__main__":
    main()
