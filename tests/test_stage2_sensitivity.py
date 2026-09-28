"""The stage 2 sensitivity (models/loss/stage2_sensitivity.py) on the synthetic fixtures."""

from pathlib import Path

import numpy as np
import pandas as pd

from models.loss import ecl
from models.loss import lifetime as LT
from models.loss import run as R
from models.loss import stage2_sensitivity as S2

FIX = Path(__file__).resolve().parent / "fixtures"


def test_variants_restage_as_defined(tmp_path):
    months = np.arange(1990 * 12, 2026 * 12 + 3)
    growth = np.random.default_rng(3).normal(0.003, 0.01, len(months))
    hpi = pd.DataFrame(
        {
            "hpi_type": "traditional",
            "hpi_flavor": "purchase-only",
            "frequency": "monthly",
            "place_id": "USA",
            "yr": months // 12,
            "period": months % 12 + 1,
            "index_sa": 100 * np.cumprod(1 + growth),
        }
    )
    hpi.to_csv(tmp_path / "hpi.csv", index=False)
    ctx = R.prepare(FIX / "marts", FIX / "models_out", n_draws=0, hpi=tmp_path / "hpi.csv")
    eng, macro, si = ctx["eng"], ctx["macro"], ctx["si"]
    dt = pd.Timestamp("2008-12-01")
    m = int(ecl.month_int(dt)[0])
    pub, fwd, none = S2.measure(eng, macro, ctx["d"]["dim_loan"], si, [dt])

    rows = si[si.reporting_date == dt]
    st = eng.stage(rows, m)
    fin = eng.w @ eng.date(st, m)[0]
    assert pub["stage2_n_loans"] == (st.stage == 2).sum()
    assert np.isclose(pub["total_ecl"], fin[:21].sum())
    assert pub["stage2_ecl"] < pub["total_ecl"]

    # The forward-mean reference is the mean covariate over the 12 months after first payment.
    assert np.isclose(
        macro.x_mean12(np.array([2005 * 12]))[0], macro.x(2005 * 12 + 1 + np.arange(12)).mean()
    )

    # Without the covariate, a clean unmodified loan has PD12_now == PD12_ref, so the PD rule
    # can only move loans with a behaviour or modification flag.
    st0 = eng.stage(rows, m, hpi=False)
    f = LT.l2_frame(rows)
    same = ((f.behaviour_state == "clean") & (f.modified == "N")).to_numpy()
    assert same.any() and np.allclose(st0.pd12[same], st0.pd12_ref[same])
    assert not st0.sicr.to_numpy()[same].any()
    assert none["stage2_n_loans"] == (st0.stage == 2).sum()
    assert fwd["n_loans"] == none["n_loans"] == len(rows)

    art = S2.artefact([pub, fwd, none], True)
    assert S2.C._check(S2.SPEC, art, "stage2_sensitivity") == []
