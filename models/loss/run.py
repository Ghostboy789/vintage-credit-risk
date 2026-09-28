"""Run the loss and provisioning engine end to end and write its outputs.

    python -m models.loss.run --fixtures --out <dir>   # synthetic fixtures, outputs to <dir>
    python -m models.loss.run                          # real marts under VINTAGE_DATA_ROOT

Real run: reads marts_out/ and models_out/loan_scores.parquet under VINTAGE_DATA_ROOT, writes
models_out/ecl_results.parquet there and artefacts/{lgd_ead,ecl,capital}.json in the repo.
The macro scenarios (E6) run when VINTAGE_HPI_CSV points at the FHFA HPI master CSV.
"""

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config import VINTAGE_DATA_ROOT
from tests import contracts as C

from . import capital, ecl, lgd
from . import lifetime as LT
from . import stats as S
from .macro import SOURCE, WEIGHTS, Macro, load_hpi

ROOT = Path(__file__).resolve().parents[2]
CUTOFF = pd.Timestamp("2026-03-01")
SI_COLS = [
    "loan_id",
    "reporting_date",
    "months_on_book",
    "age_band",
    "remaining_term",
    "current_upb",
    "non_interest_bearing_upb",
    "note_rate_pct",
    "current_rate_pct",
    "rate_incentive_pct",
    "in_default",
    "behaviour_state",
    "modified",
    "stage_floor",
    "stage_floor_reason",
    "ltv_band",
    "defaulted_before",
    "default_next_12m",
    "prepaid_next_12m",
]


def envelope(name, synthetic):
    try:
        sha = (
            subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
            ).stdout.strip()
            or "unknown"
        )
    except OSError:
        sha = "unknown"
    return {
        "schema_version": C.SCHEMA_VERSION,
        "artefact": name,
        "synthetic": synthetic,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_cutoff": "2026-03-01",
        "code_version": sha,
        "suppressed_cells": 0,
    }


def load(marts: Path, models_out: Path):
    rd = lambda p, cols=None: pd.read_parquet(p, columns=cols)  # noqa: E731
    d = {
        "dim_loan": rd(marts / "dim_loan.parquet"),
        "defaults": rd(marts / "fct_default_events.parquet"),
        "loss": rd(marts / "fct_loss_events.parquet"),
        "dim_date": rd(marts / "dim_date.parquet"),
        "scores": rd(models_out / "loan_scores.parquet", ["loan_id", "grade"]),
    }
    d["defaults"] = d["defaults"][d["defaults"].definition == "primary"]
    # ~25M rows on the real book: loan_id as a categorical, dates as datetime64, small ints.
    si = pq.read_table(
        marts / "fct_stage_inputs.parquet", columns=SI_COLS, read_dictionary=["loan_id"]
    ).to_pandas(date_as_object=False, split_blocks=True, self_destruct=True)
    si["reporting_date"] = pd.to_datetime(si["reporting_date"])
    for col in ("months_on_book", "remaining_term", "stage_floor"):
        si[col] = si[col].astype(np.int32)
    for col in ("default_next_12m", "prepaid_next_12m"):
        si[col] = si[col].map({True: 1.0, False: 0.0}).astype(np.float32)
    d["si"] = si
    return d


