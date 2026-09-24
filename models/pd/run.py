"""Run the PD engine end to end: fit the scorecard (and the challenger) on development data, score
the out-of-time and COVID samples once, and write loan_scores, pd_models.json and monitoring.json.

    python -m models.pd.run                       # real marts under VINTAGE_DATA_ROOT
    python -m models.pd.run --fixtures OUT_DIR    # synthetic fixtures, outputs under OUT_DIR

The out-of-time and COVID samples are scored only by `score_out_of_time`, once per model, and
every call is logged (VALIDATION_PLAN P3). Nothing computed before that call touches their
outcomes. If a later step fails, `--reuse-scores` rebuilds the artefacts from the saved scores
without scoring again.
"""

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from config import VINTAGE_DATA_ROOT
from models.pd import challenger as chal
from models.pd import metrics as mt
from models.pd import scorecard as sc
from tests import contracts

REPO = Path(__file__).resolve().parents[2]
DEV = ["dev_train", "dev_test"]
DEFS = {"primary": "default_12m", "naive": "default_12m_naive"}
OOT_LOG = "oot_scoring_log.jsonl"
COVID_FIRST_PAYMENT = (pd.Timestamp("2019-04-01"), pd.Timestamp("2021-12-01"))
DATA_CUTOFF = "2026-03-01"
POP = "none: population count, not an estimate"
D1A_LIMIT = 0.10


# ---------------------------------------------------------------------------------------------
# The one out-of-time scoring function (P3)
# ---------------------------------------------------------------------------------------------
def read_oot_log(models_out: Path) -> list:
    log = Path(models_out) / OOT_LOG
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]


def score_out_of_time(model: dict, ch: dict | None, base: pd.DataFrame, models_out: Path):
    """Score every loan, including `oot` and `covid`, with the frozen scorecard and challenger.

    The only caller allowed to score out-of-time and COVID loans. It refuses to run a second time
    for the same scorecard, and logs the call (timestamp, model ids, counts) to
    models_out/oot_scoring_log.jsonl. A rescoring after a bug fix is a plan deviation: record it
    and move the log entry by hand, never bypass this check.
    """
    if any(e["model_id"] == model["model_id"] for e in read_oot_log(models_out)):
        raise RuntimeError(
            f"out-of-time sample already scored with {model['model_id']}; "
            "a rescoring must be logged as a deviation (VALIDATION_PLAN P3)"
        )
    scored = sc.score(model, base, allow_oot=True)
    if ch is not None:
        scored["challenger_pd"] = chal.predict(ch, base, allow_oot=True)
    entry = {
        "model_id": model["model_id"],
        "challenger_id": ch["model_id"] if ch else None,
        "scored_at": now(),
        "n_loans": int(len(base)),
        "n_oot": int((base["sample"] == "oot").sum()),
        "n_covid": int((base["sample"] == "covid").sum()),
    }
    Path(models_out).mkdir(parents=True, exist_ok=True)
    with (Path(models_out) / OOT_LOG).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return scored, entry


# ---------------------------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------------------------
def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def code_version() -> str:
    try:
        head = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain"], capture_output=True, text=True
        ).stdout.strip()
        return head + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def count_metric(value, n):
    return contracts.metric(float(value), n=int(n), ci_method=POP)


def null_metric(reason, n=0):
    return contracts.metric(None, n=int(n), ci_method="none: " + reason)


def rate_metric(k, n, method):
    if n == 0:
        return null_metric("no loans", 0)
    lo, hi = (mt.jeffreys if method == "jeffreys_95" else mt.wilson)(int(k), int(n))
    return contracts.metric(float(k / n), lo, hi, int(n), method)


def fmt(m: dict) -> str:
    """A metric as text for pass-rule evidence: value [low, high], or the reason for no interval."""
    if m["value"] is None:
        return "not computed"
    if m["ci_low"] is None:
        return f"{m['value']:.4f} (no interval: {m['ci_method'][6:]})"
    return f"{m['value']:.4f} [{m['ci_low']:.4f}, {m['ci_high']:.4f}]"


def boot_metric(value, draws, n, method="bootstrap_1000"):
    """Percentile bootstrap metric. A statistic that resampling biases (PSI, KS) can fall outside
    its own percentile interval; the contract does not allow that, so the interval is then
    withheld and its bounds are given in ci_method instead of being altered."""
    lo, hi = mt.percentile_interval(draws)
    if not lo <= value <= hi:
        return contracts.metric(
            float(value),
            n=int(n),
            ci_method=f"none: {method} percentile interval [{lo:.6g}, {hi:.6g}] excludes the "
            "estimate (resampling bias), so it is not published as the interval",
        )
    return contracts.metric(float(value), lo, hi, int(n), method)


