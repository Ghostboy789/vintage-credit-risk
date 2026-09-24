"""PD engine: known-answer statistics, the scorecard's mechanical rules, the once-only out-of-time
scoring, and an end-to-end run on the SYNTHETIC fixtures (tests/fixtures/)."""

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import VINTAGE_DATA_ROOT  # noqa: E402
from models.pd import metrics as mt  # noqa: E402
from models.pd import run as pdrun  # noqa: E402
from models.pd import scorecard as sc  # noqa: E402
from tests import contracts  # noqa: E402

MARTS = ROOT / "tests" / "fixtures" / "marts"


# ---------------------------------------------------------------------------------------------
# Known answers
# ---------------------------------------------------------------------------------------------
def test_woe_iv_hand_computed():
    # Non-defaults 60/40 (shares .6/.4), defaults 10/30 (shares .25/.75).
    woe, iv = sc.woe_iv([60, 40], [10, 30])
    assert woe == pytest.approx([math.log(0.6 / 0.25), math.log(0.4 / 0.75)])
    assert woe == pytest.approx([0.875469, -0.628609], abs=1e-6)
    assert iv == pytest.approx(0.35 * 0.875469 + 0.35 * 0.628609, abs=1e-6)  # 0.526427
    # A bin with no defaults has no finite WoE and adds nothing to the IV.
    woe, iv = sc.woe_iv([50, 50, 10], [10, 10, 0])
    assert np.isnan(woe[2]) and np.isfinite(iv)


def test_woe_matches_optbinning_table_on_fixture():
    """Our WoE equals ln(non-default share / default share); optbinning 1.0.0's table uses the
    same sign, so the conversion is the identity (recorded in docs/PD_MODELS.md)."""
    from optbinning import OptimalBinning

    base = pd.read_parquet(MARTS / "fct_scorecard_base.parquet")
    t = base[base["sample"] == "dev_train"]
    y = t["default_12m"].astype(int).to_numpy()
    b = sc.fit_binning(sc.feature_values(t, "fico"), y, "fico")
    ob = OptimalBinning("fico", monotonic_trend="descending", **sc.BINNING_PARAMS)
    table = ob.fit(t["fico"].to_numpy(float), y).binning_table.build()
    n_regular = len(b["bins"]) - 1
    assert [x["woe_raw"] for x in b["bins"][:-1]] == pytest.approx(
        table["WoE"].iloc[:n_regular].astype(float).tolist()
    )
    assert b["iv"] == pytest.approx(float(ob.binning_table.iv))


def test_pdo_scaling_textbook():
    # 600 points at 50:1 good:bad odds, 20 points to double the odds.
    assert sc.FACTOR == pytest.approx(28.8539, abs=1e-4)
    assert sc.OFFSET == pytest.approx(487.1229, abs=1e-4)
    assert sc.pd_from_score(600) == pytest.approx(1 / 51)
    assert sc.pd_from_score(620) == pytest.approx(1 / 101)
    assert sc.pd_from_score(580) == pytest.approx(1 / 26)
    # Two features, beta -1, WoE 0, intercept -ln(50): each attribute carries half of 600.
    assert sc.points(-1.0, 0.0, -math.log(50), 2) == 300
    # One unit of WoE with beta -1 is worth factor points.
    assert sc.points(-1.0, 1.0, -math.log(50), 1) == round(600 + sc.FACTOR)
    assert sc.round_half_away(2.5) == 3 and sc.round_half_away(-2.5) == -3


def test_ks_gini_known_case():
    risk, y = [1, 2, 3, 4], [0, 0, 1, 1]
    assert mt.auc_ks(risk, y) == pytest.approx((1.0, 1.0))
    # One tie between a default and a non-default: AUC 3.5/4, Gini 0.75, KS 0.5.
    risk, y = [1, 2, 2, 3], [0, 1, 0, 1]
    auc, ks = mt.auc_ks(risk, y)
    assert auc == pytest.approx(0.875) and 2 * auc - 1 == pytest.approx(0.75)
    assert ks == pytest.approx(0.5)
    rng = np.random.default_rng(1)
    r, t = rng.integers(0, 50, 2000), rng.integers(0, 2, 2000)
    assert mt.auc_ks(r, t)[0] == pytest.approx(roc_auc_score(t, r))


def test_psi_zero_on_identical_distributions():
    counts = np.array([120, 80, 0, 300])
    assert mt.psi(counts, counts) == 0.0
    assert mt.psi(counts, counts * 3) == pytest.approx(0.0)
    # Hand check: shares .5/.5 against .25/.75.
    assert mt.psi([50, 50], [25, 75]) == pytest.approx(
        (0.25 - 0.5) * math.log(0.5) + (0.75 - 0.5) * math.log(1.5)
    )


