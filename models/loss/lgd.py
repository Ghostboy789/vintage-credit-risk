"""Realised LGD and EAD (VALIDATION_PLAN D7, D8, G1, G2) and the LGD the ECL uses."""

import numpy as np
import pandas as pd

from . import stats as S

MIN_SEGMENT = 50
CUTOFF = pd.Timestamp("2026-03-01")
LGD_SAMPLE_END = CUTOFF - pd.DateOffset(months=36)  # defaults up to 2023-03 (D8)
MEASURES = ["lgd_economic", "lgd_gross_of_mi", "lgd_undiscounted"]
G2_SPLIT = pd.Timestamp("2010-12-01")


def fold(values: pd.Series, min_n: int = MIN_SEGMENT) -> pd.Series:
    """Segments with fewer than min_n rows become 'other' (G1)."""
    counts = values.value_counts()
    small = set(counts[counts < min_n].index)
    return values.where(~values.isin(small), "other")


class SegmentLGD:
    """lgd_economic mean by origination LTV band (folded), with bootstrap draws, for ECL."""

    def __init__(self, sample: pd.DataFrame, w_boot: np.ndarray, measure="lgd_economic"):
        seg = fold(sample["ltv_band"])
        x = sample[measure].to_numpy(float)
        self.labels = sorted(seg.unique())
        self.value, self.draws = {}, {}
        for lab in self.labels:
            v, d, _ = S.boot_mean(x, w_boot, (seg == lab).to_numpy())
            self.value[lab], self.draws[lab] = v, d
        v, d, _ = S.boot_mean(x, w_boot)
        self.value["overall"], self.draws["overall"] = v, d
        self.fallback = "other" if "other" in self.labels else "overall"
        self.model = None  # set to a G2Model when G2 passes

    def segment_of(self, ltv_band: pd.Series) -> pd.Series:
        return ltv_band.where(ltv_band.isin(self.labels), self.fallback)


def _row(dim, seg, df, w_boot, mask):
    out = {"dimension": dim, "segment": str(seg)}
    for m in MEASURES:
        v, d, n = S.boot_mean(df[m], w_boot, mask)
        out[m] = S.percentile(v, d, n, "bootstrap_1000")
    return out


def segments(sample: pd.DataFrame, w_boot) -> list[dict]:
    rows = [_row("overall", "all", sample, w_boot, None)]
    dims = {
        "ltv_band": sample["ltv_band"],
        "property_state": sample["property_state"],
        "disposition_type": sample["disposition_type"],
        "default_year": sample["default_period"].dt.year.astype(str),
    }
    for dim, col in dims.items():
        seg = fold(col)
        for lab in sorted(seg.unique()):
            rows.append(_row(dim, lab, sample, w_boot, (seg == lab).to_numpy()))
    return rows


def downturn(sample: pd.DataFrame) -> tuple[list[dict], SegmentLGD | None]:
    """Mean lgd_gross_of_mi of defaults dated 2008-01 to 2011-12, by LTV band (section 9)."""
    dt = sample[sample.default_period.between("2008-01-01", "2011-12-01")].reset_index(drop=True)
    if dt.empty:
        return [], None
    seg = SegmentLGD(dt, S.boot_weights(len(dt)), "lgd_gross_of_mi")
    rows = []
    folded = fold(dt["ltv_band"])
    for lab in seg.labels:
        n = int((folded == lab).sum())
        rows.append(
            {
                "ltv_band": lab,
                "lgd_gross_of_mi": S.percentile(
                    seg.value[lab], seg.draws[lab], n, "bootstrap_1000"
                ),
            }
        )
    return rows, seg


def resolution_mix(defaults: pd.DataFrame) -> list[dict]:
    d = defaults.assign(default_year=defaults.default_period.dt.year)
    tot = d.groupby("default_year").size()
    rows = []
    for (yr, res), n in d.groupby(["default_year", "resolution"]).size().items():
        rows.append(
            {
                "default_year": int(yr),
                "resolution": res,
                "n_defaults": int(n),
                "share": S.wilson(n, tot[yr]),
            }
        )
    return rows


def _overall(x) -> tuple[float, np.ndarray, int]:
    return S.boot_mean(x, S.boot_weights(len(x)))