def would_be_sample(frame: pd.DataFrame) -> pd.Series:
    """The P1 sample a loan would have joined if it were not excluded."""
    split = frame["loan_id"].map(
        lambda i: (
            "dev_train"
            if hashlib.md5((i + "split-v1").encode()).hexdigest()[:2] < "b3"
            else "dev_test"
        )
    )
    fpd = pd.to_datetime(frame["first_payment_date"])
    covid = fpd.between(*COVID_FIRST_PAYMENT)
    v = frame["vintage_year"]
    return pd.Series(
        np.select(
            [v >= 2025, v <= 2015, v == 2016, covid],
            ["out_of_scope", split, "gap", "covid"],
            "oot",
        ),
        index=frame.index,
    )


# ---------------------------------------------------------------------------------------------
# Result tables
# ---------------------------------------------------------------------------------------------
def discrimination(frame, risks: dict, sample: str, boot: dict) -> list:
    """AUC, Gini and KS with bootstrap intervals for each model and definition. The bootstrap
    draws are kept in `boot` for the Gini drop and the paired challenger comparison."""
    rows = []
    for defn, col in DEFS.items():
        y = frame[col].astype(int).to_numpy()
        n = len(y)
        if y.sum() == 0 or y.sum() == n:
            for model in risks:
                none = null_metric("the sample has no defaults or no non-defaults", n)
                rows.append(
                    dict(sample=sample, definition=defn, model=model, auc=none, gini=none, ks=none)
                )
            continue
        point, draws = mt.bootstrap_auc_ks(y, [np.asarray(r) for r in risks.values()])
        for j, model in enumerate(risks):
            auc, ks = point[j]
            boot[(sample, defn, model)] = {"gini": 2 * auc - 1, "draws": 2 * draws[:, j, 0] - 1}
            rows.append(
                dict(
                    sample=sample,
                    definition=defn,
                    model=model,
                    auc=boot_metric(auc, draws[:, j, 0], n),
                    gini=boot_metric(2 * auc - 1, 2 * draws[:, j, 0] - 1, n),
                    ks=boot_metric(ks, draws[:, j, 1], n),
                )
            )
    return rows


def calibration(frame, pd_col, grade_col, grades, sample, defn) -> list:
    rows = []
    y = frame[DEFS[defn]].astype(int)
    for g in [g["grade"] for g in grades if g["merged_into"] is None]:
        m = (frame[grade_col] == g).to_numpy()
        n, k = int(m.sum()), int(y[m].sum())
        if n == 0:
            continue
        mean_pd = float(frame.loc[m, pd_col].mean())
        rate = rate_metric(k, n, "jeffreys_95")
        if k < 20:
            result = "INSUFFICIENT"
        else:
            result = "PASS" if rate["ci_low"] <= mean_pd <= rate["ci_high"] else "FAIL"
        rows.append(
            dict(
                sample=sample,
                definition=defn,
                grade=g,
                n=n,
                mean_pd=mean_pd,
                realised_rate=rate,
                result=result,
            )
        )
    return rows


def calibration_rule(rows) -> tuple[str, str]:
    """PASS only if every grade passes; any FAIL fails; otherwise INSUFFICIENT."""
    res = [r["result"] for r in rows]
    detail = "; ".join(
        f"{r['grade']}: mean PD {r['mean_pd']:.4f}, realised {fmt(r['realised_rate'])}, "
        f"n {r['n']}, {r['result']}"
        for r in rows
    )
    if "FAIL" in res:
        return "FAIL", detail
    if res and all(x == "PASS" for x in res):
        return "PASS", detail
    return "INSUFFICIENT", detail or "no graded loans"


def calibration_in_the_large(frame, pd_col, sample, defn):
    y = frame[DEFS[defn]].astype(int)
    n, k = len(y), int(y.sum())
    mean_pd = float(frame[pd_col].mean())
    rate = rate_metric(k, n, "jeffreys_95")
    ratio = contracts.metric(
        rate["value"] / mean_pd,
        rate["ci_low"] / mean_pd,
        rate["ci_high"] / mean_pd,
        n,
        "jeffreys_95_over_mean_pd",
    )
    return dict(sample=sample, definition=defn, mean_pd=mean_pd, realised_rate=rate, ratio=ratio)


