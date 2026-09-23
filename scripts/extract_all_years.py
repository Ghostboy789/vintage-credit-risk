"""Unzip and convert every yearly sample_YYYY.zip in data/raw/ into Parquet, one year at a time.

The zips together are ~1.1 GB, but a single year's performance file unzips to several hundred MB
(2005 alone is 447 MB), so this only ever has one year unzipped on disk at once: unzip ->
convert -> delete the unzipped text -> next year. data/raw/*.zip is never touched or deleted.

Writes/overwrites data/MANIFEST.json with the combined manifest across all years. Safe to re-run
(each run rebuilds the whole manifest from data/raw/, and re-converts every year).
"""

import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "extract"))
import build_parquet  # noqa: E402

from config import VINTAGE_DATA_ROOT  # noqa: E402


def main() -> None:
    raw_dir = VINTAGE_DATA_ROOT / "data" / "raw"
    parquet_dir = VINTAGE_DATA_ROOT / "data" / "parquet"
    manifest_path = VINTAGE_DATA_ROOT / "data" / "MANIFEST.json"
    duckdb_temp = build_parquet.os.environ.get("VINTAGE_DUCKDB_TEMP")

    scratch_root = Path(
        build_parquet.os.environ.get("TEMP", VINTAGE_DATA_ROOT / "_extract_scratch")
    )
    unzip_dir = scratch_root / "vintage_extract_year"

    zips = sorted(raw_dir.glob("sample_[0-9][0-9][0-9][0-9].zip"))
    if not zips:
        print(f"No sample_YYYY.zip files found under {raw_dir}")
        return

    manifest: dict = {"layout_version": build_parquet.LAYOUT_VERSION, "files": {}}
    for zip_path in zips:
        if unzip_dir.exists():
            shutil.rmtree(unzip_dir)
        unzip_dir.mkdir(parents=True)

        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(unzip_dir)

        year_manifest = build_parquet.build_parquet(unzip_dir, parquet_dir, duckdb_temp)
        manifest["files"].update(year_manifest["files"])
        for name, entry in year_manifest["files"].items():
            print(f"{name}: {entry['rows']} rows, {entry['loan_count']} loans")

        shutil.rmtree(unzip_dir)

    manifest_path.write_text(build_parquet.json.dumps(manifest, indent=2, sort_keys=True))
    print(f"Wrote {len(manifest['files'])} Parquet file(s) -> {manifest_path}")


if __name__ == "__main__":
    main()