def test_decile_bins_follow_s5():
    ref = np.arange(1, 101)
    edges = mt.decile_edges(ref)
    assert list(edges) == [10, 20, 30, 40, 50, 60, 70, 80, 90]
    assert list(mt.decile_bins([10, 11, 90, 91], edges)) == [0, 1, 8, 9]
    # Repeated edges are dropped: integer scores with few values give fewer bins.
    assert len(mt.decile_edges([1] * 50 + [2] * 50)) == 2


def test_jeffreys_and_wilson():
    assert mt.jeffreys(0, 50)[0] == 0.0 and mt.jeffreys(50, 50)[1] == 1.0
    lo, hi = mt.jeffreys(10, 100)
    assert lo < 0.1 < hi and lo == pytest.approx(0.0526, abs=1e-3)
    lo, hi = mt.wilson(10, 100)
    assert (lo, hi) == pytest.approx((0.0552, 0.1744), abs=1e-4)


# ---------------------------------------------------------------------------------------------
# Mechanical rules
# ---------------------------------------------------------------------------------------------
def _grade_data(spec):
    """Loans at the middle of each master-scale band: {letter: (n loans, n defaults)}."""
    pds, ys = [], []
    for g, lo, hi in sc.MASTER_SCALE:
        n, d = spec.get(g, (0, 0))
        pds += [(lo + hi) / 2] * n
        ys += [1] * d + [0] * (n - d)
    return np.array(pds), np.array(ys)


def test_grade_merge_outer_grades_move_towards_d():
    ok = (2000, 30)
    pd_, y = _grade_data({"A": (5, 0), "B": ok, "C": ok, "D": ok, "E": ok, "F": ok, "G": (10, 5)})
    grades = {g["grade"]: g for g in sc.fit_grades(pd_, y)}
    assert grades["A"]["merged_into"] == "B" and grades["G"]["merged_into"] == "F"
    assert grades["B"]["pd_low"] == 0.0 and grades["B"]["score_max"] is None
    assert grades["F"]["pd_high"] == 1.0 and grades["F"]["score_min"] is None
    assert list(sc.grade_of(np.array([0.0005, 0.5]), list(grades.values()))) == ["B", "F"]


def test_grade_merge_chains_and_d_rule():
    ok = (2000, 30)
    # A fails, merges into B; B (with A) still fails, merges into C: A must follow to C.
    pd_, y = _grade_data({"A": (5, 0), "B": (5, 0), "C": ok, "D": ok, "E": ok, "F": ok, "G": ok})
    g = {x["grade"]: x for x in sc.fit_grades(pd_, y)}
    assert g["A"]["merged_into"] == "C" and g["B"]["merged_into"] == "C"
    # D fails: it joins the neighbour with more dev_train loans...
    pd_, y = _grade_data(
        {"A": ok, "B": ok, "C": (3000, 30), "D": (10, 0), "E": ok, "F": ok, "G": ok}
    )
    assert {x["grade"]: x for x in sc.fit_grades(pd_, y)}["D"]["merged_into"] == "C"
    pd_, y = _grade_data(
        {"A": ok, "B": ok, "C": ok, "D": (10, 0), "E": (3000, 30), "F": ok, "G": ok}
    )
    assert {x["grade"]: x for x in sc.fit_grades(pd_, y)}["D"]["merged_into"] == "E"
    # ...and C on a tie.
    pd_, y = _grade_data({"A": ok, "B": ok, "C": ok, "D": (10, 0), "E": ok, "F": ok, "G": ok})
    assert {x["grade"]: x for x in sc.fit_grades(pd_, y)}["D"]["merged_into"] == "C"


def test_score_ranges_match_pd_bands():
    pd_, y = _grade_data({g: (2000, 30) for g in "ABCDEFG"})
    for g in sc.fit_grades(pd_, y):
        if g["score_min"] is not None:
            assert (
                sc.pd_from_score(g["score_min"])
                < g["pd_high"]
                <= sc.pd_from_score(g["score_min"] - 1)
            )
        if g["score_max"] is not None:
            assert (
                sc.pd_from_score(g["score_max"])
                >= g["pd_low"]
                > sc.pd_from_score(g["score_max"] + 1)
            )


def test_tie_breaks_keep_the_earlier_candidate():
    s = pd.Series({"ltv_pct": 0.5, "fico": 0.5, "dti_pct": 0.1})
    assert sc._drop_largest(s) == "ltv_pct"