def sensitivities(sample, defaults, dim_loan) -> tuple[list[dict], dict]:
    """The two pre-registered LGD sensitivities (D8)."""
    primary = sample["lgd_economic"].mean()
    d = defaults[defaults.default_period <= LGD_SAMPLE_END].merge(
        dim_loan[["loan_id", "terminal_zero_balance_code", "ltv_band"]], on="loan_id", how="left"
    )
    out, info = [], {}
    # (a) zero-loss exclusions, always run: cured_active and code-16 exits enter with LGD 0.
    zero = d[
        (d.resolution == "cured_active")
        | ((d.resolution == "other_exit") & (d.terminal_zero_balance_code == 16))
    ]
    x = np.concatenate([sample["lgd_economic"].to_numpy(float), np.zeros(len(zero))])
    v, draws, n = _overall(x)
    out.append(
        {
            "name": "zero_loss_exclusions",
            "status": "run",
            "lgd_economic": S.percentile(v, draws, n, "bootstrap_1000"),
            "delta_vs_primary": float(v - primary),
        }
    )
    info["zero_loss_added"] = len(zero)
    # (b) open workouts, run only if open defaults exceed 10% of the 36-month sample: each takes
    # its LTV-band segment's 90th-percentile lgd_economic.
    n_open = int((d.resolution == "open").sum())
    share = n_open / len(d) if len(d) else 0.0
    info["open_share"], info["n_open"], info["n_36m"] = share, n_open, len(d)
    if share > 0.10:
        seg = fold(sample["ltv_band"])
        p90 = sample.groupby(seg)["lgd_economic"].quantile(0.9)
        open_band = d.loc[d.resolution == "open", "ltv_band"]
        open_seg = open_band.where(open_band.isin(p90.index), "other" if "other" in p90 else None)
        fill = open_seg.map(p90).fillna(sample["lgd_economic"].quantile(0.9))
        x = np.concatenate([sample["lgd_economic"].to_numpy(float), fill.to_numpy(float)])
        v, draws, n = _overall(x)
        out.append(
            {
                "name": "open_workouts_p90",
                "status": "run",
                "lgd_economic": S.percentile(v, draws, n, "bootstrap_1000"),
                "delta_vs_primary": float(v - primary),
            }
        )
    else:
        out.append(
            {
                "name": "open_workouts_p90",
                "status": "not_needed",
                "lgd_economic": None,
                "delta_vs_primary": None,
            }
        )
    return out, info


def reconciliation(le: pd.DataFrame) -> tuple[dict, list[dict]]:
    """R5 (computed against Freddie Mac actual loss) and R6 (expenses against components)."""
    has = le[le.freddie_actual_loss.notna()]
    d5 = (has.computed_loss - has.freddie_actual_loss).abs()
    comp = le[
        [
            "legal_costs",
            "maintenance_and_preservation_costs",
            "taxes_and_insurance",
            "miscellaneous_expenses",
        ]
    ].sum(1)
    d6 = (le.total_expenses - comp).abs()
    rec = {
        "computed_vs_actual_within_1usd": S.metric(
            float((d5 <= 1).mean()) if len(d5) else None,
            n=len(d5),
            method="none: population check, not an estimate",
        ),
        "expenses_within_1usd": S.metric(
            float((d6 <= 1).mean()) if len(d6) else None,
            n=len(d6),
            method="none: population check, not an estimate",
        ),
    }
    rules = []
    for rid, d in [("R5", d5), ("R6", d6)]:
        if len(d) == 0:
            rules.append({"rule_id": rid, "result": "NOT_RUN", "evidence": "no events to check"})
            continue
        share = float((d <= 1).mean())
        rules.append(
            {
                "rule_id": rid,
                "result": "PASS" if share >= 0.995 else "FAIL",
                "evidence": f"{len(d)} events checked, {int((d > 1).sum())} outside $1 "
                f"(share within {share:.4f}, rule >= 0.995), largest difference ${d.max():,.2f}",
            }
        )
    return rec, rules


# --- G2: two-stage LGD model (stretch) -------------------------------------------------------
def g2_features(df: pd.DataFrame) -> pd.DataFrame:
    upb = df["original_upb"]
    size = np.select(
        [upb <= 100e3, upb <= 200e3, upb <= 300e3, upb <= 450e3],
        ["le_100k", "100_200k", "200_300k", "300_450k"],
        "gt_450k",
    )
    mi = df["mi_pct"].fillna(0)
    return pd.DataFrame(
        {
            "ltv_band": df["ltv_band"].to_numpy(),
            "mi_band": np.select([mi <= 0, mi <= 25], ["none", "1_25"], "gt_25"),
            "size_band": size,
            "occupancy": df["occupancy_status"].fillna("missing").to_numpy(),
            "property_type": df["property_type"].fillna("missing").to_numpy(),
            "state_group": df["property_state"].to_numpy(),
        },
        index=df.index,
    )


def _levels(train: pd.DataFrame) -> dict:
    """Levels with fewer than 50 training defaults are pooled into 'other'; the most common
    level is the reference."""
    cats = {}
    for col in train:
        f = fold(train[col])
        cats[col] = list(f.value_counts().index)
    return cats


def _apply_levels(feat: pd.DataFrame, cats: dict) -> pd.DataFrame:
    return pd.DataFrame(
        {c: feat[c].where(feat[c].isin(cats[c]), "other") for c in cats}, index=feat.index
    )