def prepare(marts: Path, models_out: Path, n_draws=1000, hpi=None) -> dict:
    """Load the marts, fit LGD, L1 and L2, and build the engine."""
    d = load(marts, models_out)
    synthetic = C.parquet_is_synthetic(marts / "fct_stage_inputs.parquet")
    notes = {}

    lgd_body, seg = lgd.build(d["loss"], d["defaults"], d["dim_loan"])
    macro = Macro(load_hpi(hpi, int(ecl.month_int(CUTOFF)[0]))) if hpi else None

    paths = {
        "flm": marts / "fct_loan_month.parquet",
        "fde": marts / "fct_default_events.parquet",
        "scores": models_out / "loan_scores.parquet",
        "dim_date": marts / "dim_date.parquet",
    }
    cells, l1_loans = LT.l1_cells(paths, macro is not None, os.environ.get("VINTAGE_DUCKDB_TEMP"))
    l1 = LT.L1(cells, macro)

    si = d.pop("si")
    si["grade"] = np.asarray(si["loan_id"].map(d["scores"].set_index("loan_id")["grade"]), object)
    notes["stage_rows_without_grade"] = int(si["grade"].isna().sum())
    if notes["stage_rows_without_grade"]:
        si = si[si["grade"].notna()].reset_index(drop=True)
    xbar = None
    if macro is not None:
        month = ecl.month_int(si["reporting_date"])
        um = np.unique(month)  # the 12-month-ahead mean depends on the month only
        fwd = macro.x_mean12(um)
        xbar = pd.Series(fwd[np.searchsorted(um, month)], index=si.index)
        fp = d["dim_loan"].set_index("loan_id")["first_payment_date"]
        x_loan = pd.Series(macro.x(ecl.month_int(fp)), index=fp.index)
        si["x_orig"] = np.asarray(si["loan_id"].map(x_loan), float)
    l2 = LT.L2(si, xbar)

    si["inc_band"] = LT.inc_band(si["rate_incentive_pct"])
    if seg.model is not None:  # G2 passed: loan-level LGD from the two-stage model
        # Predicted once per loan (origination attributes only), then mapped onto the rows.
        dl = d["dim_loan"]
        lgd_loan = pd.Series(seg.model.predict(dl), index=dl["loan_id"])
        si["lgd_seg"] = "g2"
        si["lgd_row"] = np.asarray(si["loan_id"].map(lgd_loan), float)
    else:
        si["lgd_seg"], si["lgd_row"] = seg.segment_of(si["ltv_band"]), 1.0

    eng = ecl.Engine(l1, l2, seg, macro, n_draws)
    return dict(
        d=d,
        synthetic=synthetic,
        notes=notes,
        lgd_body=lgd_body,
        seg=seg,
        macro=macro,
        cells=cells,
        l1=l1,
        l1_loans=l1_loans,
        l2=l2,
        si=si,
        eng=eng,
    )


def run(marts: Path, models_out: Path, n_draws=1000, hpi=None):
    """Everything in memory: (artefacts dict, ecl_results DataFrame, notes dict)."""
    ctx = prepare(marts, models_out, n_draws, hpi)
    d, synthetic, notes, lgd_body, seg, macro = (
        ctx[k] for k in ("d", "synthetic", "notes", "lgd_body", "seg", "macro")
    )
    cells, l1, l1_loans, l2, si, eng = (
        ctx[k] for k in ("cells", "l1", "l1_loans", "l2", "si", "eng")
    )
    # Stage columns are written back into si (no second copy of the book).
    n = len(si)
    out = {
        "pd12": np.full(n, np.nan),
        "pd12_ref": np.full(n, np.nan),
        "sicr": np.zeros(n, bool),
        "stage": np.zeros(n, np.int8),
        "prepay12": np.full(n, np.nan),
    }
    point, draws = {}, {}
    t0 = time.perf_counter()
    for dt, idx in sorted(si.groupby("reporting_date").indices.items()):
        dt = pd.Timestamp(dt)
        m = int(ecl.month_int(dt)[0])
        st = eng.stage(si.iloc[idx], m)
        p, dr, prepay12 = eng.date(st, m)
        for col in ("pd12", "pd12_ref", "sicr", "stage"):
            out[col][idx] = st[col].to_numpy()
        out["prepay12"][idx[prepay12.index.to_numpy()]] = prepay12.to_numpy()
        point[dt], draws[dt] = p, dr
        print(f"{dt:%Y-%m}: {len(idx)} rows, {time.perf_counter() - t0:.0f} s", flush=True)
    for col, v in out.items():
        si[col] = v
    staged = si

    ecl_body, ecl_results, ecl_by_grade = assemble(
        eng, staged, point, draws, l1, l1_loans, cells, d["dim_date"], macro
    )
    latest = staged[staged.reporting_date == staged.reporting_date.max()]
    cap_body = capital.build(si, latest, seg.downturn, ecl_by_grade)
    notes.update(
        l1_grade_map=l1.grade_map,
        l2_grade_map=l2.grade_map,
        lgd_sensitivity_info=seg.sens_info,
        macro=macro is not None,
    )

    arts = {}
    for name, body in [("lgd_ead", lgd_body), ("ecl", ecl_body), ("capital", cap_body)]:
        obj = {**envelope(name, synthetic), **body}
        obj["suppressed_cells"] = C.suppress_small_cells(obj)
        arts[name] = obj
    return arts, ecl_results, notes