def rank_ordering(frame, grades) -> tuple[str, str]:
    """S3 on oot: adjacent surviving grades, riskier grade must not have a lower realised rate."""
    y = frame["default_12m"].astype(int)
    stats = []
    for g in [g["grade"] for g in grades if g["merged_into"] is None]:
        m = (frame["grade"] == g).to_numpy()
        n = int(m.sum())
        if n:
            k = int(y[m].sum())
            stats.append((g, k / n, *mt.jeffreys(k, n), n))
    if len(stats) < 2:
        return "INSUFFICIENT", f"{len(stats)} surviving grade(s) with oot loans; nothing to compare"
    result, notes = "PASS", []
    for (g1, r1, lo1, hi1, _), (g2, r2, lo2, hi2, _) in zip(stats, stats[1:]):
        if r2 < r1:
            if hi2 < lo1:
                result = "FAIL"
                notes.append(f"{g2} below {g1}, intervals apart")
            else:
                result = "AMBER" if result == "PASS" else result
                notes.append(f"{g2} below {g1}, intervals overlap")
    rates = ", ".join(f"{g} {r:.4f} [{lo:.4f}, {hi:.4f}] n {n}" for g, r, lo, hi, n in stats)
    return result, rates + ("; inversions: " + "; ".join(notes) if notes else "; no inversion")


def psi_row(ref_counts, cmp_counts, n):
    value = mt.psi(ref_counts, cmp_counts)
    return boot_metric(value, mt.bootstrap_psi(ref_counts, cmp_counts), n), mt.rag(value)


def score_psi(ref_scores, cmp_scores):
    edges = mt.decile_edges(ref_scores)
    k = len(edges) + 1
    ref = np.bincount(mt.decile_bins(ref_scores, edges), minlength=k)
    cmp_ = np.bincount(mt.decile_bins(cmp_scores, edges), minlength=k)
    metric, rag = psi_row(ref, cmp_, len(cmp_scores))
    return k, metric, rag


def d1a_rows(base, loan_month_path) -> list:
    """D1a counts from the loan-month mart: loans first modified before their first primary
    default (or modified with no primary default), against loans with a primary default."""
    con = duckdb.connect()
    temp = os.environ.get("VINTAGE_DUCKDB_TEMP")
    if temp:
        con.execute(f"SET temp_directory = '{Path(temp).as_posix()}'")
    first_mod = con.execute(
        "SELECT loan_id, min(months_on_book) FILTER (WHERE modified) AS first_mod "
        "FROM read_parquet(?) GROUP BY loan_id",
        [str(loan_month_path)],
    ).df()
    f = base[["loan_id", "sample", "default_months_on_book"]].merge(first_mod, "left", "loan_id")
    num = f["first_mod"].notna() & (
        f["default_months_on_book"].isna() | (f["first_mod"] < f["default_months_on_book"])
    )
    den = f["default_months_on_book"].notna()
    rows = []
    for s in ["all"] + [x for x in contracts.SAMPLES if x in set(f["sample"])]:
        m = np.ones(len(f), bool) if s == "all" else (f["sample"] == s).to_numpy()
        n, a, b = int(m.sum()), int(num[m].sum()), int(den[m].sum())
        rows.append(
            dict(
                sample=s,
                modified_before_default=count_metric(a, n),
                primary_defaults=count_metric(b, n),
                ratio=contracts.metric(
                    a / b if b else None,
                    n=n,
                    ci_method="none: a ratio, not a proportion (the numerator is not a subset "
                    "of the denominator)"
                    if b
                    else "none: no primary defaults",
                ),
            )
        )
    return rows


def lin_pred_gini(train, test, binnings, features):
    """Gini on dev_test of a logistic refit on the given WoE features (fairness sensitivity)."""
    res = sc.fit_logit(train["default_12m"], sc.woe_matrix(binnings, train, features))
    x = sc.woe_matrix(binnings, test, features)
    lp = res.params["const"] + x.to_numpy() @ res.params[features].to_numpy()
    y = test["default_12m"].astype(int).to_numpy()
    point, draws = mt.bootstrap_auc_ks(y, [lp])
    return boot_metric(2 * point[0, 0] - 1, 2 * draws[:, 0, 0] - 1, len(y))


