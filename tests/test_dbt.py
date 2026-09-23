"""Builds the dbt project on the "ci" target (DuckDB, synthetic fixtures) and checks the
output marts against tests/contracts.py. No real data and no BigQuery: this is the test CI runs.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from extract.build_parquet import build_parquet  # noqa: E402
from scripts.export_marts import MART_NAMES, export_from_duckdb  # noqa: E402
from tests import contracts  # noqa: E402

CI_YEARS = [2005, 2007, 2019, 2022]
# The repo ships its own profiles.yml (dbt/profiles.yml, env-var only, no secrets or machine
# paths), so these tests work from a plain checkout with no external dbt config. An env var
# still wins if one happens to be set (a real dev machine may point DBT_PROFILES_DIR elsewhere).
PROFILES_DIR = os.environ.get("DBT_PROFILES_DIR") or str(REPO_ROOT / "dbt")


def _dbt_executable() -> str:
    """Resolves the `dbt` console script next to the running interpreter first, so this works
    whether or not a venv is activated (activation only changes PATH, not sys.executable).
    Falls back to PATH, then skips with a clear reason if dbt isn't installed at all."""
    candidate = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")
    if candidate.exists():
        return str(candidate)
    found = shutil.which("dbt")
    if found:
        return found
    pytest.skip("dbt is not installed for this interpreter", allow_module_level=True)


DBT_BIN = _dbt_executable()


