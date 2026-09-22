"""Convert Freddie Mac Single-Family Loan-Level Dataset sample text files into typed Parquet.

Column names and types are taken from Freddie Mac's official file layout, July 2026 release
(file_layout_july_2026.xlsx, "Origination Data File" and "Monthly Performance Data File" sheets),
cross-checked against the field order in file_headers_july_2026.zip
(origination_data_file_header.txt / performance_data_file_header.txt). Both live outside this repo
in vintage-cache/downloads/freddie-docs/ -- they are Freddie Mac's own documents and are never
copied into this repo (Freddie Mac data licence, see docs/DATA_LICENCE.md).

Two column types deviate from the layout's literal "Data Type & Format" text, both confirmed
against Freddie Mac's own release-47 official sample files:
  - Original UPB and Current Non-Interest Bearing UPB are listed as plain "Numeric" (no decimal
    spec given) but the sample data carries two decimal places like every other dollar amount --
    read as DOUBLE rather than BIGINT.
  - Net Sales Proceeds is listed as "Alpha-Numeric" (max length 14), unlike every sibling loss
    field which is "Numeric - 12,2" -- kept as VARCHAR/string rather than parsed as a number.

The raw files are pipe-delimited with no header row. The naming convention this module looks for
(sample_orig_YYYY.txt / sample_svcg_YYYY.txt, from each year's sample_YYYY.zip) is Freddie Mac's
historical sample-file naming. detect_source_file() is the one place that maps a filename to
(kind, year) -- adjust the patterns there if the files actually downloaded are named differently.

This script never touches data/raw/*.zip: it only reads already-unzipped .txt files matching the
patterns above, and only writes to data/parquet/ and data/MANIFEST.json.
"""

import hashlib
import json
import os
import re
import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import VINTAGE_DATA_ROOT  # noqa: E402

LAYOUT_VERSION = "Freddie Mac Single-Family Loan-Level Dataset file layout, July 2026 release"

# (raw attribute name in the official layout, output column name, DuckDB type).
# Order matches field position in the layout and in *_data_file_header.txt exactly.
# DATE columns are 6-digit YYYYMM with no day component; parsed to the first of the month below.
ORIGINATION_COLUMNS: list[tuple[str, str, str]] = [
    ("Classic FICO", "classic_fico", "BIGINT"),
    ("First Payment Date", "first_payment_date", "DATE"),
    ("First Time Homebuyer Indicator", "first_time_homebuyer_indicator", "VARCHAR"),
    ("Maturity Date", "maturity_date", "DATE"),
    ("Metropolitan Statistical Area (MSA) Or Metropolitan Division", "msa_or_md", "BIGINT"),
    ("Mortgage Insurance Percentage (MI %)", "mi_percent", "BIGINT"),
    ("Number of Units", "number_of_units", "BIGINT"),
    ("Occupancy Status", "occupancy_status", "VARCHAR"),
    ("Original Combined Loan-to-Value (CLTV)", "cltv", "BIGINT"),
    ("Original Debt-to-Income (DTI) Ratio", "dti", "BIGINT"),
    ("Original UPB", "original_upb", "DOUBLE"),
    ("Original Loan-to-Value (LTV)", "ltv", "BIGINT"),
    ("Original Interest Rate", "original_interest_rate", "DOUBLE"),
    ("Channel", "channel", "VARCHAR"),
    ("Prepayment Penalty Indicator", "prepayment_penalty_indicator", "VARCHAR"),
    ("Amortization Type", "amortization_type", "VARCHAR"),
    ("Property State", "property_state", "VARCHAR"),
    ("Property Type", "property_type", "VARCHAR"),
    ("Postal Code", "postal_code", "VARCHAR"),
    ("Loan Identifier", "loan_id", "VARCHAR"),
    ("Loan Purpose", "loan_purpose", "VARCHAR"),
    ("Original Loan Term", "original_loan_term", "BIGINT"),
    ("Number of Borrowers", "number_of_borrowers", "BIGINT"),
    ("Seller Name", "seller_name", "VARCHAR"),
    ("Super Conforming Flag", "super_conforming_flag", "VARCHAR"),
    ("Pre-HARP Loan Sequence Number", "pre_harp_loan_sequence_number", "VARCHAR"),
    ("Special Eligibility Program", "special_eligibility_program", "VARCHAR"),
    ("HARP Indicator", "harp_indicator", "VARCHAR"),
    ("Property Valuation Method", "property_valuation_method", "BIGINT"),
    ("Interest Only (I/O) Indicator", "interest_only_indicator", "VARCHAR"),
    ("VantageScore 4.0", "vantage_score_4_0", "BIGINT"),
]