def fairness(model, train, test) -> list:
    rows = []
    y = train["default_12m"].astype(int).to_numpy()
    for f in ["number_of_borrowers", "first_time_homebuyer"]:
        b = model["candidates"].get(f) or sc.fit_binning(sc.feature_values(train, f), y, f)
        binnings = {**model["candidates"], f: b}
        in_model = f in model["features"]
        iv = contracts.metric(
            b["iv"], n=len(y), ci_method="none: screening statistic, no interval fixed in the plan"
        )
        if b.get("binning_drop_reason", b["drop_reason"]) is not None and not in_model:
            na = null_metric("the feature's binning failed, so it cannot enter the model")
            rows.append(
                dict(
                    feature=f,
                    in_model=False,
                    iv=iv,
                    gini_dev_test_with=na,
                    gini_dev_test_without=na,
                )
            )
            continue
        with_f = [c for c in sc.CANDIDATES + [f] if c in model["features"] or c == f]
        without = [c for c in model["features"] if c != f]
        rows.append(
            dict(
                feature=f,
                in_model=in_model,
                iv=iv,
                gini_dev_test_with=lin_pred_gini(
                    train, test, binnings, list(dict.fromkeys(with_f))
                ),
                gini_dev_test_without=lin_pred_gini(train, test, binnings, without)
                if without
                else null_metric("no model feature is left without it"),
            )
        )
    return rows


# ---------------------------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------------------------
def s1_rule(model) -> tuple[str, str]:
    """S1: every numeric model feature has monotonic WoE in its expected direction."""
    num_feats = [f for f in model["features"] if f in sc.NUMERIC_TREND]
    bad = [
        f
        for f in num_feats
        if not sc._is_monotonic(
            [b["woe"] for b in model["binnings"][f]["bins"][:-1]], sc.NUMERIC_TREND[f]
        )
    ]
    return (
        "FAIL" if bad else "PASS",
        f"numeric model features {num_feats}; non-monotonic: {bad or 'none'}",
    )


def dry_run_summary(model, ch, dev_scored, train, test, s1, models_out) -> dict:
    """Everything that uses development data only, printed, so the fit can be checked before the
    single out-of-time scoring. Writes only the binning report."""
    models_out.mkdir(parents=True, exist_ok=True)
    binning_report(model, models_out / "binning_report.csv")
    boot, disc, calib = {}, [], []
    for name in DEV:
        frame = dev_scored[dev_scored["sample"] == name]
        risks = {"champion": frame["pd_12m"]}
        if ch:
            risks["challenger"] = frame["challenger_pd"]
        disc += discrimination(frame, risks, name, boot)
    test_scored = dev_scored[dev_scored["sample"] == "dev_test"]
    calib = calibration(test_scored, "pd_12m", "grade", model["grades"], "dev_test", "primary")
    return dict(
        model_id=model["model_id"],
        challenger_id=ch["model_id"] if ch else None,
        challenger_confirm={k: ch[k] for k in ("confirm_passed", "dev_test_auc", "chosen")}
        if ch
        else None,
        features=model["features"],
        grades=[(g["grade"], g["merged_into"]) for g in model["grades"]],
        discrimination=disc,
        s1=s1,
        s4a=calibration_rule(calib),
        fairness=fairness(model, train, test),
    )


def jsonable(o):
    return o.item() if hasattr(o, "item") else str(o)


def write_parquet(df: pd.DataFrame, path: Path, synthetic: bool):
    table = pa.Table.from_pandas(df, preserve_index=False)
    if synthetic:
        table = table.replace_schema_metadata(
            {**(table.schema.metadata or {}), contracts.SYNTHETIC_KEY: b"true"}
        )
    pq.write_table(table, path)