@pytest.fixture(scope="session")
def ci_build(tmp_path_factory):
    """Runs `dbt build --target ci` once for the whole test session and returns the duckdb path."""
    tmp_root = tmp_path_factory.mktemp("dbt_ci")
    parquet_dir = tmp_root / "data" / "parquet"
    build_parquet(REPO_ROOT / "tests" / "fixtures" / "raw", parquet_dir)

    duckdb_path = tmp_root / "vintage_ci.duckdb"
    env = dict(os.environ)
    env["VINTAGE_CI_PARQUET_ROOT"] = str(parquet_dir)
    env["VINTAGE_CI_MODELS_ROOT"] = str(REPO_ROOT / "tests" / "fixtures" / "models_out")
    env["VINTAGE_CI_DB"] = str(duckdb_path)
    env["DBT_PROFILES_DIR"] = PROFILES_DIR

    result = subprocess.run(
        [
            DBT_BIN,
            "build",
            "--target",
            "ci",
            "--project-dir",
            str(REPO_ROOT / "dbt"),
            "--profiles-dir",
            PROFILES_DIR,
            "--vars",
            json.dumps({"vintage_years": CI_YEARS}),
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(f"dbt build --target ci failed:\n{result.stdout}\n{result.stderr}")
    return duckdb_path


MARTS_WITH_KEYS = {
    "dim_date": ["month"],
    "dim_loan": ["loan_id"],
    "fct_loan_month": ["loan_id", "period"],
    "fct_default_events": ["loan_id", "definition"],
    "fct_loss_events": ["loan_id"],
    "fct_vintage_curve": ["vintage_quarter", "months_on_book"],
    "fct_roll_rates": ["period", "vintage_year", "from_bucket", "from_forbearance", "to_state"],
    "fct_scorecard_base": ["loan_id"],
    "fct_stage_inputs": ["loan_id", "reporting_date"],
    "metrics_monthly": ["period"],
}


def test_ci_build_succeeds(ci_build):
    assert ci_build.exists()


@pytest.mark.parametrize("mart", sorted(MARTS_WITH_KEYS))
def test_mart_has_rows_and_unique_keys(ci_build, mart):
    con = duckdb.connect(str(ci_build), read_only=True)
    try:
        n = con.execute(f"select count(*) from main_marts.{mart}").fetchone()[0]
        assert n > 0, f"{mart} is empty"
        keys = MARTS_WITH_KEYS[mart]
        key_list = ", ".join(keys)
        dupes = con.execute(
            f"select count(*) from (select {key_list} from main_marts.{mart} "
            f"group by {key_list} having count(*) > 1)"
        ).fetchone()[0]
        assert dupes == 0, f"{mart} has {dupes} duplicate keys on {keys}"
    finally:
        con.close()


def test_no_negative_balances(ci_build):
    con = duckdb.connect(str(ci_build), read_only=True)
    try:
        n = con.execute(
            "select count(*) from main_marts.fct_loan_month where current_upb < 0"
        ).fetchone()[0]
        assert n == 0
    finally:
        con.close()


def test_at_most_one_first_default_per_loan(ci_build):
    con = duckdb.connect(str(ci_build), read_only=True)
    try:
        n = con.execute(
            "select count(*) from ("
            "  select loan_id from main_marts.fct_loan_month"
            "  where is_first_default_month group by loan_id having count(*) > 1"
            ")"
        ).fetchone()[0]
        assert n == 0
    finally:
        con.close()


def test_metricflow_manifest_parses(ci_build):
    """dbt itself is the semantic-model/metric validator here: `dbt parse` (which `dbt build`
    already ran as part of the ci_build fixture) fails loudly on a bad measure reference, an
    invalid metric type, or a missing time spine -- all of which this project hit and fixed
    while wiring models/semantic/_semantic.yml. The separate `mf validate-configs` / `mf query`
    CLI (dbt-metricflow 0.15.0) crashes on this Windows checkout with an unrelated internal
    error ("cannot use a string pattern on a bytes-like object", no --target flag either) before
    it gets far enough to check the config, so it is not used as the test here.
    """
    assert (REPO_ROOT / "dbt" / "target" / "semantic_manifest.json").exists()


def test_metrics_match_metrics_monthly(ci_build):
    """R7: each MetricFlow metric's own formula, evaluated directly in SQL, equals the matching
    metrics_monthly column for every month. This checks the semantic model's measure
    expressions (models/semantic/_semantic.yml) against metrics_monthly's independently written
    aggregation (models/marts/metrics_monthly.sql) -- the two are meant to agree by definition,
    but were written separately, so this is a real cross-check, not a tautology.
    """
    con = duckdb.connect(str(ci_build), read_only=True)
    try:
        computed = con.execute(
            """
            select
                lm.period,
                count(case when lm.zero_balance_code is null then 1 end) as active_loans,
                sum(case when lm.zero_balance_code is null then lm.current_upb end) as total_upb,
                sum(case when lm.zero_balance_code is null
                    and lm.dpd_bucket in ('dpd_30','dpd_60','dpd_90p','reo')
                    then lm.current_upb end) as dpd30p_upb,
                sum(case when lm.zero_balance_code is null and lm.dpd_bucket in ('dpd_90p','reo')
                    then lm.current_upb end) as dpd90p_upb,
                sum(case when lm.at_risk_at_start then 1 else 0 end) as at_risk,
                sum(case when lm.is_first_default_month then 1 else 0 end) as new_defaults
            from main_marts.fct_loan_month lm
            group by 1
            """
        ).fetchdf()
        reference = con.execute("select * from main_marts.metrics_monthly").fetchdf()
    finally:
        con.close()

    def same(a, b):
        # A month with no matching loan-months can come back null on the ad-hoc side even
        # though metrics_monthly coalesces to 0; treat null and 0 as the same value here.
        return (a.fillna(0) == b.fillna(0)).all()

    merged = computed.merge(reference, on="period", suffixes=("_mf", "_ref"), how="inner")
    assert len(merged) == len(reference) == len(computed)
    assert same(merged["active_loans"], merged["n_active_loans"])
    assert same(merged["total_upb_mf"], merged["total_upb_ref"])
    assert same(merged["dpd30p_upb"], merged["upb_dpd30p"])
    assert same(merged["dpd90p_upb"], merged["upb_dpd90p"])
    assert same(merged["at_risk"], merged["n_at_risk_start"])
    assert same(merged["new_defaults"], merged["n_new_defaults"])


def test_exported_marts_pass_contracts(ci_build, tmp_path):
    """scripts/export_marts.py's duckdb path, exercised end to end: export every mart from the
    ci build and check each one with tests/contracts.py -- the same check the real BigQuery
    export runs.
    """
    out_dir = tmp_path / "marts_out"
    out_dir.mkdir()
    export_from_duckdb(str(ci_build), out_dir, MART_NAMES)
    for name in MART_NAMES:
        problems = contracts.check_mart(name, out_dir / f"{name}.parquet")
        assert problems == [], f"{name}: {problems}"


def test_roll_rates_sum_to_one(ci_build):
    con = duckdb.connect(str(ci_build), read_only=True)
    try:
        bad = con.execute(
            "select count(*) from ("
            "  select period, vintage_year, from_bucket, from_forbearance, sum(roll_rate) as total"
            "  from main_marts.fct_roll_rates"
            "  group by 1, 2, 3, 4"
            "  having abs(total - 1.0) > 1e-6"
            ")"
        ).fetchone()[0]
        assert bad == 0
    finally:
        con.close()