def assemble(eng, staged, point, draws, l1, l1_loans, cells, dim_date, macro):
    scen_names = eng.scen
    by_date, totals, cured_rows, results = [], [], [], []
    ecl_by_grade = {}
    latest = max(point)
    for dt in sorted(point):
        p, dr = point[dt], draws[dt]  # p: scen x 22, dr: draws x scen x 22
        fp, fd = eng.w @ p, np.einsum("s,dsk->dk", eng.w, dr)
        rows = staged[staged.reporting_date == dt]
        in_sample = bool(dt <= ecl.IN_SAMPLE_END)
        grp = rows.groupby(["grade", "stage"]).agg(
            n=("loan_id", "size"), ead=("current_upb", "sum")
        )
        for (g, s), r in grp.iterrows():
            k = LT.GRADES.index(g) * 3 + s - 1
            n, ead = int(r.n), float(r.ead)
            by_date.append(
                {
                    "reporting_date": dt.strftime("%Y-%m-%d"),
                    "in_sample": in_sample,
                    "stage": str(s),
                    "grade": g,
                    "n_loans": n,
                    "ead": S.metric(ead, n=n, method="none: population total"),
                    "ecl": S.percentile(fp[k], fd[:, k], n, "parameter_draws_1000"),
                    "coverage": S.percentile(
                        fp[k] / ead, fd[:, k] / ead, n, "parameter_draws_1000"
                    ),
                }
            )
            for si_, name in enumerate(["final"] + (scen_names if macro else [])):
                val = fp[k] if name == "final" else p[si_ - 1, k]
                results.append(
                    {
                        "reporting_date": dt.date(),
                        "scenario": name,
                        "grade": g,
                        "stage": int(s),
                        "n_loans": n,
                        "ead": ead,
                        "ecl": float(val),
                        "in_sample": in_sample,
                    }
                )
            if dt == latest and s < 3:
                pt, dd = ecl_by_grade.get(g, (0.0, 0.0))
                ecl_by_grade[g] = (pt + fp[k], dd + fd[:, k])
        n_all = len(rows)
        totals.append(
            {
                "reporting_date": dt.strftime("%Y-%m-%d"),
                "scenario": "final",
                "ecl": S.percentile(
                    fp[:21].sum(), fd[:, :21].sum(1), n_all, "parameter_draws_1000"
                ),
            }
        )
        if macro:
            for i, name in enumerate(scen_names):
                totals.append(
                    {
                        "reporting_date": dt.strftime("%Y-%m-%d"),
                        "scenario": name,
                        "ecl": S.percentile(
                            p[i, :21].sum(), dr[:, i, :21].sum(1), n_all, "parameter_draws_1000"
                        ),
                    }
                )
        cur = rows[rows.defaulted_before.astype(bool) & ~rows.in_default.astype(bool)]
        if len(cur):
            cured_rows.append(
                {
                    "reporting_date": dt.strftime("%Y-%m-%d"),
                    "n_loans": len(cur),
                    "ead": S.metric(
                        cur.current_upb.sum(), n=len(cur), method="none: population total"
                    ),
                    "ecl": S.percentile(fp[21], fd[:, 21], len(cur), "parameter_draws_1000"),
                }
            )

    bt_rows, verdict = ecl.backtest(staged)
    lm = int(ecl.month_int(latest)[0])
    term, e4c_dev = [], 0.0
    for g in LT.GRADES:
        if g not in l1_loans.index:
            continue
        ann, cum, dev = eng.term_structure(g, lm)
        e4c_dev = max(e4c_dev, dev)
        dd = [eng.term_structure(g, lm, d=i) for i in range(1, eng.n_draws + 1)]
        da, dc = np.array([x[0] for x in dd]), np.array([x[1] for x in dd])
        e4c_dev = max(e4c_dev, max(x[2] for x in dd))
        n = int(l1_loans[g])
        for y in range(len(ann)):
            term.append(
                {
                    "grade": g,
                    "year": y + 1,
                    "marginal_pd": S.percentile(ann[y], da[:, y], n, "parameter_draws_1000"),
                    "cumulative_pd": S.percentile(cum[y], dc[:, y], n, "parameter_draws_1000"),
                }
            )

    e4a, e4b = check_e4a(), check_e4b(eng)
    rules = [
        ecl.backtest_rule(verdict),
        {
            "rule_id": "E4a",
            "result": "PASS" if e4a < 0.01 else "FAIL",
            "evidence": f"Hand-worked loans (stage 1, 2 and 3): largest difference ${e4a:.6f} "
            "against an independent month-by-month calculation (tolerance $0.01).",
        },
        {
            "rule_id": "E4b",
            "result": "PASS" if not e4b else "FAIL",
            "evidence": "Staging edge cases: 29 against 30 days past due, cure probation, "
            "a forborne 90+ loan (stage 2, not 3), a credit-event exit (leaves the book)"
            + ("" if not e4b else "; failed: " + "; ".join(e4b)),
        },
        {
            "rule_id": "E4c",
            "result": "PASS" if e4c_dev < 1e-12 else "FAIL",
            "evidence": "Marginal default + marginal prepayment + final survival = 1 for every "
            f"grade, "
            f"scenario and parameter draw over 30 years: largest deviation {e4c_dev:.1e} "
            f"(tolerance 1e-12). Grade merges for estimation: L1 {merges(l1.grade_map)}, "
            f"L2 {merges(eng.l2.grade_map)}.",
        },
    ]
    body = {
        "scenarios": {
            "used": macro is not None,
            "source": SOURCE if macro else None,
            "weights": [{"scenario": s, "weight": w} for s, w in WEIGHTS.items()] if macro else [],
        },
        "sicr": {"ratio_threshold": ecl.RATIO, "absolute_threshold": ecl.ABSOLUTE},
        "by_date": by_date,
        "scenario_totals": totals,
        "stage_migration": ecl.migration(staged),
        "pd_term_structure": term,
        "backtest": bt_rows,
        "prepayment_backtest": ecl.prepayment_backtest(staged),
        "stage2_drivers": ecl.stage2_drivers(staged),
        "cured_population": cured_rows,
        "hazard_inputs": {
            "market_rate_carried_forward_months": int(dim_date.market_rate_carried_forward.sum()),
            "loan_months_without_market_rate": int(cells.n_no_market_rate.sum()),
        },
        "pass_rules": rules,
    }
    return body, pd.DataFrame(results), ecl_by_grade


