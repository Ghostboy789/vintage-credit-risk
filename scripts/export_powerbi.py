"""Export the tables behind the Power BI risk pack in ``powerbi/``.

    python scripts/export_powerbi.py --source fixtures   (default: fixtures)
    python scripts/export_powerbi.py --source real

Reads the published artefacts (``artefacts/*.json``) and the ``dim_date`` and
``metrics_monthly`` marts, and writes a small set of flat, already-aggregated
CSVs to ``powerbi/data``. Nothing here re-derives a number: every value is
copied from an artefact's metric object (value/ci_low/ci_high/n/ci_method) or
from an aggregated mart column. Loan-level marts (``fct_loan_month``,
``fct_scorecard_base``, ``fct_stage_inputs``, ...) are never read here and
never reach ``powerbi/data`` (CONTRACTS.md publication rule).

``--source fixtures`` reads ``tests/fixtures/{artefacts,marts}`` (synthetic;
every row's ``synthetic`` column is ``True``). ``--source real`` reads
``artefacts/`` and ``marts_out/`` under ``VINTAGE_DATA_ROOT``. Real export
happens once those exist; until then the fixtures export is what chat E
built and validated against, and ``powerbi/README.md`` says so.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from config import VINTAGE_DATA_ROOT

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT = REPO_ROOT / "powerbi" / "data"

ARTEFACT_NAMES = ["portfolio", "pd_models", "monitoring", "lgd_ead", "ecl", "capital"]

METRIC_KEYS = ("value", "ci_low", "ci_high", "n", "ci_method")


def _is_metric(obj: object) -> bool:
    return isinstance(obj, dict) and "value" in obj and "ci_method" in obj


def _flatten_row(row: dict, synthetic: bool) -> dict:
    """Expand every metric-object field in one row into value/lo/hi/n/method columns."""
    out: dict = {}
    for key, val in row.items():
        if _is_metric(val):
            out[key] = val["value"]
            out[f"{key}_lo"] = val["ci_low"]
            out[f"{key}_hi"] = val["ci_high"]
            out[f"{key}_n"] = val["n"]
            out[f"{key}_method"] = val["ci_method"]
        elif isinstance(val, (dict, list)):
            continue  # nested structures the report doesn't chart go unflattened
        else:
            out[key] = val
    out["synthetic"] = synthetic
    return out


def flatten_list(artefact: dict, field: str, synthetic: bool) -> pd.DataFrame:
    rows = artefact.get(field, [])
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([_flatten_row(r, synthetic) for r in rows])


def load_artefact(artefacts_dir: Path, name: str) -> dict:
    return json.loads((artefacts_dir / f"{name}.json").read_text())


# artefact -> {output table name: list field}
TABLE_SPEC: dict[str, dict[str, str]] = {
    "portfolio": {
        "vintage_curves": "vintage_curves",
        "roll_rates": "roll_rates",
        "roll_cure_rates": "roll_cure_rates",
        "default_cure_rates": "default_cure_rates",
        "sma": "sma",
        "prepayment": "prepayment",
        "loss_drivers": "loss_drivers",
        "default_definition_effect": "default_definition_effect",
        "portfolio_reconciliation": "reconciliation",
        "portfolio_pass_rules": "pass_rules",
    },
    "pd_models": {
        "scorecard_points": "points_table",
        "scorecard_grades": "grades",
        "scorecard_discrimination": "discrimination",
        "scorecard_calibration": "calibration",
        "scorecard_gini_drop": "gini_drop",
        "scorecard_samples": "samples",
        "scorecard_pass_rules": "pass_rules",
    },
    "monitoring": {
        "monitoring_psi": "score_psi",
        "monitoring_csi": "csi",
    },
    "lgd_ead": {
        "lgd_segments": "lgd_segments",
        "lgd_resolution_mix": "resolution_mix",
        "lgd_downturn": "downturn_lgd",
        "lgd_pass_rules": "pass_rules",
    },
    "ecl": {
        "ecl_by_date": "by_date",
        "ecl_scenario_totals": "scenario_totals",
        "ecl_stage_migration": "stage_migration",
        "ecl_pd_term_structure": "pd_term_structure",
        "ecl_backtest": "backtest",
        "ecl_stage2_drivers": "stage2_drivers",
        "ecl_pass_rules": "pass_rules",
    },
    "capital": {
        "capital_by_grade": "by_grade",
    },
}


def build_tables(artefacts_dir: Path, marts_dir: Path) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    meta_rows = []
    for artefact_name in ARTEFACT_NAMES:
        artefact = load_artefact(artefacts_dir, artefact_name)
        synthetic = bool(artefact["synthetic"])
        meta_rows.append(
            {
                "artefact": artefact_name,
                "synthetic": synthetic,
                "generated_at": artefact["generated_at"],
                "data_cutoff": artefact["data_cutoff"],
                "code_version": artefact["code_version"],
                "suppressed_cells": artefact["suppressed_cells"],
            }
        )
        for table_name, field in TABLE_SPEC.get(artefact_name, {}).items():
            df = flatten_list(artefact, field, synthetic)
            if not df.empty:
                tables[table_name] = df

    # Single-row tables that don't fit the list-of-metric-objects shape.
    pd_models = load_artefact(artefacts_dir, "pd_models")
    scaling = dict(pd_models["scaling"])
    scaling["synthetic"] = bool(pd_models["synthetic"])
    tables["scorecard_scaling"] = pd.DataFrame([scaling])

    capital = load_artefact(artefacts_dir, "capital")
    totals_row = {
        **capital["totals"],
        "status": capital["status"],
        "reporting_date": capital["reporting_date"],
    }
    totals = _flatten_row(totals_row, bool(capital["synthetic"]))
    tables["capital_totals"] = pd.DataFrame([totals])

    tables["artefact_metadata"] = pd.DataFrame(meta_rows)

    tables["dim_date"] = pd.read_parquet(marts_dir / "dim_date.parquet")
    tables["metrics_monthly"] = pd.read_parquet(marts_dir / "metrics_monthly.parquet")
    return tables


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", choices=["fixtures", "real"], default="fixtures")
    args = parser.parse_args()

    if args.source == "fixtures":
        fixtures_root = REPO_ROOT / "tests" / "fixtures"
        artefacts_dir = fixtures_root / "artefacts"
        marts_dir = fixtures_root / "marts"
    else:
        artefacts_dir = VINTAGE_DATA_ROOT / "artefacts"
        marts_dir = VINTAGE_DATA_ROOT / "marts_out"
        if not (artefacts_dir / "portfolio.json").exists():
            raise SystemExit(
                "No real artefacts yet under VINTAGE_DATA_ROOT/artefacts. "
                "Run with --source fixtures until chat R2/D2/G have merged real outputs."
            )

    OUT.mkdir(parents=True, exist_ok=True)
    tables = build_tables(artefacts_dir, marts_dir)
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
        print(f"{name:28s} {len(df):6d} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
