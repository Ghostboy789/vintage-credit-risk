"""The application scorecard (VALIDATION_PLAN.md section 3): WoE binning, screening, logistic
regression with mechanical elimination, PDO points, the PD master scale and reason codes.

Everything is fitted on `dev_train` only. The fitted model is a plain JSON-serialisable dict, and
scoring uses nothing but that dict, so the published points table is the whole model.
"""

import hashlib
import json
import math

import numpy as np
import pandas as pd
import statsmodels.api as sm
from optbinning import OptimalBinning
from statsmodels.stats.outliers_influence import variance_inflation_factor

# Candidate order also breaks every tie: the earlier feature is kept.
CANDIDATES = [
    "fico",
    "ltv_pct",
    "cltv_pct",
    "dti_pct",
    "mi_pct",
    "rate_spread_pct",
    "original_upb",
    "term_band",
    "loan_purpose",
    "occupancy_status",
    "property_type",
    "number_of_units",
    "channel",
    "first_time_homebuyer",
    "super_conforming",
]
NUMERIC_TREND = {
    "fico": "descending",
    "ltv_pct": "ascending",
    "cltv_pct": "ascending",
    "dti_pct": "ascending",
    "mi_pct": "ascending",
    "rate_spread_pct": "ascending",
    "original_upb": "auto_asc_desc",
}
BINNING_PARAMS = dict(
    solver="cp",
    prebinning_method="cart",
    max_n_prebins=20,
    min_prebin_size=0.05,
    min_bin_size=0.05,
    max_n_bins=8,
    min_bin_n_event=20,
    split_digits=4,
    time_limit=600,
)
CAT_CUTOFF = 0.05
MIN_MISSING_EVENTS = 20
IV_MIN, IV_REVIEW = 0.02, 0.5
CORR_MAX = 0.7
P_MAX = 0.01
VIF_MAX = 5.0
MAX_FEATURES = 12

BASE_SCORE, BASE_ODDS, PDO = 600, 50.0, 20
FACTOR = PDO / math.log(2)
OFFSET = BASE_SCORE - FACTOR * math.log(BASE_ODDS)
PD_LABEL = "12-month PD, 1999-2015 development average"

MASTER_SCALE = [
    ("A", 0.0, 0.001),
    ("B", 0.001, 0.002),
    ("C", 0.002, 0.004),
    ("D", 0.004, 0.008),
    ("E", 0.008, 0.016),
    ("F", 0.016, 0.032),
    ("G", 0.032, 1.0),
]
MERGE_ORDER = "AGBFCED"
MIN_GRADE_SHARE, MIN_GRADE_DEFAULTS = 0.01, 20


# ---------------------------------------------------------------------------------------------
# Binning
# ---------------------------------------------------------------------------------------------
def feature_values(df: pd.DataFrame, feature: str) -> np.ndarray:
    """Numeric features as floats (NaN missing); categorical ones as strings (None missing).
    `number_of_units` and `super_conforming` are binned as categories, so they become strings."""
    s = df[feature]
    if feature in NUMERIC_TREND:
        return s.astype(float).to_numpy()
    if feature == "number_of_units" or feature == "number_of_borrowers":
        return np.array([None if pd.isna(v) else str(int(v)) for v in s], dtype=object)
    if feature == "super_conforming":
        return np.array([None if pd.isna(v) else str(bool(v)).lower() for v in s], dtype=object)
    return np.array([None if pd.isna(v) else str(v) for v in s], dtype=object)


def woe_iv(nonevent, event) -> tuple[np.ndarray, float]:
    """WoE = ln(share of non-defaults in bin / share of defaults in bin), and the IV.

    The single place WoE is computed. A bin with no defaults or no non-defaults has no finite
    WoE (NaN) and adds nothing to the IV.
    """
    g = np.asarray(nonevent, float) / np.sum(nonevent)
    b = np.asarray(event, float) / np.sum(event)
    with np.errstate(divide="ignore", invalid="ignore"):
        woe = np.where((g > 0) & (b > 0), np.log(g / b), np.nan)
    iv = float(np.nansum((g - b) * woe))
    return woe, iv