def merges(grade_map) -> str:
    m = [f"{g} into {t}" for g, t in grade_map.items() if g != t]
    return ", ".join(m) if m else "none"


# --- E4 checks, shared with tests/test_loss.py ---------------------------------------------------
def hand_ecl(stage, pd12, hd, hp, lgd_, upb, rate, note, rem):
    """Independent month-by-month ECL for a loan with no deferred balance (E4a)."""
    r, q = rate / 1200, note / 1200
    pay = upb * r / (1 - (1 + r) ** -rem)
    bal, surv, total = upb, 1.0, 0.0
    if stage == 3:
        return lgd_ * upb
    horizon = min(12, rem) if stage == 1 else rem
    for m in range(1, horizon + 1):
        prep = surv * hp[m - 1]
        dflt = min(pd12 / 12, surv - prep) if m <= 12 else surv * hd[m - 1]
        total += dflt * lgd_ * bal / (1 + q) ** m
        surv -= dflt + prep
        bal = bal * (1 + r) - pay
    return total


def check_e4a() -> float:
    worst = 0.0
    rem = 36
    hd, hp = np.full(rem, 0.002), np.full(rem, 0.01)
    for stage in (1, 2, 3):
        a = ecl.loan_ecl(stage, 0.03, hd, hp, 0.25, 200000.0, 0.0, 6.0, 6.5, rem)
        b = hand_ecl(stage, 0.03, hd, hp, 0.25, 200000.0, 6.0, 6.5, rem)
        worst = max(worst, abs(a - b))
    return worst