def run(
    base_path,
    dim_loan_path,
    loan_month_path,
    artefacts_dir,
    models_out,
    with_challenger=True,
    reuse_scores=False,
    dry_run=False,
) -> dict:
    base_path, artefacts_dir, models_out = Path(base_path), Path(artefacts_dir), Path(models_out)
    synthetic = contracts.parquet_is_synthetic(base_path)
    real_outputs = {
        (REPO / "artefacts").resolve(),
        (Path(VINTAGE_DATA_ROOT) / "models_out").resolve(),
    }
    if synthetic and {artefacts_dir.resolve(), models_out.resolve()} & real_outputs:
        raise ValueError("synthetic fixtures must never be written to artefacts/ or models_out/")

    base = pd.read_parquet(base_path)
    dev = base[base["sample"].isin(DEV)]
    train, test = dev[dev["sample"] == "dev_train"], dev[dev["sample"] == "dev_test"]

    # 1. Fit and freeze on development data only.
    model = sc.fit(train)
    ch = chal.fit(train, test) if with_challenger else None

    # 2. Development results (no out-of-time data involved).
    dev_scored = sc.score(model, dev)
    if ch:
        dev_scored["challenger_pd"] = chal.predict(ch, dev)
    dev_scored = dev_scored.join(dev[list(DEFS.values())])
    s1 = s1_rule(model)
    if dry_run:
        return dry_run_summary(model, ch, dev_scored, train, test, s1, models_out)

    # 3. The single out-of-time scoring, or its saved result.
    models_out.mkdir(parents=True, exist_ok=True)
    scores_path = models_out / "loan_scores.parquet"
    ch_path = models_out / "challenger_scores.parquet"
    if reuse_scores:
        entries = [e for e in read_oot_log(models_out) if e["model_id"] == model["model_id"]]
        scored = pd.read_parquet(scores_path)
        if len(entries) != 1 or set(scored["model_id"]) != {model["model_id"]}:
            raise RuntimeError("no single logged out-of-time scoring matches this scorecard")
        if ch:
            if entries[0]["challenger_id"] != ch["model_id"]:
                raise RuntimeError("the saved challenger scores come from a different challenger")
            scored = scored.merge(pd.read_parquet(ch_path)[["loan_id", "challenger_pd"]], "left")
        scored.index = base.set_index("loan_id").index.get_indexer(scored["loan_id"])
        scored = scored.sort_index()
    else:
        scored, _ = score_out_of_time(model, ch, base, models_out)
        cols = [
            "loan_id",
            "sample",
            "model_id",
            "score",
            "pd_12m",
            "grade",
            "reason_1",
            "reason_2",
            "reason_3",
        ]
        write_parquet(scored[cols], scores_path, synthetic)
        if ch:
            write_parquet(scored[["loan_id", "sample", "challenger_pd"]], ch_path, synthetic)
    entries = [e for e in read_oot_log(models_out) if e["model_id"] == model["model_id"]]
    scored = scored.join(base[list(DEFS.values()) + ["vintage_year"]])
    (models_out / "scorecard.json").write_text(
        json.dumps({k: v for k, v in model.items()}, indent=1, default=jsonable), encoding="utf-8"
    )

    # 4. Everything that uses out-of-time outcomes comes after the scoring above.
    samples = {
        "dev_train": dev_scored[dev_scored["sample"] == "dev_train"].copy(),
        "dev_test": dev_scored[dev_scored["sample"] == "dev_test"].copy(),
        "oot": scored[scored["sample"] == "oot"].copy(),
        "covid": scored[scored["sample"] == "covid"].copy(),
        "oot_and_covid": scored[scored["sample"].isin(["oot", "covid"])].copy(),
    }
    # Secondary out-of-time windows (pre- and post-COVID), never pass or fail on their own.
    for lo, hi in ((2017, 2019), (2022, 2024)):
        frame = samples["oot"][samples["oot"]["vintage_year"].between(lo, hi)]
        if len(frame):
            samples[f"oot_{lo}_{hi}"] = frame.copy()
    if ch:
        for s in samples.values():
            s["challenger_grade"] = sc.grade_of(s["challenger_pd"].to_numpy(), model["grades"])

    boot, disc, calib, citl = {}, [], [], []
    for name, frame in samples.items():
        risks = {"champion": frame["pd_12m"]}
        if ch:
            risks["challenger"] = frame["challenger_pd"]
        disc += discrimination(frame, risks, name, boot)
        if name != "dev_train":
            for defn in DEFS:
                calib += calibration(frame, "pd_12m", "grade", model["grades"], name, defn)
                citl.append(calibration_in_the_large(frame, "pd_12m", name, defn))

    gini_drop = []
    for defn in DEFS:
        t, o = boot.get(("dev_test", defn, "champion")), boot.get(("oot", defn, "champion"))
        if not (t and o):
            continue
        n = len(samples["oot"])
        rel = (t["gini"] - o["gini"]) / t["gini"]
        gini_drop.append(
            dict(
                definition=defn,
                relative=boot_metric(rel, (t["draws"] - o["draws"]) / t["draws"], n),
                absolute=boot_metric(t["gini"] - o["gini"], t["draws"] - o["draws"], n),
                rag=mt.gini_drop_rag(rel),
            )
        )

    # Stability (S5)
    ref = samples["dev_train"]["score"].to_numpy()
    k, psi_oot, rag_oot = score_psi(ref, samples["oot"]["score"].to_numpy())
    score_psi_rows = [dict(comparison="dev_train_vs_oot", n_bins=k, psi=psi_oot, rag=rag_oot)]
    in_pop = scored[scored["sample"] != "excluded"]
    for year in sorted(in_pop["vintage_year"].unique()):
        yr = in_pop.loc[in_pop["vintage_year"] == year, "score"].to_numpy()
        k_y, m_y, r_y = score_psi(ref, yr)
        score_psi_rows.append(
            dict(comparison=f"dev_train_vs_{int(year)}", n_bins=k_y, psi=m_y, rag=r_y)
        )
    csi_rows = []
    oot_base = base[base["sample"] == "oot"]
    for f in model["features"]:
        b = model["binnings"][f]
        nb = len(b["bins"])
        r = np.bincount(sc.bin_index(b, sc.feature_values(train, f)), minlength=nb)
        c = np.bincount(sc.bin_index(b, sc.feature_values(oot_base, f)), minlength=nb)
        metric, rag = psi_row(r, c, len(oot_base))
        csi_rows.append(dict(feature=f, comparison="dev_train_vs_oot", csi=metric, rag=rag))

    # Challenger (section 5, C1)
    ch_obj = dict(
        status="not_run",
        confirm_passed=None,
        delta_gini_oot=None,
        promotion_recommended=None,
        criteria=[],
        shap_global=[],
    )
    c1 = ("NOT_RUN", "challenger not run")
    if ch:
        oot = samples["oot"]
        y = oot["default_12m"].astype(int).to_numpy()
        point, draws = mt.bootstrap_auc_ks(y, [oot["pd_12m"], oot["challenger_pd"]])
        delta = (2 * point[1, 0] - 1) - (2 * point[0, 0] - 1)
        d_draws = 2 * draws[:, 1, 0] - 2 * draws[:, 0, 0]
        delta_m = boot_metric(delta, d_draws, len(y), "paired_bootstrap_1000")
        delta_lo = mt.percentile_interval(d_draws)[0]
        champ_fails = sum(
            r["result"] == "FAIL"
            for r in calibration(oot, "pd_12m", "grade", model["grades"], "oot", "primary")
        )
        chal_fails = sum(
            r["result"] == "FAIL"
            for r in calibration(
                oot, "challenger_pd", "challenger_grade", model["grades"], "oot", "primary"
            )
        )
        _, ch_psi, _ = score_psi(
            samples["dev_train"]["challenger_pd"].to_numpy(), oot["challenger_pd"].to_numpy()
        )
        oc = samples["oot_and_covid"]
        shap_all = chal.shap_values(ch, base.loc[oc.index])
        shap_dev = chal.shap_values(ch, test)
        criteria = [
            (
                f"paired bootstrap 95% interval of the oot Gini gain has its lower bound above "
                f"+0.02 (gain {fmt(delta_m)}, lower bound {delta_lo:.4f})",
                delta_lo > 0.02,
            ),
            (
                f"oot calibration fails in no more grades than the champion ({chal_fails} vs "
                f"{champ_fails})",
                chal_fails <= champ_fails,
            ),
            (
                f"score PSI dev_train to oot at most 0.25 ({ch_psi['value']:.4f})",
                ch_psi["value"] <= 0.25,
            ),
            (
                "SHAP reason codes for every oot and covid loan, and every monotone "
                "constraint holds",
                bool(np.isfinite(shap_all).all()) and chal.monotone_constraints_hold(ch, train),
            ),
        ]
        promote = ch["confirm_passed"] and all(m for _, m in criteria)
        ch_obj = dict(
            status="run",
            confirm_passed=ch["confirm_passed"],
            delta_gini_oot=delta_m,
            promotion_recommended=bool(promote),
            criteria=[dict(criterion=c, met=bool(m)) for c, m in criteria],
            shap_global=[
                dict(feature=f, mean_abs_shap=float(v))
                for f, v in sorted(
                    zip(sc.CANDIDATES, np.abs(shap_dev).mean(axis=0)), key=lambda t: -t[1]
                )
            ],
        )
        conf = (
            f"confirm step {'passed' if ch['confirm_passed'] else 'FAILED (overfit)'}: "
            f"dev_test AUC {ch['dev_test_auc']:.4f} vs mean fold AUC "
            f"{ch['chosen']['mean_fold_auc']:.4f}"
        )
        c1 = (
            "PASS" if promote else "FAIL",
            conf
            + "; "
            + "; ".join(f"{c}: {'met' if m else 'not met'}" for c, m in criteria)
            + ". The scorecard stays the model used downstream in this release.",
        )

    # Pass rules
    d1a = d1a_rows(base, loan_month_path)
    ratio = d1a[0]["ratio"]["value"]
    d1a_rule = (
        ("PASS" if ratio <= D1A_LIMIT else "AMBER") if ratio is not None else "INSUFFICIENT",
        "modified before or without a primary default "
        f"{d1a[0]['modified_before_default']['value']:.0f}"
        f" / primary defaults {d1a[0]['primary_defaults']['value']:.0f}"
        + (f" = {ratio:.4f}" if ratio is not None else "")
        + (
            "; above 10%, so the modification-trigger sensitivity is required"
            if ratio is not None and ratio > D1A_LIMIT
            else ""
        ),
    )
    prim = next((g for g in gini_drop if g["definition"] == "primary"), None)
    s2 = (
        {"green": "PASS", "amber": "AMBER", "red": "FAIL"}[prim["rag"]] if prim else "INSUFFICIENT",
        (
            f"Gini dev_test {boot[('dev_test', 'primary', 'champion')]['gini']:.4f}, oot "
            f"{boot[('oot', 'primary', 'champion')]['gini']:.4f}, relative drop "
            f"{fmt(prim['relative'])}, {prim['rag']}"
        )
        if prim
        else "Gini not computable",
    )
    s3 = rank_ordering(samples["oot"], model["grades"])
    pick = [r for r in calib if r["definition"] == "primary"]
    s4a = calibration_rule([r for r in pick if r["sample"] == "dev_test"])
    s4b = calibration_rule([r for r in pick if r["sample"] == "oot"])
    s5 = (
        {"green": "PASS", "amber": "AMBER", "red": "FAIL"}[rag_oot],
        f"score PSI dev_train vs oot {fmt(psi_oot)} on {k} bins, {rag_oot}",
    )
    rules = [
        ("D1a", d1a_rule),
        ("S1", s1),
        ("S2", s2),
        ("S3", s3),
        ("S4a", s4a),
        ("S4b", s4b),
        ("S5", s5),
        ("C1", c1),
    ]

    # Samples and exclusions
    dim = pd.read_parquet(
        dim_loan_path, columns=["loan_id", "first_payment_date", "terminal_zero_balance_code"]
    )
    samples_rows = []
    for s in [x for x in contracts.SAMPLES if x in set(base["sample"])]:
        f = base[base["sample"] == s]
        y = f["default_12m"].dropna()
        samples_rows.append(
            dict(
                sample=s,
                vintages=sorted(int(v) for v in f["vintage_year"].unique()),
                n_loans=count_metric(len(f), len(f)),
                default_rate=rate_metric(int(y.sum()), len(y), "wilson_95")
                if len(y)
                else null_metric("excluded loans have no 12-month outcome", len(f)),
            )
        )
    ex = base[base["sample"] == "excluded"].merge(dim, "left", "loan_id")
    ex["before"] = would_be_sample(ex)
    ex["zbc"] = np.where(
        ex["exclusion_reason"] == "indeterminate_exit", ex["terminal_zero_balance_code"], np.nan
    )
    exclusions = [
        dict(
            reason=r,
            sample_before_exclusion=s,
            zero_balance_code=None if pd.isna(z) else int(z),
            n_loans=count_metric(n, n),
        )
        for (r, s, z), n in ex.groupby(["exclusion_reason", "before", "zbc"], dropna=False)
        .size()
        .items()
    ]

    grades_out = [
        {k: g[k] for k in ["grade", "pd_low", "pd_high", "score_min", "score_max", "merged_into"]}
        for g in model["grades"]
    ]
    points_table = []
    for f in model["features"]:
        for b in model["binnings"][f]["bins"]:
            n = b["nonevent"] + b["event"]
            points_table.append(
                dict(
                    feature=f,
                    bin=b["bin"],
                    lower=b["lower"],
                    upper=b["upper"],
                    categories=b["categories"],
                    is_missing_bin=b["is_missing_bin"],
                    woe=float(b["woe"]),
                    points=int(b["points"]),
                    default_rate_dev_train=rate_metric(b["event"], n, "wilson_95")
                    if n
                    else null_metric("no dev_train loans in this bin"),
                )
            )
    features_out = [
        dict(
            feature=f,
            iv=contracts.metric(
                float(c["iv"]),
                n=model["n_dev_train"],
                ci_method="none: screening statistic, no interval fixed in the plan",
            ),
            selected=f in model["features"],
            drop_reason=c["drop_reason"],
            coefficient=model["coefficients"].get(f),
        )
        for f, c in model["candidates"].items()
    ]
    oot_entry = entries[0] if entries else None
    envelope = dict(
        schema_version=contracts.SCHEMA_VERSION,
        synthetic=bool(synthetic),
        generated_at=now(),
        data_cutoff=DATA_CUTOFF,
        code_version=code_version(),
        suppressed_cells=0,
    )
    pd_models = dict(
        schema_version=envelope["schema_version"],
        artefact="pd_models",
        **{k: v for k, v in envelope.items() if k != "schema_version"},
        model_id=model["model_id"],
        samples=samples_rows,
        exclusions=exclusions,
        d1a=d1a,
        scaling=dict(
            base_score=sc.BASE_SCORE,
            base_odds=sc.BASE_ODDS,
            pdo=sc.PDO,
            factor=sc.FACTOR,
            offset=sc.OFFSET,
            intercept=model["intercept"],
            pd_label=sc.PD_LABEL + (" (synthetic fixture)" if synthetic else ""),
        ),
        features=features_out,
        points_table=points_table,
        grades=grades_out,
        discrimination=disc,
        calibration=calib,
        calibration_in_the_large=citl,
        gini_drop=gini_drop,
        fairness_sensitivity=fairness(model, train, test),
        challenger=ch_obj,
        oot_scoring=dict(
            calls=len(entries), scored_at=oot_entry["scored_at"] if oot_entry else None
        ),
        pass_rules=[dict(rule_id=r, result=res, evidence=ev) for r, (res, ev) in rules],
    )
    monitoring = dict(
        schema_version=envelope["schema_version"],
        artefact="monitoring",
        **{k: v for k, v in envelope.items() if k != "schema_version"},
        model_id=model["model_id"],
        thresholds=dict(stable_below=mt.STABLE_BELOW, red_above=mt.RED_ABOVE),
        score_psi=score_psi_rows,
        csi=csi_rows,
    )

    problems = []
    for name, art in (("pd_models", pd_models), ("monitoring", monitoring)):
        art["suppressed_cells"] = contracts.suppress_small_cells(art)
        problems += contracts.check_artefact(name, art)
    problems += contracts.check_model_output("loan_scores", scores_path)
    if problems:
        raise RuntimeError("outputs break the contract:\n" + "\n".join(problems))
    artefacts_dir.mkdir(parents=True, exist_ok=True)
    for name, art in (("pd_models", pd_models), ("monitoring", monitoring)):
        (artefacts_dir / f"{name}.json").write_text(
            json.dumps(art, indent=2, default=jsonable) + "\n", encoding="utf-8"
        )
    binning_report(model, models_out / "binning_report.csv")
    return {"model": model, "challenger": ch, "pd_models": pd_models, "monitoring": monitoring}