def _is_monotonic(woe: list, trend: str) -> bool:
    d = np.diff(woe)
    up, down = bool((d >= 0).all()), bool((d <= 0).all())
    # Default rate falling as the value rises means WoE rising, and the reverse.
    return {"descending": up, "ascending": down, "auto_asc_desc": up or down}[trend]


def fit_binning(values: np.ndarray, y: np.ndarray, feature: str) -> dict:
    """Bin one feature on dev_train with the pinned optbinning parameters.

    Returns the bins (non-missing bins in order, then the missing bin) with counts and WoE, the
    IV, and `drop_reason` (None if the feature passes the binning checks).
    """
    numeric = feature in NUMERIC_TREND
    if numeric:
        ob = OptimalBinning(
            feature, dtype="numerical", monotonic_trend=NUMERIC_TREND[feature], **BINNING_PARAMS
        )
    else:
        ob = OptimalBinning(
            feature,
            dtype="categorical",
            monotonic_trend=None,
            cat_cutoff=CAT_CUTOFF,
            **BINNING_PARAMS,
        )
    ob.fit(values, y)
    table = ob.binning_table.build()
    nonevent = table["Non-event"].iloc[:-1].to_numpy()  # drop the Totals row
    event = table["Event"].iloc[:-1].to_numpy()
    labels = list(table.index[:-1])
    # Rows: the regular bins, then Special (always empty: no special codes), then Missing.
    n_regular = len(labels) - 2
    keep = list(range(n_regular)) + [n_regular + 1]
    nonevent, event = nonevent[keep].astype(int), event[keep].astype(int)
    woe, iv = woe_iv(nonevent, event)

    splits = ob.splits
    others = getattr(ob, "_cat_others", None)
    others = [] if others is None else [str(c) for c in others]
    bins = []
    for i in range(n_regular):
        if numeric:
            lower = float(splits[i - 1]) if i > 0 else None
            upper = float(splits[i]) if i < len(splits) else None
            label = f"[{'-inf' if lower is None else f'{lower:g}'}, "
            label += f"{'inf' if upper is None else f'{upper:g}'})"
            cats = []
        else:
            lower = upper = None
            cats = [str(c) for c in splits[i]]
            label = "[" + ", ".join(cats) + "]"
        bins.append(
            {
                "bin": label,
                "lower": lower,
                "upper": upper,
                "categories": cats,
                "is_missing_bin": False,
                "is_other_bin": bool(set(cats) & set(others)),
                "nonevent": int(nonevent[i]),
                "event": int(event[i]),
                "woe_raw": None if np.isnan(woe[i]) else float(woe[i]),
            }
        )
    bins.append(
        {
            "bin": "Missing",
            "lower": None,
            "upper": None,
            "categories": [],
            "is_missing_bin": True,
            "is_other_bin": False,
            "nonevent": int(nonevent[-1]),
            "event": int(event[-1]),
            "woe_raw": None if np.isnan(woe[-1]) else float(woe[-1]),
        }
    )

    regular_woe = [b["woe_raw"] for b in bins[:-1]]
    drop = None
    if ob.status not in ("OPTIMAL", "FEASIBLE"):
        drop = f"binning status {ob.status}"
    elif n_regular < 2:
        drop = "binning returned a single non-missing bin"
    elif any(w is None for w in regular_woe):
        # Cannot happen with min_bin_n_event=20 unless a bin has no non-defaults; never guess.
        raise RuntimeError(f"{feature}: a non-missing bin has no finite WoE")
    elif numeric and not _is_monotonic(regular_woe, NUMERIC_TREND[feature]):
        drop = "WoE not monotonic in the expected direction"

    # The WoE used by the model: the missing bin takes the highest-risk (lowest) WoE of the
    # feature when it has fewer than 20 defaults.
    missing = bins[-1]
    missing["woe_substituted"] = missing["event"] < MIN_MISSING_EVENTS
    for b in bins[:-1]:
        b["woe"] = b["woe_raw"]
        b["woe_substituted"] = False
    if drop is None:
        missing["woe"] = min(regular_woe) if missing["woe_substituted"] else missing["woe_raw"]
    else:
        missing["woe"] = missing["woe_raw"]
    return {
        "feature": feature,
        "numeric": numeric,
        "status": ob.status,
        "splits": [float(s) for s in splits] if numeric else None,
        "bins": bins,
        "iv": iv,
        "drop_reason": drop,
    }


