"""Tests for extract/build_parquet.py.

All rows here are SYNTHETIC, made up inline -- never copied from Freddie Mac's sample files
(the project's data licence rule).
"""

import json
import sys
from pathlib import Path

import duckdb
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extract"))
import build_parquet  # noqa: E402

from config import VINTAGE_DATA_ROOT  # noqa: E402


def _row(columns, values: dict) -> str:
    """Build one pipe-delimited row in official column order; unset fields are left blank."""
    return "|".join(str(values.get(name, "")) for _, name, _ in columns)


ORIG_ROWS = [
    _row(
        build_parquet.ORIGINATION_COLUMNS,
        {
            "classic_fico": 700,
            "first_payment_date": "200102",
            "first_time_homebuyer_indicator": "Y",
            "maturity_date": "203101",
            "mi_percent": 25,
            "number_of_units": 1,
            "occupancy_status": "P",
            "cltv": 80,
            "dti": 36,
            "original_upb": "150000.00",
            "ltv": 80,
            "original_interest_rate": "6.500",
            "channel": "R",
            "prepayment_penalty_indicator": "N",
            "amortization_type": "FRM",
            "property_state": "CA",
            "property_type": "SF",
            "postal_code": "940",
            "loan_id": "TEST0000000001",
            "loan_purpose": "P",
            "original_loan_term": 360,
            "number_of_borrowers": 2,
            "seller_name": "SYNTHETIC TEST SELLER",
            "super_conforming_flag": "N",
            "harp_indicator": "N",
            "property_valuation_method": 1,
            "interest_only_indicator": "N",
            "vantage_score_4_0": 750,
        },
    ),
    _row(
        build_parquet.ORIGINATION_COLUMNS,
        {
            "classic_fico": 650,
            "first_payment_date": "200103",
            "first_time_homebuyer_indicator": "N",
            "maturity_date": "203102",
            "mi_percent": 0,
            "number_of_units": 1,
            "occupancy_status": "I",
            "cltv": 70,
            "dti": 40,
            "original_upb": "220000.00",
            "ltv": 70,
            "original_interest_rate": "7.125",
            "channel": "T",
            "prepayment_penalty_indicator": "N",
            "amortization_type": "FRM",
            "property_state": "TX",
            "property_type": "PU",
            "postal_code": "770",
            "loan_id": "TEST0000000002",
            "loan_purpose": "C",
            "original_loan_term": 360,
            "number_of_borrowers": 1,
            "seller_name": "SYNTHETIC TEST SELLER",
            "super_conforming_flag": "N",
            "harp_indicator": "N",
            "property_valuation_method": 2,
            "interest_only_indicator": "N",
            "vantage_score_4_0": 9999,
        },
    ),
]

PERF_ROWS = [
    _row(
        build_parquet.PERFORMANCE_COLUMNS,
        {
            "loan_id": "TEST0000000001",
            "period": "200102",
            "current_actual_upb": "150000.00",
            "current_loan_delinquency_status": "00",
            "loan_age": 0,
            "remaining_months_to_legal_maturity": 360,
            "current_interest_rate": "6.500",
        },
    ),
    _row(
        build_parquet.PERFORMANCE_COLUMNS,
        {
            "loan_id": "TEST0000000001",
            "period": "200103",
            "current_actual_upb": "149800.00",
            "current_loan_delinquency_status": "01",
            "loan_age": 1,
            "remaining_months_to_legal_maturity": 359,
            "current_interest_rate": "6.500",
        },
    ),
    _row(
        build_parquet.PERFORMANCE_COLUMNS,
        {
            "loan_id": "TEST0000000002",
            "period": "200103",
            "current_actual_upb": "220000.00",
            "current_loan_delinquency_status": "00",
            "loan_age": 0,
            "remaining_months_to_legal_maturity": 360,
            "current_interest_rate": "7.125",
        },
    ),
]


def test_detect_source_file():
    assert build_parquet.detect_source_file(Path("sample_orig_2001.txt")) == ("orig", 2001)
    assert build_parquet.detect_source_file(Path("sample_perf_2001.txt")) == ("perf", 2001)
    assert build_parquet.detect_source_file(Path("sample_2001.zip")) is None
    assert build_parquet.detect_source_file(Path("origination_sample_file.txt")) is None