def binning_report(model: dict, path: Path):
    """One row per bin of every candidate feature, with its IV and why it left the model."""
    rows = []
    for f, c in model["candidates"].items():
        for b in c["bins"]:
            n = b["nonevent"] + b["event"]
            rows.append(
                dict(
                    feature=f,
                    status=c["status"],
                    iv=c["iv"],
                    iv_above_review_level=c["iv_above_review_level"],
                    selected=f in model["features"],
                    drop_reason=c["drop_reason"],
                    bin=b["bin"],
                    n=n,
                    defaults=b["event"],
                    default_rate=b["event"] / n if n else None,
                    woe_raw=b["woe_raw"],
                    woe_used=b["woe"],
                    missing_woe_substituted=b["woe_substituted"],
                    points=b.get("points"),
                )
            )
    pd.DataFrame(rows).to_csv(path, index=False)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument(
        "--fixtures",
        metavar="OUT_DIR",
        help="run on the synthetic fixtures and write every output under OUT_DIR",
    )
    p.add_argument("--no-challenger", action="store_true")
    p.add_argument(
        "--reuse-scores",
        action="store_true",
        help="rebuild artefacts from the saved out-of-time scoring",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="fit and report on development data only; no out-of-time scoring, no artefacts",
    )
    a = p.parse_args()
    if a.fixtures:
        marts, out = REPO / "tests" / "fixtures" / "marts", Path(a.fixtures)
        artefacts, models_out = out / "artefacts", out / "models_out"
    else:
        marts = Path(VINTAGE_DATA_ROOT) / "marts_out"
        artefacts, models_out = REPO / "artefacts", Path(VINTAGE_DATA_ROOT) / "models_out"
    res = run(
        marts / "fct_scorecard_base.parquet",
        marts / "dim_loan.parquet",
        marts / "fct_loan_month.parquet",
        artefacts,
        models_out,
        with_challenger=not a.no_challenger,
        reuse_scores=a.reuse_scores,
        dry_run=a.dry_run,
    )
    if a.dry_run:
        print(json.dumps(res, indent=1, default=jsonable))
        return
    for r in res["pd_models"]["pass_rules"]:
        print(f"{r['rule_id']:4} {r['result']:12} {r['evidence']}")


if __name__ == "__main__":
    main()
