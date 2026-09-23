"""Load data/parquet/*.parquet into a BigQuery sandbox dataset (raw), one table per file.

Uses the `bq` CLI (from the Google Cloud SDK already on PATH) rather than the
google-cloud-bigquery Python package, so no new dependency is needed. Auth is
Application Default Credentials under CLOUDSDK_CONFIG -- no service-account key file.

Dry run: BigQuery load jobs have no cost-estimate dry-run of their own (that's a query-job
concept), so "dry run" here means estimating the *logical* (uncompressed) bytes the load would
add to the project's storage -- the number that counts against the sandbox's 10 GB storage quota
-- from each Parquet file's own row-group metadata, before touching BigQuery at all.

If that estimate is at or over BUDGET_BYTES, this script does NOT load everything: it falls back
to YEARS_IF_OVER_BUDGET (2005-2008, the pre-crisis/crisis vintages, plus 2020-2021, the COVID
forbearance window -- the years most relevant to the risk models this project builds), loading
only those years' origination and performance tables. As of the 27-year sample dataset, the
actual logical-byte estimate is ~1.7 GB against a 10 GB budget, so this fallback has not been
exercised -- every year loads.

Safe to re-run: each table load uses `bq load --replace` (BigQuery's WRITE_TRUNCATE), so a table
is fully overwritten rather than appended to. Useful since the sandbox's tables expire after 60
days and this script is how they'd be refreshed.

After loading, every table's row count is checked against data/MANIFEST.json's "rows" field for
that file, and any mismatch is reported (not silently ignored).
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import VINTAGE_DATA_ROOT  # noqa: E402

# Windows only has bq.cmd on PATH, and subprocess (without shell=True) won't apply PATHEXT to a
# bare "bq" -- resolve the real executable once, up front.
BQ = shutil.which("bq") or "bq"

BUDGET_BYTES = 10_000_000_000  # sandbox project storage quota, 10 GB
DATASET = "raw"
YEARS_IF_OVER_BUDGET = [2005, 2006, 2007, 2008, 2020, 2021]


def estimate_logical_bytes(parquet_dir: Path) -> int:
    """Sum each Parquet file's uncompressed row-group byte size (pyarrow metadata only,
    no BigQuery call) -- an estimate of the logical bytes BigQuery storage would report."""
    total = 0
    for path in sorted(parquet_dir.glob("*.parquet")):
        md = pq.ParquetFile(path).metadata
        for rg in range(md.num_row_groups):
            total += md.row_group(rg).total_byte_size
    return total


def project() -> str:
    proj = os.environ.get("VINTAGE_GCP_PROJECT")
    if not proj:
        raise SystemExit("VINTAGE_GCP_PROJECT is not set -- source the project's env file first.")
    return proj


def bq(*args: str) -> str:
    result = subprocess.run(
        [BQ, *args], capture_output=True, text=True, check=True, encoding="utf-8"
    )
    return result.stdout


def ensure_dataset(proj: str) -> None:
    existing = json.loads(bq("ls", "--format=json", f"--project_id={proj}") or "[]")
    if any(d["datasetReference"]["datasetId"] == DATASET for d in existing):
        return
    bq("mk", "--dataset", "--location=US", f"{proj}:{DATASET}")


def load_table(proj: str, parquet_path: Path) -> None:
    table_name = parquet_path.stem  # e.g. orig_2005, perf_2005
    bq(
        "load", "--replace", "--source_format=PARQUET",
        f"{proj}:{DATASET}.{table_name}", str(parquet_path),
    )


def table_row_count(proj: str, table_name: str) -> int:
    out = bq(
        "query", "--use_legacy_sql=false", "--format=csv",
        f"SELECT count(*) FROM `{proj}.{DATASET}.{table_name}`",
    )
    lines = [line for line in out.strip().splitlines() if line]
    return int(lines[-1])


def main() -> None:
    proj = project()
    parquet_dir = VINTAGE_DATA_ROOT / "data" / "parquet"
    manifest_path = VINTAGE_DATA_ROOT / "data" / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())

    logical_bytes = estimate_logical_bytes(parquet_dir)
    pct = 100 * logical_bytes / BUDGET_BYTES
    print(
        f"Estimated logical bytes: {logical_bytes:,} ({logical_bytes / 1e9:.2f} GB), "
        f"{pct:.1f}% of the {BUDGET_BYTES / 1e9:.0f} GB sandbox storage budget."
    )

    files = sorted(parquet_dir.glob("*.parquet"))
    if logical_bytes >= BUDGET_BYTES:
        print(
            f"Over budget -- loading only {YEARS_IF_OVER_BUDGET} "
            "(pre-crisis/crisis vintages + COVID forbearance window)."
        )
        files = [f for f in files if int(f.stem.split("_")[-1]) in YEARS_IF_OVER_BUDGET]

    ensure_dataset(proj)

    mismatches = []
    for path in files:
        table_name = path.stem
        print(f"Loading {table_name} ...")
        load_table(proj, path)

        expected = manifest["files"].get(path.name, {}).get("rows")
        actual = table_row_count(proj, table_name)
        status = "OK" if actual == expected else "MISMATCH"
        print(f"  {table_name}: manifest={expected} bigquery={actual} [{status}]")
        if actual != expected:
            mismatches.append((table_name, expected, actual))

    if mismatches:
        print(f"\n{len(mismatches)} table(s) did not match the manifest row count:")
        for name, expected, actual in mismatches:
            print(f"  {name}: expected {expected}, got {actual}")
        raise SystemExit(1)

    print(f"\nAll {len(files)} table(s) loaded into {proj}:{DATASET}, row counts match manifest.")


if __name__ == "__main__":
    main()
