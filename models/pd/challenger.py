"""LightGBM challenger (VALIDATION_PLAN.md section 5) on the scorecard's raw candidate features.

Tuned by five-fold cross-validation on dev_train, confirmed once on dev_test, refitted on all of
dev_train. SHAP values are LightGBM's own TreeSHAP contributions (`pred_contrib=True`).
"""

import hashlib
import itertools

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold

from models.pd.metrics import SEED, auc_ks
from models.pd.scorecard import CANDIDATES, NUMERIC_TREND

# Expected direction of default risk; original_upb has none assumed, so it is unconstrained.
MONOTONE = {f: {"descending": -1, "ascending": 1}.get(t, 0) for f, t in NUMERIC_TREND.items()}
BASE_PARAMS = dict(
    objective="binary",
    metric="auc",
    learning_rate=0.05,
    feature_fraction=0.8,
    bagging_fraction=0.8,
    bagging_freq=1,
    seed=SEED,
    deterministic=True,
    force_row_wise=True,
    verbose=-1,
)
GRID = list(itertools.product([15, 31], [200, 1000], [0, 10]))  # num_leaves, min_child, l2
MAX_ROUNDS, EARLY_STOP, CONFIRM_TOLERANCE = 2000, 50, 0.02


def design(df: pd.DataFrame, categories: dict) -> pd.DataFrame:
    """Raw candidate features: numeric as float, the rest as categoricals with dev_train's
    categories (a category unseen in dev_train becomes missing)."""
    out = {}
    for f in CANDIDATES:
        if f in NUMERIC_TREND:
            out[f] = df[f].astype(float)
        else:
            out[f] = pd.Categorical(df[f].astype("string"), categories=categories[f])
    return pd.DataFrame(out, index=df.index)


def _params(num_leaves, min_child, l2):
    return {
        **BASE_PARAMS,
        "num_leaves": num_leaves,
        "min_child_samples": min_child,
        "lambda_l2": l2,
        "monotone_constraints": [MONOTONE.get(f, 0) for f in CANDIDATES],
    }


def fit(train: pd.DataFrame, test: pd.DataFrame) -> dict:
    """Tune, confirm and refit. Returns the frozen challenger with its CV record."""
    categories = {
        f: sorted(train[f].dropna().astype(str).unique())
        for f in CANDIDATES
        if f not in NUMERIC_TREND
    }
    x, y = design(train, categories), train["default_12m"].astype(int).to_numpy()
    folds = list(StratifiedKFold(5, shuffle=True, random_state=SEED).split(x, y))
    results = []
    for num_leaves, min_child, l2 in GRID:
        aucs, rounds = [], []
        for tr, va in folds:
            booster = lgb.train(
                _params(num_leaves, min_child, l2),
                lgb.Dataset(x.iloc[tr], y[tr]),
                MAX_ROUNDS,
                valid_sets=[lgb.Dataset(x.iloc[va], y[va])],
                callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)],
            )
            aucs.append(booster.best_score["valid_0"]["auc"])
            rounds.append(booster.best_iteration)
        results.append(
            {
                "num_leaves": num_leaves,
                "min_child_samples": min_child,
                "lambda_l2": l2,
                "mean_fold_auc": float(np.mean(aucs)),
                "mean_best_round": float(np.mean(rounds)),
            }
        )
    # Highest mean fold AUC; ties to fewer leaves, then more min_child_samples, then more l2.
    best = min(
        results,
        key=lambda r: (
            -r["mean_fold_auc"],
            r["num_leaves"],
            -r["min_child_samples"],
            -r["lambda_l2"],
        ),
    )
    n_rounds = max(1, int(np.floor(best["mean_best_round"] + 0.5)))
    booster = lgb.train(
        _params(best["num_leaves"], best["min_child_samples"], best["lambda_l2"]),
        lgb.Dataset(x, y),
        n_rounds,
    )
    test_auc = auc_ks(booster.predict(design(test, categories)), test["default_12m"])[0]
    model_string = booster.model_to_string()
    return {
        "booster": booster,
        "categories": categories,
        "cv": results,
        "chosen": best,
        "n_rounds": n_rounds,
        "dev_test_auc": test_auc,
        "confirm_passed": bool(test_auc >= best["mean_fold_auc"] - CONFIRM_TOLERANCE),
        "model_id": "lgbm-" + hashlib.sha256(model_string.encode()).hexdigest()[:12],
    }


def predict(ch: dict, df: pd.DataFrame, allow_oot: bool = False) -> np.ndarray:
    """Challenger PD. Out-of-time and COVID rows only through run.score_out_of_time (P3)."""
    if not allow_oot and df["sample"].isin(["oot", "covid"]).any():
        raise PermissionError(
            "oot and covid loans are scored only through run.score_out_of_time (plan P3)"
        )
    return ch["booster"].predict(design(df, ch["categories"]))


def shap_values(ch: dict, df: pd.DataFrame) -> np.ndarray:
    """TreeSHAP contributions per loan and feature (log-odds scale), bias column dropped."""
    return ch["booster"].predict(design(df, ch["categories"]), pred_contrib=True)[:, :-1]


def monotone_constraints_hold(ch: dict, df: pd.DataFrame, n_loans: int = 500) -> bool:
    """Vary each constrained feature over its dev_train deciles for up to n_loans loans and check
    that the predicted PD moves only in the constrained direction."""
    x = design(df.head(n_loans), ch["categories"])
    for f, sign in MONOTONE.items():
        if sign == 0:
            continue
        grid = np.unique(np.nanquantile(df[f].astype(float), np.linspace(0, 1, 11)))
        preds = []
        for v in grid:
            x2 = x.copy()
            x2[f] = v
            preds.append(ch["booster"].predict(x2))
        steps = np.diff(np.array(preds), axis=0) * sign
        if (steps < -1e-12).any():
            return False
    return True
