"""export_powerbi.py: fixtures export only aggregates, matches the artefacts exactly."""

import json
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from scripts.export_powerbi import build_tables  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"


def test_no_loan_level_column_reaches_the_export():
    tables = build_tables(FIXTURES / "artefacts", FIXTURES / "marts")
    for name, df in tables.items():
        assert "loan_id" not in df.columns, f"{name} carries a loan identifier"


def test_every_table_is_marked_synthetic_from_fixtures():
    tables = build_tables(FIXTURES / "artefacts", FIXTURES / "marts")
    for name, df in tables.items():
        if name in ("dim_date", "metrics_monthly"):
            continue  # marts have no synthetic flag of their own; carried by the fixtures dir
        assert df["synthetic"].all(), f"{name} has a row not flagged synthetic"


def test_vintage_curve_values_match_the_artefact_exactly():
    portfolio = json.loads((FIXTURES / "artefacts" / "portfolio.json").read_text())
    tables = build_tables(FIXTURES / "artefacts", FIXTURES / "marts")
    df = tables["vintage_curves"]
    first = portfolio["vintage_curves"][0]
    row = df.iloc[0]
    assert row["cum_default_rate"] == first["cum_default_rate"]["value"]
    assert row["cum_default_rate_lo"] == first["cum_default_rate"]["ci_low"]
    assert row["cum_default_rate_n"] == first["cum_default_rate"]["n"]


def test_metrics_monthly_row_count_matches_the_mart():
    mart = pd.read_parquet(FIXTURES / "marts" / "metrics_monthly.parquet")
    tables = build_tables(FIXTURES / "artefacts", FIXTURES / "marts")
    assert len(tables["metrics_monthly"]) == len(mart)


def test_no_local_machine_path_in_the_committed_pbip():
    """The DataFolder parameter must point at the GitHub raw URL, never a local disk path
    (a known Power BI trap: a local DataFolder would commit this machine's own directory tree)."""
    import re

    windows_absolute_path = re.compile(r"[A-Za-z]:[\\/](Users|[A-Za-z0-9 _.-]+[\\/])")
    powerbi_dir = REPO_ROOT / "powerbi"
    checked = 0
    for path in powerbi_dir.rglob("*"):
        if path.is_file() and path.suffix in (".tmdl", ".json", ".pbip"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            checked += 1
            match = windows_absolute_path.search(text)
            assert match is None, f"{path} contains a local machine path ({match.group()!r})"
    assert checked > 10, "expected to check the semantic model and report files"


def test_real_mode_refuses_without_artefacts():
    import os
    import subprocess
    import tempfile

    d_temp = Path(os.environ.get("VINTAGE_DUCKDB_TEMP", REPO_ROOT.parent / "vintage-cache" / "tmp"))
    d_temp.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=d_temp) as empty_root:
        result = subprocess.run(
            [sys.executable, "-m", "scripts.export_powerbi", "--source", "real"],
            cwd=REPO_ROOT,
            env={"VINTAGE_DATA_ROOT": empty_root, **os.environ},
            capture_output=True,
            text=True,
        )
    assert result.returncode != 0
    assert "No real artefacts yet" in result.stderr