PERFORMANCE_COLUMNS: list[tuple[str, str, str]] = [
    ("Loan Identifier", "loan_id", "VARCHAR"),
    ("Period", "period", "DATE"),
    ("Current Actual UPB", "current_actual_upb", "DOUBLE"),
    ("Current Loan Delinquency Status", "current_loan_delinquency_status", "VARCHAR"),
    ("Loan Age", "loan_age", "BIGINT"),
    ("Remaining Months to Legal Maturity", "remaining_months_to_legal_maturity", "BIGINT"),
    (
        "Underwriting Defect and Major Servicing Defect Settlement Date",
        "underwriting_defect_settlement_date",
        "DATE",
    ),
    ("Modification Flag", "modification_flag", "VARCHAR"),
    ("Zero Balance Code", "zero_balance_code", "BIGINT"),
    ("Zero Balance Effective Date", "zero_balance_effective_date", "DATE"),
    ("Current Interest Rate", "current_interest_rate", "DOUBLE"),
    ("Current Non-Interest Bearing UPB", "current_non_interest_bearing_upb", "DOUBLE"),
    ("Due Date of Last Paid Installment (DDLPI)", "due_date_of_last_paid_installment", "DATE"),
    ("MI Recoveries", "mi_recoveries", "DOUBLE"),
    ("Net Sales Proceeds", "net_sales_proceeds", "VARCHAR"),
    ("Non MI Recoveries", "non_mi_recoveries", "DOUBLE"),
    ("Total Expenses", "total_expenses", "DOUBLE"),
    ("Legal Costs", "legal_costs", "DOUBLE"),
    ("Maintenance and Preservation Costs", "maintenance_and_preservation_costs", "DOUBLE"),
    ("Taxes and Insurance", "taxes_and_insurance", "DOUBLE"),
    ("Miscellaneous Expenses", "miscellaneous_expenses", "DOUBLE"),
    ("Actual Loss", "actual_loss", "DOUBLE"),
    ("Cumulative Modification Costs", "cumulative_modification_costs", "DOUBLE"),
    ("Interest Rate Step Indicator", "interest_rate_step_indicator", "VARCHAR"),
    ("Payment Deferral Flag", "payment_deferral_flag", "VARCHAR"),
    ("Estimated Loan-to-Value (ELTV)", "eltv", "BIGINT"),
    ("Zero Balance Removal UPB", "zero_balance_removal_upb", "DOUBLE"),
    ("Delinquent Accrued Interest", "delinquent_accrued_interest", "DOUBLE"),
    ("Delinquency Due to Disaster", "delinquency_due_to_disaster", "VARCHAR"),
    ("Borrower Assistance Plan", "borrower_assistance_plan", "VARCHAR"),
    ("Current Period Modification Costs", "current_period_modification_costs", "DOUBLE"),
    ("Current Interest Bearing UPB", "current_interest_bearing_upb", "DOUBLE"),
    (
        "Mortgage Insurance Cancellation Indicator",
        "mortgage_insurance_cancellation_indicator",
        "VARCHAR",
    ),
    ("Servicer Name", "servicer_name", "VARCHAR"),
    ("Bankruptcy Cramdown Costs", "bankruptcy_cramdown_costs", "DOUBLE"),
]

assert len(ORIGINATION_COLUMNS) == 31, "origination layout has 31 fields"
assert len(PERFORMANCE_COLUMNS) == 35, "performance layout has 35 fields"

# Column whose min/max becomes the manifest's "date range" for each file kind.
PRIMARY_DATE_COLUMN = {"orig": "first_payment_date", "perf": "period"}

# The one place that maps a raw filename to (kind, year). Freddie Mac's historical sample
# naming only -- extend/adjust here, not elsewhere, if the real
# downloads use a different name.
FILENAME_PATTERNS = {
    "orig": re.compile(r"^sample_orig_(\d{4})\.txt$", re.IGNORECASE),
    "perf": re.compile(r"^sample_svcg_(\d{4})\.txt$", re.IGNORECASE),
}