class G2Model:
    def __init__(self, df: pd.DataFrame):
        feat = g2_features(df)
        self.cats = _levels(feat)
        f = _apply_levels(feat, self.cats)
        X, _ = S.design(f, self.cats)
        self.keep = S.independent_columns(X)
        X = X[:, self.keep]
        y = df["lgd_economic"].to_numpy(float)
        pos = y > 0
        self.b1, _, ok1 = S.fit_mnlogit(X, np.column_stack([~pos, pos]).astype(float))
        sev = np.clip(y[pos], 0, 1)
        self.b2, _, ok2 = S.fit_mnlogit(X[pos], np.column_stack([1 - sev, sev]))
        self.converged = ok1 and ok2

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        X, _ = S.design(_apply_levels(g2_features(df), self.cats), self.cats)
        X = X[:, self.keep]
        return S.probs(X, self.b1)[:, 1] * S.probs(X, self.b2)[:, 1]


def g2(sample: pd.DataFrame, dim_loan: pd.DataFrame):
    """Fit on defaults to 2010-12, compare MAE with the LTV-band segment mean on 2011-01 to
    2023-03 by a paired bootstrap; used in ECL only if the whole interval is below 0."""
    cols = ["loan_id", "original_upb", "mi_pct", "occupancy_status", "property_type"]
    df = sample.merge(dim_loan[cols], on="loan_id", how="left")
    train, test = df[df.default_period <= G2_SPLIT], df[df.default_period > G2_SPLIT]
    if len(train) < MIN_SEGMENT or len(test) < MIN_SEGMENT:
        return None, "fewer than 50 training or held-out defaults"
    model = G2Model(train)
    if not model.converged:
        return None, "a stage did not converge"
    seg = train.groupby(fold(train["ltv_band"]))["lgd_economic"].mean()
    bands = test["ltv_band"].where(test["ltv_band"].isin(seg.index), "other")
    bench = bands.map(seg).fillna(train["lgd_economic"].mean()).to_numpy(float)
    y = test["lgd_economic"].to_numpy(float)
    diff = np.abs(y - model.predict(test)) - np.abs(y - bench)
    w = S.boot_weights(len(test))
    draws = w @ diff / w.sum(1)
    m = S.percentile(float(diff.mean()), draws, len(test), "paired_bootstrap_1000")
    return {"delta_mae": m, "passed": m["ci_high"] < 0, "train_n": len(train)}, None


def build(le: pd.DataFrame, defaults: pd.DataFrame, dim_loan: pd.DataFrame):
    """lgd_ead.json body (without the envelope) and the LGD object the ECL uses."""
    le = le.copy()
    le["default_period"] = pd.to_datetime(le["default_period"])
    defaults = defaults.copy()
    defaults["default_period"] = pd.to_datetime(defaults["default_period"])
    sample = le[le.in_lgd_sample].reset_index(drop=True)
    w = S.boot_weights(len(sample))
    ecl_lgd = SegmentLGD(sample, w)

    v, d, n = _overall(defaults["ead"].to_numpy(float))
    sens, sens_info = sensitivities(sample, defaults, dim_loan)
    dt_rows, dt_seg = downturn(sample)
    x = sample["lgd_economic"]
    rec, rules = reconciliation(le)

    g2_res, g2_err = g2(sample, dim_loan)
    used = bool(g2_res and g2_res["passed"])
    if g2_res is None:
        rules.append({"rule_id": "G2", "result": "NOT_RUN", "evidence": g2_err})
        lgd_model = {"status": "not_run", "used_in_ecl": False, "delta_mae": None}
    else:
        m = g2_res["delta_mae"]
        rules.append(
            {
                "rule_id": "G2",
                "result": "PASS" if used else "FAIL",
                "evidence": f"MAE(model) - MAE(LTV-band mean) on {m['n']} held-out defaults "
                f"(2011-01 to 2023-03) = {m['value']:.4f}, 95% paired bootstrap "
                f"[{m['ci_low']:.4f}, {m['ci_high']:.4f}]; the model is used only if the whole "
                f"interval is below 0. Fitted on {g2_res['train_n']} defaults to 2010-12.",
            }
        )
        lgd_model = {"status": "run", "used_in_ecl": used, "delta_mae": m}
    if used:  # refit on the whole LGD sample for use in ECL
        cols = ["loan_id", "original_upb", "mi_pct", "occupancy_status", "property_type"]
        ecl_lgd.model = G2Model(sample.merge(dim_loan[cols], on="loan_id", how="left"))

    body = {
        "ead": {
            "ccf_applied": False,
            "mean_ead": S.percentile(v, d, n, "bootstrap_1000"),
        },
        "lgd_segments": segments(sample, w),
        "downturn_lgd": dt_rows,
        "resolution_mix": resolution_mix(defaults),
        "sensitivities": sens,
        "lgd_distribution": {
            "share_above_1": S.wilson((x > 1).sum(), len(x)),
            "share_below_0": S.wilson((x < 0).sum(), len(x)),
        },
        "reconciliation": rec,
        "lgd_model": lgd_model,
        "pass_rules": rules,
    }
    ecl_lgd.downturn = dt_seg
    ecl_lgd.sens_info = sens_info
    return body, ecl_lgd
