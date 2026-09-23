"""Tests for the loss and provisioning engine (models/loss), VALIDATION_PLAN E4 and friends."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from models.loss import capital, ecl, lgd
from models.loss import lifetime as LT
from models.loss import run as R
from models.loss import stats as S
from models.loss.macro import Macro
from tests import contracts as C

FIX = Path(__file__).resolve().parent / "fixtures"


# --- E4a: ECL = PD x LGD x EAD x discount on hand-worked loans --------------------------------
def test_e4a_one_month_loan_by_hand():
    # Stage 1, one month left: ECL = PD12/12 * LGD * UPB / (1 + 6%/12)
    #   = 0.002 * 0.3 * 100000 / 1.005
    got = ecl.loan_ecl(1, 0.024, [0.0], [0.0], 0.3, 100000.0, 0.0, 6.0, 6.0, 1)
    assert abs(got - 60 / 1.005) < 0.01


def test_e4a_stage3_is_lgd_times_exposure():
    assert ecl.loan_ecl(3, 0.5, [0.1], [0.1], 0.35, 150000.0, 0.0, 5.0, 5.0, 100) == 52500.0


def test_e4a_36_month_loan_matches_month_by_month_calculation():
    assert R.check_e4a() < 0.01


def test_deferred_balance_stays_until_maturity():
    w = ecl.weights([1000.0], [400.0], [0.0], [0.0], [3], [3], 5)[0]
    # 600 interest-bearing at 0%: 600, 400, 200 before payments 1-3; deferred 400 throughout.
    assert np.allclose(w, [1000, 800, 600, 0, 0])


# --- E4b: staging edge cases -----------------------------------------------------------------
class StubL2:
    """PD depends only on behaviour state, so the PD rule can be checked by hand."""

    pds = {"clean": 0.005, "recent_dpd": 0.02, "dpd_30": 0.1, "dpd_60p": 0.3, "default": 1.0}

    def pd12(self, f, x=None, **_):
        return f["behaviour_state"].map(self.pds).to_numpy() * np.where(f.grade == "A", 0.1, 1)


def stub_engine():
    eng = ecl.Engine.__new__(ecl.Engine)
    eng.l2, eng.w, eng.macro, eng.scen = StubL2(), np.ones(1), None, ["final"]
    return eng


def staged(**over):
    row = {
        "grade": "D",
        "age_band": "25_36",
        "behaviour_state": "clean",
        "modified": False,
        "in_default": False,
        "stage_floor": 1,
        "stage_floor_reason": None,
        "defaulted_before": False,
        **over,
    }
    return int(stub_engine().stage(pd.DataFrame([row]), 0)["stage"].iloc[0])


def test_e4b_29_vs_30_days_past_due():
    assert staged() == 1  # status 00 covers 0-29 days: no stage 2 rule holds
    assert staged(stage_floor=2, stage_floor_reason="dpd30_backstop", behaviour_state="dpd_30") == 2


def test_e4b_forborne_90_plus_is_stage_2_not_3():
    assert staged(stage_floor=2, stage_floor_reason="forbearance", behaviour_state="dpd_60p") == 2


def test_e4b_cure_probation_then_back_to_stage_1():
    assert staged(stage_floor=2, stage_floor_reason="cure_probation", defaulted_before=True) == 2
    assert staged(defaulted_before=True) == 1  # probation over, clean: no probation 2 -> 1


def test_e4b_in_default_is_stage_3():
    assert staged(in_default=True, stage_floor=3, behaviour_state="default") == 3


def test_e4b_pd_rule_needs_both_thresholds():
    assert staged(behaviour_state="recent_dpd") == 2  # 4x and +1.5 points
    # Grade A: 0.05% -> 0.2% is 4x but only +0.15 points, under the 0.20-point floor.
    assert staged(grade="A", behaviour_state="recent_dpd") == 1


def test_e4b_credit_event_exit_leaves_the_book():
    st = pd.DataFrame(
        {
            "reporting_date": pd.to_datetime(["2010-09-01", "2010-12-01"]),
            "loan_id": ["a", "b"],
            "stage": [3, 1],
        }
    )
    moves = ecl.migration(st)
    assert [(m["from_stage"], m["to_stage"]) for m in moves] == [("3", "exited")]


# --- E4c: competing risks sum to one ---------------------------------------------------------
def test_e4c_marginal_default_prepay_and_survival_sum_to_one():
    rng = np.random.default_rng(1)
    hd, hp = rng.uniform(0, 0.02, (50, 360)), rng.uniform(0, 0.05, (50, 360))
    pd12 = np.r_[rng.uniform(0, 0.2, 49), 0.99]  # the last one hits the survival cap
    md, mp, s = LT.paths(pd12, hd, hp)
    assert np.max(np.abs(md.sum(1) + mp.sum(1) + s - 1)) < 1e-12
    assert (md >= 0).all() and (mp >= 0).all() and (s >= -1e-15).all()
    assert np.allclose(md[:49, :12], pd12[:49, None] / 12)  # L2 PD spread evenly in year 1


# --- E3 colours --------------------------------------------------------------------------------
def test_vasicek_quantile_inverts_the_plan_cdf():
    from scipy.stats import norm

    p, rho = 0.01, 0.15
    x = S.vasicek_quantile(0.975, p, rho)
    cdf = norm.cdf((np.sqrt(1 - rho) * norm.ppf(x) - norm.ppf(p)) / np.sqrt(rho))
    assert abs(cdf - 0.975) < 1e-12


def test_backtest_colours():
    assert ecl.rag(0.01, 1000, 0.01)[0] == "green"
    assert ecl.rag(0.025, 1000, 0.01)[0] == "amber"  # outside binomial, inside Vasicek
    assert ecl.rag(0.2, 1000, 0.01)[0] == "red"


def test_backtest_rule_counts_only_non_covid_dates():
    ok = {d: [("green", False)] for d in ecl.BACKTEST_DATES}
    assert ecl.backtest_rule(ok)["result"] == "PASS"
    ok[pd.Timestamp("2020-12-01")] = [("red", True)]
    assert ecl.backtest_rule(ok)["result"] == "PASS"
    ok[pd.Timestamp("2017-12-01")] = [("red", True)]
    r = ecl.backtest_rule(ok)
    assert r["result"] == "FAIL" and "under-predicted" in r["evidence"]


# --- Basel K against a hand calculation -------------------------------------------------------
def test_basel_k_hand_computed():
    # PD 1%, LGD 25%, R 0.15: G(0.01) = -2.326348, G(0.999) = 3.090232,
    # N(-2.326348 / 0.921954 + 0.420084 * 3.090232) = N(-1.225122) = 0.110266,
    # K = 0.25 * (0.110266 - 0.01) = 0.025066; RWA on 100,000 = 12.5 * K * EAD = 31,333.
    k = float(capital.k_irb(0.01, 0.25))
    assert abs(k - 0.025066) < 1e-6
    assert abs(12.5 * k * 100000 - 31333) < 1


# --- estimation helpers ---------------------------------------------------------------------------
def test_grade_merge_follows_the_plan_order():
    t = pd.DataFrame(
        {"d": [0, 5, 5, 0, 5, 5, 0], "n": [10, 50, 60, 70, 60, 50, 10]}, index=list("ABCDEFG")
    )
    m = LT.merge_grades(t, lambda r: r["d"] > 0)
    assert m["A"] == "B" and m["G"] == "F" and m["D"] == "C"  # D ties 60/60 -> C


def test_multinomial_logit_recovers_cell_shares():
    X = np.array([[1, 0], [1, 1]], float)
    Y = np.array([[80, 10, 10], [50, 30, 20]], float)
    b, cov, ok = S.fit_mnlogit(X, Y)
    assert ok and np.allclose(S.probs(X, b), Y / Y.sum(1, keepdims=True))


def test_lgd_sensitivities():
    sample = pd.DataFrame({"ltv_band": ["60_80"] * 60, "lgd_economic": np.linspace(0, 0.6, 60)})
    defaults = pd.DataFrame(
        {
            "loan_id": list("abcdef"),
            "default_period": pd.Timestamp("2010-01-01"),
            "resolution": [
                "cured_active",
                "other_exit",
                "other_exit",
                "defect_settlement",
                "credit_event_loss",
                "open",
            ],
        }
    )
    dim = pd.DataFrame(
        {
            "loan_id": list("abcdef"),
            "ltv_band": "60_80",
            "terminal_zero_balance_code": [None, 16, 96, 3, 9, None],
        }
    )
    out, info = lgd.sensitivities(sample, defaults, dim)
    assert info["zero_loss_added"] == 2  # cured_active and code 16; not 96 or defect settlement
    zl = out[0]["lgd_economic"]
    assert abs(zl["value"] - sample.lgd_economic.sum() / 62) < 1e-12 and zl["n"] == 62
    assert info["open_share"] == 1 / 6 and out[1]["status"] == "run"  # 1 of 6 > 10%


def test_macro_scenarios():
    months = np.arange(1995 * 12, 2026 * 12 + 3)
    growth = np.random.default_rng(2).normal(0.003, 0.01, len(months))
    hpi = pd.Series(100 * np.cumprod(1 + growth), index=months)
    m = Macro(hpi)
    assert abs(m.base - m.chg.median()) < 1e-12 and m.p90 > m.base
    x = m.x_paths(2020 * 12, "upside", 30)
    assert np.allclose(x[3:27], m.p90) and np.allclose(x[27:], m.base)
    assert np.allclose(x[:3], m.chg.loc[2020 * 12 - 2 : 2020 * 12].to_numpy())  # observed, lag 3
    x = m.x_paths(2020 * 12, "adverse", 70)
    assert np.allclose(x[3:63], m.chg.loc[2007 * 12 : 2011 * 12 + 11].to_numpy())
    assert np.allclose(x[63:], m.base)
    assert np.allclose(m.x(np.array([2010 * 12])), m.chg.loc[2010 * 12 - 3])


# --- end to end on the synthetic fixtures ------------------------------------------------------
@pytest.fixture(scope="module")
def fixture_ctx():
    return R.prepare(FIX / "marts", FIX / "models_out", n_draws=3)


def test_engine_matches_loan_by_loan_ecl(fixture_ctx):
    eng, si = fixture_ctx["eng"], fixture_ctx["si"]
    dt = pd.Timestamp("2008-12-01")
    m = int(ecl.month_int(dt)[0])
    st = eng.stage(si[si.reporting_date == dt], m).reset_index(drop=True)
    point, _, _ = eng.date(st, m)
    lgd_by_seg = dict(zip(eng.segs, eng.p3[0]))
    total = np.zeros(21)
    for r in st.itertuples():
        rem = max(r.remaining_term, 1)
        hd, hp = eng.l1.hazards(
            [r.grade], np.array([min(max(r.months_on_book, 0), 121)]), [r.inc_band], rem
        )
        total[LT.GRADES.index(r.grade) * 3 + r.stage - 1] += ecl.loan_ecl(
            r.stage,
            r.pd12,
            hd[0],
            hp[0],
            lgd_by_seg[r.lgd_seg],
            r.current_upb,
            r.non_interest_bearing_upb or 0.0,
            r.current_rate_pct if pd.notna(r.current_rate_pct) else r.note_rate_pct,
            r.note_rate_pct,
            rem,
        )
    assert np.allclose(point[0, :21], total, rtol=1e-9, atol=1e-6)


def test_fixture_run_follows_the_contracts(fixture_ctx, tmp_path):
    arts, results, _ = R.run(FIX / "marts", FIX / "models_out", n_draws=3)
    for name, obj in arts.items():
        assert C.check_artefact(name, obj) == [], name
        assert obj["synthetic"] is True
    rules = {r["rule_id"]: r["result"] for r in arts["ecl"]["pass_rules"]}
    assert rules["E4a"] == rules["E4b"] == rules["E4c"] == "PASS"
    path = tmp_path / "ecl_results.parquet"
    R.write_parquet(results, path, True)
    assert C.check_model_output("ecl_results", path) == []
    assert C.parquet_is_synthetic(path)
