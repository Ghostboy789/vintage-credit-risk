"""Exports every dbt mart to marts_out/<name>.parquet under VINTAGE_DATA_ROOT and checks each
one against CONTRACTS.md (tests/contracts.py). Works against any dbt target:

    python scripts/export_marts.py --target bq   # BigQuery dataset written by `dbt build`
    python scripts/export_marts.py --target ci --duckdb-path <path>      # a DuckDB ci build
    python scripts/export_marts.py --target local --duckdb-path <path>  # a DuckDB local build

Reports the bytes scanned for the BigQuery export (the validation plan's reconciliation ask).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import VINTAGE_DATA_ROOT  # noqa: E402
from tests import contracts  # noqa: E402

MART_NAMES = [
    "dim_date",
    "dim_loan",
    "fct_loan_month",
    "fct_default_events",
    "fct_loss_events",
    "fct_vintage_curve",
    "fct_roll_rates",
    "fct_scorecard_base",
    "fct_stage_inputs",
    "metrics_monthly",
    "fct_ecl",
]


def export_from_duckdb(duckdb_path: str, out_dir: Path, marts: list[str]) -> None:
    import duckdb

    con = duckdb.connect(duckdb_path, read_only=True)
    try:
        for name in marts:
            out_path = out_dir / f"{name}.parquet"
            dest = out_path.as_posix()
            con.execute(f"COPY (SELECT * FROM main_marts.{name}) TO '{dest}' (FORMAT PARQUET)")
            print(f"wrote {out_path} from duckdb main_marts.{name}")
    finally:
        con.close()


def export_from_bigquery(project: str, dataset: str, out_dir: Path, marts: list[str]) -> int:
    """Returns total bytes billed/scanned across every export query.

    Streams each mart page-by-page (RowIterator.to_arrow_iterable, no bqstorage client
    needed) into a ParquetWriter instead of materializing the whole result as one Arrow
    table, so peak memory stays bounded even for the loan-month-level marts.
    """
    import time

    import pyarrow.parquet as pq
    from google.cloud import bigquery, bigquery_storage

    client = bigquery.Client(project=project)
    bqstorage_client = bigquery_storage.BigQueryReadClient(
        credentials=client._credentials
    )
    total_bytes = 0
    for name in marts:
        table = f"{project}.{dataset}_marts.{name}"
        start = time.monotonic()
        job = client.query(f"SELECT * FROM `{table}`")
        result = job.result()
        out_path = out_dir / f"{name}.parquet"
        writer = None
        rows = 0
        try:
            for batch in result.to_arrow_iterable(bqstorage_client=bqstorage_client):
                if writer is None:
                    writer = pq.ParquetWriter(out_path, batch.schema)
                writer.write_batch(batch)
                rows += batch.num_rows
        finally:
            if writer is not None:
                writer.close()
        if writer is None:
            # Zero-row result: no pages were yielded, write an empty file with the
            # right schema (cheap at 0 rows).
            pq.write_table(result.to_arrow(create_bqstorage_client=False), out_path)
        elapsed = time.monotonic() - start
        scanned = job.total_bytes_processed or 0
        total_bytes += scanned
        size = out_path.stat().st_size
        print(
            f"wrote {out_path} from {table} ({scanned:,} bytes scanned, {rows:,} rows, "
            f"{size:,} bytes on disk, {elapsed:.1f}s)"
        )
    return total_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=["bq", "ci", "local"], required=True)
    parser.add_argument("--duckdb-path", help="Required for --target ci/local")
    parser.add_argument("--project", help="GCP project; defaults to VINTAGE_GCP_PROJECT")
    parser.add_argument(
        "--dataset", default="vintage", help="dbt output dataset (matches profiles.yml)"
    )
    parser.add_argument("--marts", nargs="*", default=MART_NAMES)
    args = parser.parse_args()

    out_dir = VINTAGE_DATA_ROOT / "marts_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.target in ("ci", "local"):
        if not args.duckdb_path:
            parser.error(f"--duckdb-path is required for --target {args.target}")
        export_from_duckdb(args.duckdb_path, out_dir, args.marts)
    else:
        import os

        project = args.project or os.environ["VINTAGE_GCP_PROJECT"]
        total_bytes = export_from_bigquery(project, args.dataset, out_dir, args.marts)
        print(f"\nTotal bytes scanned across {len(args.marts)} mart exports: {total_bytes:,}")

    print("\nChecking every export against CONTRACTS.md...")
    problems_found = False
    for name in args.marts:
        path = out_dir / f"{name}.parquet"
        problems = contracts.check_mart(name, path)
        size = path.stat().st_size
        if problems:
            problems_found = True
            print(f"[FAIL] {name} ({size:,} bytes): {problems}")
        else:
            print(f"[OK] {name} ({size:,} bytes)")

    if problems_found:
        sys.exit(1)


if __name__ == "__main__":
    main()