def bin_index(binning: dict, values: np.ndarray) -> np.ndarray:
    """Position of each value's bin in binning['bins']. Missing values go to the missing bin; a
    category not seen in dev_train goes to the bin holding the grouped rare categories (it is
    rarer than the 5% cut-off), or to the missing bin if there is no such bin."""
    bins = binning["bins"]
    missing = len(bins) - 1
    if binning["numeric"]:
        x = np.asarray(values, float)
        idx = np.searchsorted(np.array(binning["splits"], float), x, side="right")
        return np.where(np.isnan(x), missing, idx)
    lookup = {c: i for i, b in enumerate(bins) for c in b["categories"]}
    other = next((i for i, b in enumerate(bins) if b["is_other_bin"]), missing)
    return np.array([missing if v is None else lookup.get(v, other) for v in values], dtype=int)


def woe_matrix(binnings: dict, df: pd.DataFrame, features: list) -> pd.DataFrame:
    out = {}
    for f in features:
        woe = np.array([b["woe"] for b in binnings[f]["bins"]], float)
        out[f] = woe[bin_index(binnings[f], feature_values(df, f))]
    return pd.DataFrame(out, index=df.index)


# ---------------------------------------------------------------------------------------------
# Screening and model
# ---------------------------------------------------------------------------------------------
def _order(f: str) -> int:
    return CANDIDATES.index(f) if f in CANDIDATES else len(CANDIDATES)


def _drop_largest(values: pd.Series) -> str:
    """Feature with the largest value; on a tie the later candidate is dropped."""
    return max(values.index, key=lambda f: (values[f], _order(f)))


def fit_logit(y, x: pd.DataFrame):
    res = sm.Logit(np.asarray(y, float), sm.add_constant(x, has_constant="add")).fit(
        method="newton", maxiter=100, disp=0
    )
    if not res.mle_retvals.get("converged", False):
        raise RuntimeError(f"logistic regression did not converge on {list(x.columns)}")
    return res


def select_and_fit(binnings: dict, x_woe: pd.DataFrame, y) -> tuple[list, dict, object]:
    """Steps 2 to 5 of the screening: IV screen, correlation screen, logistic regression and
    one-feature-per-refit elimination. Returns (final features, drop reasons, fitted model)."""
    reasons = {f: b["drop_reason"] for f, b in binnings.items() if b["drop_reason"]}
    kept = [f for f in CANDIDATES if f in binnings and f not in reasons]
    for f in list(kept):
        if binnings[f]["iv"] < IV_MIN:
            reasons[f] = f"IV {binnings[f]['iv']:.4f} below {IV_MIN}"
            kept.remove(f)

    corr = x_woe[kept].corr().abs()
    pairs = [
        (corr.loc[a, b], a, b)
        for i, a in enumerate(kept)
        for b in kept[i + 1 :]
        if corr.loc[a, b] > CORR_MAX
    ]
    # Descending correlation; equal correlations in candidate order, so the result is fixed.
    for r, a, b in sorted(pairs, key=lambda p: (-p[0], _order(p[1]), _order(p[2]))):
        if a in kept and b in kept:
            ia, ib = binnings[a]["iv"], binnings[b]["iv"]
            loser = b if ia >= ib else a  # equal IV: the later candidate (b) goes
            winner = a if loser == b else b
            reasons[loser] = f"|correlation| {r:.3f} with {winner}, lower IV"
            kept.remove(loser)

    while True:
        if not kept:
            raise RuntimeError("every candidate feature was dropped")
        res = fit_logit(y, x_woe[kept])
        coef, pval = res.params[kept], res.pvalues[kept]
        exog = sm.add_constant(x_woe[kept], has_constant="add").to_numpy()
        vif = pd.Series(
            [variance_inflation_factor(exog, i + 1) for i in range(len(kept))], index=kept
        )
        if (coef > 0).any():
            f = _drop_largest(coef[coef > 0])
            reasons[f] = f"elimination: positive coefficient {coef[f]:.4f}"
        elif (pval > P_MAX).any():
            f = _drop_largest(pval)
            reasons[f] = f"elimination: p-value {pval[f]:.4g} above {P_MAX}"
        elif (vif >= VIF_MAX).any():
            f = _drop_largest(vif)
            reasons[f] = f"elimination: VIF {vif[f]:.2f} at or above {VIF_MAX:g}"
        elif len(kept) > MAX_FEATURES:
            z = res.tvalues[kept].abs()
            f = min(kept, key=lambda k: (z[k], -_order(k)))
            reasons[f] = f"elimination: smallest |z| {z[f]:.3f} with more than {MAX_FEATURES}"
        else:
            return kept, reasons, res
        kept.remove(f)


