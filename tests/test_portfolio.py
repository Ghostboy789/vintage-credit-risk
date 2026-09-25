"""Tests for analysis/portfolio.py: the pre-registration gate, contract compliance and a few
hand-worked known-answer checks (VALIDATION_PLAN D4, D9, and the outcome-query ban)."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from analysis import portfolio as P
from tests import contracts as C

FIX = Path(__file__).resolve().parent / "fixtures"


# --- Pre-registration gate: no 2016+ outcomes before the out-of-time scoring is logged --------
def test_locked_without_oot_log(tmp_path):
    assert P.oot_scored(tmp_path) is False
    assert P.max_vintage(tmp_path) == P.LOCKED_MAX_VINTAGE


def test_locked_with_missing_models_out_dir(tmp_path):
    assert P.max_vintage(tmp_path / "does_not_exist") == P.LOCKED_MAX_VINTAGE


def test_locked_with_empty_log_file(tmp_path):
    (tmp_path / "oot_scoring_log.jsonl").write_text("", encoding="utf-8")
    assert P.oot_scored(tmp_path) is False


def test_locked_with_garbage_log_file(tmp_path):
    (tmp_path / "oot_scoring_log.jsonl").write_text("not json\n{also not json", encoding="utf-8")
    assert P.oot_scored(tmp_path) is False


def test_unlocked_once_a_real_scoring_call_is_logged(tmp_path):
    (tmp_path / "oot_scoring_log.jsonl").write_text(
        '{"model_id": "champion-v1", "scored_at": "2026-09-25T00:00:00Z"}\n', encoding="utf-8"
    )
    assert P.oot_scored(tmp_path) is True
    assert P.max_vintage(tmp_path) == P.FULL_MAX_VINTAGE


# --- Contract compliance on the synthetic fixtures ---------------------------------------------
@pytest.fixture(scope="module")
def fixture_artefact(tmp_path_factory):
    empty_models_out = tmp_path_factory.mktemp("models_out")  # no oot log: stays locked
    return P.build(FIX / "marts", empty_models_out, FIX / "raw")


def test_fixture_artefact_passes_the_contract(fixture_artefact):
    obj = dict(fixture_artefact)
    obj.pop("_max_vintage_year_included")
    obj["suppressed_cells"] = C.suppress_small_cells(obj)
    problems = C.check_artefact("portfolio", obj)
    assert problems == []


def test_fixture_run_is_locked_to_1999_2015(fixture_artefact):
    assert fixture_artefact["_max_vintage_year_included"] == 2015
    years = {r["vintage_year"] for r in fixture_artefact["vintage_curves"]}
    years |= {r["vintage_year"] for r in fixture_artefact["vintage_curves_annual"]}
    years |= {r["vintage_year"] for r in fixture_artefact["default_definition_effect"]}
    assert years and max(years) <= 2015


def test_reconciliation_covers_r1_through_r8(fixture_artefact):
    ids = {r["rule_id"] for r in fixture_artefact["reconciliation"]}
    assert ids == {"R1", "R2", "R3", "R4", "R7", "R8"}
    assert {r["rule_id"] for r in fixture_artefact["pass_rules"]} == ids


def test_r7_reconciliation_passes_on_fixtures(fixture_artefact):
    r7 = next(r for r in fixture_artefact["reconciliation"] if r["rule_id"] == "R7")
    assert r7["n_outside_tolerance"] == 0
    assert r7["max_abs_difference"] < 1e-9


# --- Unlocked run: 2016+ vintages appear once the gate opens -----------------------------------
def test_unlocked_run_includes_2016_plus(tmp_path):
    (tmp_path / "oot_scoring_log.jsonl").write_text(
        '{"model_id": "champion-v1"}\n', encoding="utf-8"
    )
    obj = P.build(FIX / "marts", tmp_path, FIX / "raw")
    assert obj["_max_vintage_year_included"] == 2024
    years = {r["vintage_year"] for r in obj["vintage_curves_annual"]}
    assert any(y >= 2016 for y in years)
    assert all(y <= 2024 for y in years)


# --- D4 cure rate: hand-worked on a tiny synthetic default-events frame ------------------------
def test_default_cure_rates_hand_worked():
    defaults = pd.DataFrame(
        {
            "loan_id": ["a", "b", "c", "d"],
            "definition": ["primary"] * 4,
            "vintage_year": [2005] * 4,
            "default_period": pd.to_datetime(
                ["2008-01-01", "2008-02-01", "2008-03-01", "2008-04-01"]
            ),
            "cure_period": pd.to_datetime([None, "2008-05-01", "2010-01-01", None]),
        }
    )
    rows = P.build_default_cure_rates({"defaults": defaults})
    assert len(rows) == 1
    row = rows[0]
    assert row["default_year"] == 2008
    # b cures 3 months later (within 12m); c cures ~22 months later (ever, not within 12m).
    assert row["cure_ever"]["n"] == 4
    assert row["cure_ever"]["value"] == pytest.approx(0.5)
    assert row["cure_12m"]["value"] == pytest.approx(0.25)


# --- comparable_months_on_book: the min, across compared vintage quarters, of each quarter's
# own largest fully-observed months on book -----------------------------------------------------
def test_comparable_months_on_book_is_the_binding_quarter():
    vc = pd.DataFrame(
        {
            "vintage_year": [2005, 2005, 2005, 2006, 2006],
            "vintage_quarter": ["2005Q1", "2005Q1", "2005Q1", "2006Q1", "2006Q1"],
            "months_on_book": [1, 2, 3, 1, 2],
            "n_loans": [100, 100, 100, 100, 100],
            "original_upb_total": [1e7] * 5,
            "cum_defaults": [0, 1, 2, 0, 1],
            "cum_default_rate": [0.0, 0.01, 0.02, 0.0, 0.01],
            "cum_net_loss": [0.0, 0.0, 0.0, 0.0, 0.0],
            "cum_loss_rate": [0.0, 0.0, 0.0, 0.0, 0.0],
            "fully_observed": [True, True, True, True, False],
        }
    )
    empty_loss = pd.DataFrame(
        {
            "loan_id": pd.Series(dtype=str),
            "vintage_year": pd.Series(dtype=int),
            "computed_loss": pd.Series(dtype=float),
            "months_to_resolution": pd.Series(dtype=float),
        }
    )
    empty_defaults = pd.DataFrame(
        {
            "loan_id": pd.Series(dtype=str),
            "definition": pd.Series(dtype=str),
            "default_months_on_book": pd.Series(dtype=float),
            "vintage_year": pd.Series(dtype=int),
        }
    )
    dim_loan = pd.DataFrame(
        {"loan_id": pd.Series(dtype=str), "vintage_quarter": pd.Series(dtype=str)}
    )
    rows, comparable = P.build_vintage_curves(
        {"vcurve": vc, "loss": empty_loss, "defaults": empty_defaults, "dim_loan": dim_loan}
    )
    assert comparable == 1  # 2006Q1's own max fully-observed point is 1
    assert len(rows) == 5


# --- D9 / roll rates: rates over to_state sum to 1 per (period_group, from_bucket) --------------
def test_roll_rates_sum_to_one_per_from_cell():
    dim_loan = pd.read_parquet(FIX / "marts" / "dim_loan.parquet")
    dim_date = pd.read_parquet(FIX / "marts" / "dim_date.parquet")
    roll = pd.read_parquet(FIX / "marts" / "fct_roll_rates.parquet")
    roll = roll[roll.vintage_year <= 2015]
    rows = P.build_roll_rates({"roll": roll, "dim_date": dim_date, "dim_loan": dim_loan})
    by_cell = {}
    for r in rows:
        if r["rate"]["value"] is None:
            continue
        by_cell.setdefault((r["period_group"], r["from_bucket"]), 0.0)
        by_cell[(r["period_group"], r["from_bucket"])] += r["rate"]["value"]
    for total in by_cell.values():
        assert total == pytest.approx(1.0, abs=1e-9)


def test_prepayment_cpr_matches_smm_formula(tmp_path):
    # Computed from fct_loan_month.exit_type / at_risk_at_start directly, not from
    # fct_roll_rates.to_state: the real build's fct_roll_rates never carries an exit-type
    # to_state (every exit lands in 'missing' instead of 'prepaid'/'matured'/etc, verified
    # against dim_loan.exit_type and fct_loan_month.exit_type, which are both correct).
    flm = pd.DataFrame(
        {
            "loan_id": [f"l{i}" for i in range(1000)],
            "period": pd.to_datetime(["2010-01-01"] * 1000),
            "vintage_year": [2005] * 1000,
            "at_risk_at_start": [True] * 1000,
            "exit_type": ["prepaid"] * 100 + [None] * 900,
        }
    )
    flm.to_parquet(tmp_path / "fct_loan_month.parquet")
    rows = P.build_prepayment(tmp_path, 2024)
    assert len(rows) == 1
    smm = 100 / 1000
    expected_cpr = 1 - (1 - smm) ** 12
    assert rows[0]["cpr"]["value"] == pytest.approx(expected_cpr)


def test_loss_curve_draws_are_zero_before_any_loss_and_stable_after():
    loss = pd.DataFrame({"disposal_mob": [10, 10], "computed_loss": [1000.0, 2000.0]})
    draws = P.loss_curve_draws(loss, n_loans=1000, mobs=np.array([1, 10, 20]))
    assert (draws[:, 0] == 0).all()
    # by month 20 every draw has seen both losses' full population-average contribution in
    # expectation; the mean across 1000 draws should be close to the population total (3000).
    assert draws[:, 2].mean() == pytest.approx(3000.0, rel=0.2)