def test_monotonic_check_directions():
    assert sc._is_monotonic([-1, 0, 1], "descending")  # fico: WoE rises with the value
    assert not sc._is_monotonic([-1, 0, 1], "ascending")
    assert sc._is_monotonic([1, 0, -1], "auto_asc_desc")
    assert not sc._is_monotonic([1, -1, 0], "auto_asc_desc")


def test_d1a_counts(tmp_path):
    base = pd.DataFrame(
        {
            "loan_id": ["a", "b", "c", "d"],
            "sample": ["dev_train"] * 4,
            "default_months_on_book": [10.0, 10.0, None, None],
        }
    )
    lm = pd.DataFrame(
        {
            "loan_id": ["a", "a", "b", "c", "d"],
            "months_on_book": [5, 6, 12, 7, 3],
            "modified": [True, True, True, True, False],
        }
    )
    path = tmp_path / "lm.parquet"
    lm.to_parquet(path)
    row = pdrun.d1a_rows(base, path)[0]
    # a: modified at 5 before default at 10; b: modified after default; c: modified, no default.
    assert row["modified_before_default"]["value"] == 2
    assert row["primary_defaults"]["value"] == 2
    assert row["ratio"]["value"] == 1.0 and row["ratio"]["ci_low"] is None


def test_would_be_sample():
    f = pd.DataFrame(
        {
            "loan_id": ["F05Q1S000001", "x", "y", "z", "w"],
            "vintage_year": [2005, 2016, 2019, 2019, 2025],
            "first_payment_date": pd.to_datetime(
                ["2005-03-01", "2016-03-01", "2019-03-01", "2019-04-01", "2025-03-01"]
            ),
        }
    )
    got = list(pdrun.would_be_sample(f))
    assert got[0] in ("dev_train", "dev_test")
    assert got[1:] == ["gap", "oot", "covid", "out_of_scope"]


# ---------------------------------------------------------------------------------------------
# Out-of-time scoring happens once, through one function (VALIDATION_PLAN P3)
# ---------------------------------------------------------------------------------------------
def test_only_the_guarded_function_may_score_oot():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "models" / "pd").glob("*.py"))
    assert src.count("allow_oot=True)") == 2  # the scorecard and challenger calls
    body = (ROOT / "models" / "pd" / "run.py").read_text(encoding="utf-8")
    guarded = body.split("def score_out_of_time", 1)[1].split("\ndef ", 1)[0]
    assert guarded.count("allow_oot=True)") == 2


def test_real_oot_log_has_one_call_per_model():
    """Fails if the real out-of-time sample was ever scored twice with the same scorecard."""
    entries = pdrun.read_oot_log(Path(VINTAGE_DATA_ROOT) / "models_out")
    ids = [e["model_id"] for e in entries]
    assert len(ids) == len(set(ids)), f"out-of-time scored more than once: {ids}"


@pytest.fixture(scope="module")
def fixture_run(tmp_path_factory):
    out = tmp_path_factory.mktemp("pd")
    res = pdrun.run(
        MARTS / "fct_scorecard_base.parquet",
        MARTS / "dim_loan.parquet",
        MARTS / "fct_loan_month.parquet",
        out / "artefacts",
        out / "models_out",
    )
    return out, res


def test_scoring_refuses_oot_outside_the_guard(fixture_run):
    _, res = fixture_run
    base = pd.read_parquet(MARTS / "fct_scorecard_base.parquet")
    with pytest.raises(PermissionError):
        sc.score(res["model"], base[base["sample"] == "oot"])
    from models.pd import challenger as chal

    with pytest.raises(PermissionError):
        chal.predict(res["challenger"], base[base["sample"] == "covid"])


def test_second_oot_scoring_is_refused(fixture_run):
    out, res = fixture_run
    base = pd.read_parquet(MARTS / "fct_scorecard_base.parquet")
    with pytest.raises(RuntimeError, match="already scored"):
        pdrun.score_out_of_time(res["model"], None, base, out / "models_out")
    entries = pdrun.read_oot_log(out / "models_out")
    assert [e["model_id"] for e in entries] == [res["model"]["model_id"]]
    assert res["pd_models"]["oot_scoring"]["calls"] == 1


# ---------------------------------------------------------------------------------------------
# End to end on the synthetic fixtures
# ---------------------------------------------------------------------------------------------
def test_outputs_follow_the_contract(fixture_run):
    out, _ = fixture_run
    for name in ("pd_models", "monitoring"):
        art = json.loads((out / "artefacts" / f"{name}.json").read_text(encoding="utf-8"))
        assert contracts.check_artefact(name, art) == []
        assert art["synthetic"] is True
    scores = out / "models_out" / "loan_scores.parquet"
    assert contracts.check_model_output("loan_scores", scores) == []
    assert contracts.parquet_is_synthetic(scores)
    base = pd.read_parquet(MARTS / "fct_scorecard_base.parquet")
    assert len(pd.read_parquet(scores)) == len(base)