# ---------------------------------------------------------------------------------------------
# Points, grades, scoring
# ---------------------------------------------------------------------------------------------
def round_half_away(x: float) -> int:
    """Round half away from zero, as spreadsheet ROUND does."""
    return int(math.copysign(math.floor(abs(x) + 0.5), x))


def points(beta: float, woe: float, intercept: float, k: int) -> int:
    return round_half_away(-FACTOR * beta * woe + (OFFSET - FACTOR * intercept) / k)


def pd_from_score(score):
    return 1.0 / (1.0 + np.exp((np.asarray(score, float) - OFFSET) / FACTOR))


def score_threshold(pd_value: float) -> float:
    """The score at which pd_12m equals pd_value (pd falls as the score rises)."""
    return OFFSET + FACTOR * math.log(1.0 / pd_value - 1.0)


def master_letter(pd_values) -> np.ndarray:
    """Letter on the unmerged master scale: [pd_low, pd_high)."""
    cuts = np.array([hi for _, _, hi in MASTER_SCALE[:-1]])
    return np.array([g for g, _, _ in MASTER_SCALE])[np.searchsorted(cuts, pd_values, "right")]


def fit_grades(pd_train, y_train) -> list:
    """Master-scale grades after the section 3 merge rule, decided on dev_train only."""
    letters = master_letter(pd_train)
    y = np.asarray(y_train)
    n_total = len(y)
    members = {g: {g} for g, _, _ in MASTER_SCALE}  # surviving grade -> original letters
    merged_into = {}
    scale = [g for g, _, _ in MASTER_SCALE]

    def counts(g):
        m = np.isin(letters, list(members[g]))
        return int(m.sum()), int(y[m].sum())

    def fails(g):
        n, d = counts(g)
        return n < MIN_GRADE_SHARE * n_total or d < MIN_GRADE_DEFAULTS

    changed = True
    while changed and len(members) > 1:
        changed = False
        for g in MERGE_ORDER:
            if g not in members or not fails(g):
                continue
            alive = [s for s in scale if s in members]
            i = alive.index(g)
            left = alive[i - 1] if i > 0 else None
            right = alive[i + 1] if i + 1 < len(alive) else None
            if g == "D":
                cands = [c for c in (left, right) if c]
                target = max(cands, key=lambda c: (counts(c)[0], c == left))
            else:
                towards_d = right if scale.index(g) < scale.index("D") else left
                target = towards_d or left or right
            members[target] |= members.pop(g)
            for letter in [g] + [k for k, v in merged_into.items() if v == g]:
                merged_into[letter] = target
            changed = True
            break

    grades = []
    for g, lo, hi in MASTER_SCALE:
        if g in members:
            letters_g = members[g]
            lo = min(lo2 for g2, lo2, _ in MASTER_SCALE if g2 in letters_g)
            hi = max(hi2 for g2, _, hi2 in MASTER_SCALE if g2 in letters_g)
        n, d = counts(g) if g in members else (None, None)
        grades.append(
            {
                "grade": g,
                "pd_low": lo,
                "pd_high": hi,
                # pd >= pd_low means score <= threshold(pd_low); pd < pd_high means score above
                # threshold(pd_high). Open ends are null.
                "score_min": None if hi >= 1.0 else math.floor(score_threshold(hi)) + 1,
                "score_max": None if lo <= 0.0 else math.floor(score_threshold(lo)),
                "merged_into": merged_into.get(g),
                "n_dev_train": n,
                "defaults_dev_train": d,
            }
        )
    return grades