def detect_source_file(path: Path) -> tuple[str, int] | None:
    """Return (kind, year) for a recognised raw filename, else None."""
    for kind, pattern in FILENAME_PATTERNS.items():
        m = pattern.match(path.name)
        if m:
            return kind, int(m.group(1))
    return None


def _duckdb_columns(columns: list[tuple[str, str, str]]) -> dict[str, str]:
    # DATE fields have no day component (YYYYMM) so they're read as text and cast explicitly.
    return {name: ("VARCHAR" if dtype == "DATE" else dtype) for _, name, dtype in columns}


def _select_list(columns: list[tuple[str, str, str]]) -> str:
    exprs = []
    for _, name, dtype in columns:
        if dtype == "DATE":
            exprs.append(
                f"(CASE WHEN {name} IS NULL THEN NULL "
                f"ELSE strptime({name}, '%Y%m')::DATE END) AS {name}"
            )
        else:
            exprs.append(name)
    return ", ".join(exprs)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def convert_file(con: duckdb.DuckDBPyConnection, src: Path, kind: str, out_path: Path) -> dict:
    """Read one raw pipe-delimited file with the official schema and write it to Parquet.

    Returns the manifest entry for the written file, minus bytes/sha256 (the caller fills those
    in once the file is on disk).
    """
    columns = ORIGINATION_COLUMNS if kind == "orig" else PERFORMANCE_COLUMNS
    src_sql = src.resolve().as_posix().replace("'", "''")
    out_sql = out_path.resolve().as_posix().replace("'", "''")

    read_csv_sql = (
        f"read_csv('{src_sql}', delim='|', header=false, quote='', nullstr='', "
        f"columns={_duckdb_columns(columns)!r})"
    )
    select_sql = _select_list(columns)
    con.execute(f"COPY (SELECT {select_sql} FROM {read_csv_sql}) TO '{out_sql}' (FORMAT PARQUET)")

    date_col = PRIMARY_DATE_COLUMN[kind]
    rows, loan_count, date_min, date_max = con.execute(
        f"SELECT count(*), count(DISTINCT loan_id), min({date_col}), max({date_col}) "
        f"FROM read_parquet('{out_sql}')"
    ).fetchone()

    return {
        "source_file": src.name,
        "kind": "origination" if kind == "orig" else "performance",
        "rows": rows,
        "loan_count": loan_count,
        "date_min": str(date_min) if date_min is not None else None,
        "date_max": str(date_max) if date_max is not None else None,
    }


def build_parquet(raw_dir: Path, parquet_dir: Path, duckdb_temp: str | None = None) -> dict:
    """Convert every recognised file under raw_dir into Parquet under parquet_dir.

    Returns the manifest dict; the caller decides whether/where to write it to disk. Files that
    don't match a known naming pattern (including any still-zipped .zip) are silently skipped.
    """
    manifest: dict = {"layout_version": LAYOUT_VERSION, "files": {}}
    if not raw_dir.exists():
        return manifest

    parquet_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    try:
        if duckdb_temp:
            Path(duckdb_temp).mkdir(parents=True, exist_ok=True)
            con.execute(f"SET temp_directory = '{Path(duckdb_temp).resolve().as_posix()}'")

        for path in sorted(raw_dir.iterdir()):
            if not path.is_file():
                continue
            detected = detect_source_file(path)
            if not detected:
                continue
            kind, year = detected
            out_name = f"{kind}_{year}.parquet"
            out_path = parquet_dir / out_name

            entry = convert_file(con, path, kind, out_path)
            entry["year"] = year
            entry["bytes"] = out_path.stat().st_size
            entry["sha256"] = sha256_file(out_path)
            manifest["files"][out_name] = entry
    finally:
        con.close()

    return manifest


def main() -> None:
    raw_dir = VINTAGE_DATA_ROOT / "data" / "raw"
    parquet_dir = VINTAGE_DATA_ROOT / "data" / "parquet"
    manifest = build_parquet(raw_dir, parquet_dir, os.environ.get("VINTAGE_DUCKDB_TEMP"))
    manifest_path = VINTAGE_DATA_ROOT / "data" / "MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"Wrote {len(manifest['files'])} Parquet file(s) -> {manifest_path}")


if __name__ == "__main__":
    main()