def check_e4b(eng) -> list[str]:
    """Stage outcomes for rows built the way the dbt stage floor sees them."""
    base = {
        "loan_id": "x",
        "reporting_date": pd.Timestamp("2010-12-01"),
        "grade": "D",
        "months_on_book": 30,
        "age_band": "25_36",
        "modified": False,
        "in_default": False,
        "stage_floor": 1,
        "stage_floor_reason": None,
        "behaviour_state": "clean",
        "defaulted_before": False,
        "x_orig": 0.0,
    }
    cases = {
        "29 days past due (status 00) is stage 1": ({}, 1),
        "30 days past due (status 01) is stage 2": (
            {"stage_floor": 2, "stage_floor_reason": "dpd30_backstop", "behaviour_state": "dpd_30"},
            2,
        ),
        "cure probation is stage 2": (
            {"stage_floor": 2, "stage_floor_reason": "cure_probation", "defaulted_before": True},
            2,
        ),
        "forborne 90+ loan is stage 2, not 3": (
            {"stage_floor": 2, "stage_floor_reason": "forbearance", "behaviour_state": "dpd_60p"},
            2,
        ),
        "loan in default is stage 3": (
            {
                "stage_floor": 3,
                "stage_floor_reason": "default",
                "in_default": True,
                "behaviour_state": "default",
                "defaulted_before": True,
            },
            3,
        ),
    }
    fails = []
    for name, (over, want) in cases.items():
        got = int(eng.stage(pd.DataFrame([{**base, **over}]), 2010 * 12 + 11)["stage"].iloc[0])
        if got != want:
            fails.append(f"{name}: got {got}")
    # A credit-event exit has no stage-input row after it, so it migrates to 'exited'.
    st = pd.DataFrame(
        {
            "reporting_date": pd.to_datetime(["2010-09-01", "2010-12-01"]),
            "loan_id": ["a", "b"],
            "stage": [3, 1],
        }
    )
    mig = ecl.migration(st)
    if not any(r["from_stage"] == "3" and r["to_stage"] == "exited" for r in mig):
        fails.append("credit-event exit does not migrate to exited")
    return fails


def write_parquet(df: pd.DataFrame, path: Path, synthetic: bool):
    spec = C.MODEL_OUTPUTS["ecl_results"]["columns"]
    table = pa.Table.from_pandas(df[list(spec)], preserve_index=False)
    table = table.cast(
        pa.schema(
            [
                (
                    c,
                    {
                        "string": pa.string(),
                        "int": pa.int64(),
                        "float": pa.float64(),
                        "bool": pa.bool_(),
                        "date": pa.date32(),
                    }[spec[c][0]],
                )
                for c in spec
            ]
        )
    )
    if synthetic:
        table = table.replace_schema_metadata(
            {**(table.schema.metadata or {}), C.SYNTHETIC_KEY: b"true"}
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true", help="run on tests/fixtures (synthetic)")
    ap.add_argument("--out", type=Path, help="output folder (required with --fixtures)")
    ap.add_argument("--draws", type=int, default=1000)
    a = ap.parse_args(argv)
    hpi = os.environ.get("VINTAGE_HPI_CSV")
    if a.fixtures:
        if a.out is None:
            ap.error("--fixtures needs --out: fixture outputs never go to artefacts/")
        marts, mo = ROOT / "tests/fixtures/marts", ROOT / "tests/fixtures/models_out"
        art_dir, res_path = a.out, a.out / "ecl_results.parquet"
    else:
        marts, mo = VINTAGE_DATA_ROOT / "marts_out", VINTAGE_DATA_ROOT / "models_out"
        art_dir, res_path = a.out or ROOT / "artefacts", mo / "ecl_results.parquet"
    arts, results, notes = run(marts, mo, a.draws, hpi)
    art_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in arts.items():
        problems = C.check_artefact(name, obj)
        if problems:
            raise SystemExit(f"{name}.json breaks the contract: {problems[:5]}")
        (art_dir / f"{name}.json").write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
    write_parquet(results, res_path, arts["ecl"]["synthetic"])
    print(json.dumps(notes, indent=1, default=str))
    for name, obj in arts.items():
        for r in obj.get("pass_rules", []):
            print(f"{name}: {r['rule_id']} {r['result']} - {r['evidence'][:160]}")


if __name__ == "__main__":
    main()