def grade_of(pd_values, grades: list) -> np.ndarray:
    survivor = {g["grade"]: g["merged_into"] or g["grade"] for g in grades}
    return np.array([survivor[x] for x in master_letter(pd_values)], dtype=object)


def points_matrix(model: dict, df: pd.DataFrame) -> np.ndarray:
    """Points per loan (rows) and model feature (columns, in candidate order)."""
    cols = []
    for f in model["features"]:
        b = model["binnings"][f]
        pts = np.array([x["points"] for x in b["bins"]], int)
        cols.append(pts[bin_index(b, feature_values(df, f))])
    return np.column_stack(cols)


def score(model: dict, df: pd.DataFrame, allow_oot: bool = False) -> pd.DataFrame:
    """Score, PD, grade and the three reason codes for every row.

    Refuses out-of-time and COVID rows unless called from the one guarded out-of-time function
    (VALIDATION_PLAN P3), which is the only caller that passes allow_oot=True.
    """
    if not allow_oot and df["sample"].isin(["oot", "covid"]).any():
        raise PermissionError(
            "oot and covid loans are scored only through run.score_out_of_time (plan P3)"
        )
    pts = points_matrix(model, df)
    total = pts.sum(axis=1)
    pd_12m = pd_from_score(total)
    out = pd.DataFrame(
        {
            "loan_id": df["loan_id"].to_numpy(),
            "sample": df["sample"].to_numpy(),
            "model_id": model["model_id"],
            "score": total.astype("int64"),
            "pd_12m": pd_12m,
            "grade": grade_of(pd_12m, model["grades"]),
        },
        index=df.index,
    )
    max_pts = np.array(
        [max(b["points"] for b in model["binnings"][f]["bins"]) for f in model["features"]]
    )
    shortfall = max_pts[None, :] - pts
    order = np.argsort(-shortfall, axis=1, kind="stable")  # ties keep candidate order
    names = np.array(model["features"], dtype=object)
    for r in range(3):
        if r < len(names):
            col = order[:, r]
            short = shortfall[np.arange(len(df)), col]
            out[f"reason_{r + 1}"] = np.where(short > 0, names[col], None)
        else:
            out[f"reason_{r + 1}"] = None
    return out


# ---------------------------------------------------------------------------------------------
# Fit end to end
# ---------------------------------------------------------------------------------------------
def fit(train: pd.DataFrame) -> dict:
    """Fit the scorecard on dev_train and return the frozen model dict (with its model_id)."""
    if not (train["sample"] == "dev_train").all():
        raise ValueError("the scorecard is fitted on dev_train only")
    y = train["default_12m"].astype(int).to_numpy()
    binnings = {f: fit_binning(feature_values(train, f), y, f) for f in CANDIDATES}
    usable = [f for f in CANDIDATES if binnings[f]["drop_reason"] is None]
    x_woe = woe_matrix(binnings, train, usable)
    features, reasons, res = select_and_fit(binnings, x_woe, y)
    intercept = float(res.params["const"])
    coefs = {f: float(res.params[f]) for f in features}
    for f in features:
        for b in binnings[f]["bins"]:
            b["points"] = points(coefs[f], b["woe"], intercept, len(features))
    model = {
        "features": features,
        "intercept": intercept,
        "coefficients": coefs,
        "binnings": {f: binnings[f] for f in features},
        "factor": FACTOR,
        "offset": OFFSET,
    }
    train_pd = pd_from_score(points_matrix(model, train).sum(axis=1))
    model["grades"] = fit_grades(train_pd, y)
    frozen = {
        "features": features,
        "points": {f: [[b["bin"], b["points"]] for b in binnings[f]["bins"]] for f in features},
        "grades": [[g["grade"], g["merged_into"]] for g in model["grades"]],
        "offset": OFFSET,
        "factor": FACTOR,
    }
    digest = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
    model["model_id"] = "scorecard-" + digest[:12]
    # Every candidate's binning, with the reason it left the model (None if selected).
    model["candidates"] = {
        f: {
            **binnings[f],
            "binning_drop_reason": binnings[f]["drop_reason"],
            "drop_reason": reasons.get(f),
            "iv_above_review_level": binnings[f]["iv"] > IV_REVIEW,
        }
        for f in CANDIDATES
    }
    model["n_dev_train"] = int(len(y))
    return model