def test_points_table_reproduces_every_score(fixture_run):
    """The published points table alone gives each loan's score and PD."""
    out, res = fixture_run
    art = json.loads((out / "artefacts" / "pd_models.json").read_text(encoding="utf-8"))
    scores = pd.read_parquet(out / "models_out" / "loan_scores.parquet").set_index("loan_id")
    base = pd.read_parquet(MARTS / "fct_scorecard_base.parquet").set_index("loan_id")
    total = np.zeros(len(base), int)
    for f in {r["feature"] for r in art["points_table"]}:
        rows = [r for r in art["points_table"] if r["feature"] == f]
        vals = base[f]
        pts = np.full(len(base), -(10**6))
        for r in rows:
            if r["is_missing_bin"]:
                m = vals.isna().to_numpy()
            elif r["categories"]:
                m = np.isin(sc.feature_values(base, f), r["categories"])
            else:
                lo = -np.inf if r["lower"] is None else r["lower"]
                hi = np.inf if r["upper"] is None else r["upper"]
                m = ((vals >= lo) & (vals < hi)).to_numpy()
            pts = np.where(m, r["points"], pts)
        assert (pts > -(10**6)).all(), f"{f}: a loan fell in no bin"
        total += pts
    assert (total == scores.loc[base.index, "score"].to_numpy()).all()
    s = art["scaling"]
    pd_ = 1 / (1 + np.exp((total - s["offset"]) / s["factor"]))
    assert np.allclose(pd_, scores.loc[base.index, "pd_12m"])


def test_reuse_scores_rebuilds_without_rescoring(fixture_run):
    out, res = fixture_run
    again = pdrun.run(
        MARTS / "fct_scorecard_base.parquet",
        MARTS / "dim_loan.parquet",
        MARTS / "fct_loan_month.parquet",
        out / "artefacts2",
        out / "models_out",
        reuse_scores=True,
    )
    assert again["model"]["model_id"] == res["model"]["model_id"]
    assert len(pdrun.read_oot_log(out / "models_out")) == 1
    strip = lambda a: {k: v for k, v in a.items() if k not in ("generated_at", "code_version")}  # noqa: E731
    assert strip(again["pd_models"]) == strip(res["pd_models"])


def test_fixtures_never_written_to_real_outputs():
    with pytest.raises(ValueError, match="synthetic"):
        pdrun.run(
            MARTS / "fct_scorecard_base.parquet",
            MARTS / "dim_loan.parquet",
            MARTS / "fct_loan_month.parquet",
            ROOT / "artefacts",
            Path(VINTAGE_DATA_ROOT) / "models_out",
        )


def test_reason_codes_are_largest_shortfalls(fixture_run):
    out, res = fixture_run
    model = res["model"]
    base = pd.read_parquet(MARTS / "fct_scorecard_base.parquet")
    dev = base[base["sample"] == "dev_test"].head(200)
    scored = sc.score(model, dev)
    pts = sc.points_matrix(model, dev)
    max_pts = np.array(
        [max(b["points"] for b in model["binnings"][f]["bins"]) for f in model["features"]]
    )
    for i in range(len(dev)):
        short = max_pts - pts[i]
        first = model["features"][int(np.argmax(short))] if short.max() > 0 else None
        assert scored["reason_1"].iloc[i] == first


def test_dry_run_never_scores_out_of_time(tmp_path):
    res = pdrun.run(
        MARTS / "fct_scorecard_base.parquet",
        MARTS / "dim_loan.parquet",
        MARTS / "fct_loan_month.parquet",
        tmp_path / "artefacts",
        tmp_path / "models_out",
        with_challenger=False,
        dry_run=True,
    )
    assert pdrun.read_oot_log(tmp_path / "models_out") == []
    assert not (tmp_path / "artefacts").exists()
    assert not (tmp_path / "models_out" / "loan_scores.parquet").exists()
    assert {r["sample"] for r in res["discrimination"]} == {"dev_train", "dev_test"}


def test_secondary_oot_windows_split_the_oot_sample(fixture_run):
    _, res = fixture_run
    rows = {
        r["sample"]: r["gini"]["n"]
        for r in res["pd_models"]["discrimination"]
        if r["model"] == "champion" and r["definition"] == "primary"
    }
    # Late-2021 originations paying first in 2022 are oot but in neither vintage window.
    assert 0 < rows["oot_2017_2019"] + rows["oot_2022_2024"] <= rows["oot"]
