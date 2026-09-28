"""export_powerbi.py: fixtures export only aggregates, matches the artefacts exactly."""

import json
import sys
from pathlib import Path

import numpy as np
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
            env={**os.environ, "VINTAGE_DATA_ROOT": empty_root},
            capture_output=True,
            text=True,
        )
    assert result.returncode != 0
    assert "No real artefacts yet" in result.stderr


def test_committed_export_matches_the_published_artefacts_and_marts():
    """powerbi/data/ is exactly what the export builds from artefacts/ and marts_out/."""
    from config import VINTAGE_DATA_ROOT

    artefacts, marts = VINTAGE_DATA_ROOT / "artefacts", VINTAGE_DATA_ROOT / "marts_out"
    if not (marts / "metrics_monthly.parquet").exists():
        import pytest

        pytest.skip("marts_out/ not present")
    tables = build_tables(artefacts, marts)
    data_dir = REPO_ROOT / "powerbi" / "data"
    assert {p.stem for p in data_dir.glob("*.csv")} == set(tables)
    for name, df in tables.items():
        got = pd.read_csv(data_dir / f"{name}.csv")
        assert len(got) == len(df), name
        assert list(got.columns) == list(df.columns), name
        for col in df.select_dtypes("number").columns:
            ok = np.allclose(got[col].fillna(-1), df[col].fillna(-1), rtol=1e-9, atol=0)
            assert ok, (name, col)
    assert not any(t["synthetic"].any() for n, t in tables.items() if "synthetic" in t)


def test_semantic_model_loads_in_desktop():
    """Guards the three shapes Desktop refuses to load: tables without an import
    partition, DAX-calculated dimension tables, and relationships whose
    one-side (toColumn) is not a dimension."""
    model = REPO_ROOT / "powerbi" / "Vintage.SemanticModel" / "definition"
    for tmdl in (model / "tables").glob("*.tmdl"):
        text = tmdl.read_text(encoding="utf-8")
        assert "= m\n\t\tmode: import" in text, f"{tmdl.stem} has no import partition"
        assert "= calculated" not in text, f"{tmdl.stem} is a calculated table"
    for line in (model / "relationships.tmdl").read_text(encoding="utf-8").splitlines():
        if "toColumn:" in line:
            assert line.split("toColumn:")[1].strip().startswith("'Dim "), line