def test_column_layout_field_counts():
    # 31 origination / 35 performance fields, per file_layout_july_2026.xlsx.
    assert len(build_parquet.ORIGINATION_COLUMNS) == 31
    assert len(build_parquet.PERFORMANCE_COLUMNS) == 35


def test_build_parquet_from_synthetic_rows(tmp_path):
    raw_dir = tmp_path / "raw"
    parquet_dir = tmp_path / "parquet"
    raw_dir.mkdir()

    (raw_dir / "sample_orig_2001.txt").write_text("\n".join(ORIG_ROWS) + "\n")
    (raw_dir / "sample_perf_2001.txt").write_text("\n".join(PERF_ROWS) + "\n")
    # A still-zipped file must be ignored, not processed -- A-data unzips, this script doesn't.
    (raw_dir / "sample_2001.zip").write_bytes(b"not a real zip, just checking it's skipped")

    manifest = build_parquet.build_parquet(
        raw_dir, parquet_dir, duckdb_temp=str(tmp_path / "duckdb_tmp")
    )

    assert set(manifest["files"]) == {"orig_2001.parquet", "perf_2001.parquet"}

    orig_entry = manifest["files"]["orig_2001.parquet"]
    assert orig_entry["rows"] == 2
    assert orig_entry["loan_count"] == 2
    assert orig_entry["date_min"] == "2001-02-01"
    assert orig_entry["date_max"] == "2001-03-01"
    assert orig_entry["bytes"] > 0
    assert len(orig_entry["sha256"]) == 64

    perf_entry = manifest["files"]["perf_2001.parquet"]
    assert perf_entry["rows"] == 3
    assert perf_entry["loan_count"] == 2  # two distinct loans across three loan-months
    assert perf_entry["date_min"] == "2001-02-01"
    assert perf_entry["date_max"] == "2001-03-01"

    out = parquet_dir / "orig_2001.parquet"
    assert out.stat().st_size == orig_entry["bytes"]
    assert build_parquet.sha256_file(out) == orig_entry["sha256"]

    # Round-trip a few values to check the typing decisions, not just row counts.
    con = duckdb.connect()
    orig_rows = con.execute(
        "SELECT loan_id, classic_fico, first_payment_date, original_upb, postal_code "
        f"FROM read_parquet('{out.as_posix()}') ORDER BY loan_id"
    ).fetchall()
    assert orig_rows[0][0] == "TEST0000000001"
    assert orig_rows[0][1] == 700  # BIGINT
    assert str(orig_rows[0][2]) == "2001-02-01"  # DATE, first of month
    assert orig_rows[0][3] == 150000.00  # DOUBLE, not truncated
    assert orig_rows[0][4] == "940"  # postal code kept as text, not an int

    perf_out = parquet_dir / "perf_2001.parquet"
    perf_rows = con.execute(
        "SELECT loan_id, current_loan_delinquency_status "
        f"FROM read_parquet('{perf_out.as_posix()}') "
        "WHERE period = DATE '2001-03-01' ORDER BY loan_id"
    ).fetchall()
    # Delinquency status keeps its leading zero -- it's a code, not a number.
    assert perf_rows[0][1] == "01"
    con.close()


def test_build_parquet_skips_cleanly_when_raw_dir_missing(tmp_path):
    manifest = build_parquet.build_parquet(tmp_path / "does_not_exist", tmp_path / "parquet")
    assert manifest["files"] == {}


def test_manifest_matches_real_data_or_skips():
    """Production check: real Parquet under data/ must match data/MANIFEST.json.

    Skips cleanly when there's no real data yet -- CI has none."""
    manifest_path = VINTAGE_DATA_ROOT / "data" / "MANIFEST.json"
    if not manifest_path.exists():
        pytest.skip("no data/MANIFEST.json -- real data hasn't been extracted here")

    manifest = json.loads(manifest_path.read_text())
    parquet_dir = VINTAGE_DATA_ROOT / "data" / "parquet"
    for name, entry in manifest["files"].items():
        path = parquet_dir / name
        assert path.exists(), f"{name} listed in MANIFEST.json but missing from data/parquet/"
        assert path.stat().st_size == entry["bytes"], f"{name}: size doesn't match manifest"
        assert build_parquet.sha256_file(path) == entry["sha256"], f"{name}: checksum mismatch"
