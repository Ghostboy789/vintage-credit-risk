"""Stage 2 sensitivity to the house-price definition in the PD rule (validation issue V-05).

Restages two reporting dates three ways and recomputes the probability-weighted ECL at the point
estimate (no parameter draws). The fitted LGD, L1 and L2 models and the ECL engine are unchanged;
only the stage assignment differs.

- `published`: as in `ecl.Engine.stage`. PD12_now takes the mean house-price covariate over the
  next 12 months under each scenario; PD12_ref takes the covariate at the first payment month.
- `forward_mean_ref`: PD12_ref takes the mean covariate over the 12 months after the first
  payment month, the definition L2 is fitted on and PD12_now uses.
- `no_house_price`: the covariate term is dropped from both PD12_now and PD12_ref (the fitted
  coefficients are kept, not refitted).

    python -m models.loss.stage2_sensitivity    # real marts under VINTAGE_DATA_ROOT

Needs VINTAGE_HPI_CSV. Writes artefacts/stage2_sensitivity.json (aggregates only).
"""

import json
import os

import numpy as np
import pandas as pd

from config import VINTAGE_DATA_ROOT
from tests import contracts as C

from . import ecl
from . import run as R

VARIANTS = ["published", "forward_mean_ref", "no_house_price"]
DATES = [pd.Timestamp("2023-03-01"), pd.Timestamp("2026-03-01")]
POINT = "none: point estimate"
SPEC = C.ARTEFACTS["stage2_sensitivity"]


def measure(eng, macro, dim_loan, si, dates) -> list[dict]:
    """Stage 2 count, PD-rule-only count, stage 2 ECL and total ECL per date and variant."""
    fp = dim_loan.set_index("loan_id")["first_payment_date"]
    x_fwd = pd.Series(macro.x_mean12(ecl.month_int(fp)), index=fp.index)
    out = []
    for dt in dates:
        m = int(ecl.month_int(dt)[0])
        rows = si[si.reporting_date == dt]
        for v in VARIANTS:
            r = rows
            if v == "forward_mean_ref":
                r = rows.assign(x_orig=np.asarray(rows["loan_id"].map(x_fwd), float))
            st = eng.stage(r, m, hpi=v != "no_house_price")
            point, _, _ = eng.date(st, m)
            fin = eng.w @ point  # by (grade, stage) group: index grade * 3 + stage - 1
            s2 = st["stage"].to_numpy() == 2
            out.append(
                {
                    "reporting_date": dt,
                    "variant": v,
                    "n_loans": len(st),
                    "stage2_n_loans": int(s2.sum()),
                    "stage2_pd_rule_only": int((s2 & (st["stage_floor"].to_numpy() < 2)).sum()),
                    "stage2_ecl": float(fin[1:21:3].sum()),
                    "total_ecl": float(fin[:21].sum()),
                }
            )
    return out


def artefact(rows: list[dict], synthetic: bool) -> dict:
    obj = R.envelope("stage2_sensitivity", synthetic)
    obj["variants"] = [
        {
            "reporting_date": r["reporting_date"].strftime("%Y-%m-%d"),
            "variant": r["variant"],
            "n_loans": r["n_loans"],
            "stage2_n_loans": r["stage2_n_loans"],
            "stage2_pd_rule_only": r["stage2_pd_rule_only"],
            "stage2_share": C.metric(
                r["stage2_n_loans"] / r["n_loans"], n=r["n_loans"], ci_method=POINT
            ),
            "stage2_ecl": C.metric(r["stage2_ecl"], n=r["stage2_n_loans"], ci_method=POINT),
            "total_ecl": C.metric(r["total_ecl"], n=r["n_loans"], ci_method=POINT),
        }
        for r in rows
    ]
    obj["suppressed_cells"] = C.suppress_small_cells(obj)
    return obj


def main():
    marts, mo = VINTAGE_DATA_ROOT / "marts_out", VINTAGE_DATA_ROOT / "models_out"
    ctx = R.prepare(marts, mo, n_draws=0, hpi=os.environ["VINTAGE_HPI_CSV"])
    rows = measure(ctx["eng"], ctx["macro"], ctx["d"]["dim_loan"], ctx["si"], DATES)
    obj = artefact(rows, ctx["synthetic"])
    problems = C.check_artefact("stage2_sensitivity", obj)
    if problems:
        raise SystemExit(f"stage2_sensitivity.json breaks the conventions: {problems[:5]}")
    path = R.ROOT / "artefacts" / "stage2_sensitivity.json"
    path.write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
    for r in rows:
        print(
            f"{r['reporting_date']:%Y-%m} {r['variant']:<17} stage 2 {r['stage2_n_loans']:>7,}"
            f" of {r['n_loans']:,} (PD rule only {r['stage2_pd_rule_only']:,}),"
            f" stage 2 ECL ${r['stage2_ecl'] / 1e6:.1f}m, total ${r['total_ecl'] / 1e6:.1f}m"
        )


if __name__ == "__main__":
    main()
