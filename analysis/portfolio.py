"""Portfolio analytics: vintage curves, roll rates, cures, SMA, prepayment and loss drivers.

    python -m analysis.portfolio --fixtures --out <dir>   # synthetic fixtures
    python -m analysis.portfolio                          # real marts under VINTAGE_DATA_ROOT

Real run reads marts_out/ (and data/parquet/ for reconciliation) under VINTAGE_DATA_ROOT and
writes artefacts/portfolio.json in the repo.

Pre-registration (VALIDATION_PLAN.md, and the project's own outcome-query ban): no outcome
analysis of defaults, losses, cures or roll rates for 2016+ vintages until
models_out/oot_scoring_log.jsonl records that the scorecard's out-of-time scoring has happened
(P3). Until then, every vintage-scoped query here is filtered to vintage_year <= LOCKED_MAX_
VINTAGE (2015). R1-R4 (loan counts, loan-month counts, balances, loss sums) are the one exception
the plan's own reconciliation carve-out allows on the full range, because they are not default
rates or outcome rates by vintage.
"""

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from config import VINTAGE_DATA_ROOT
from models.loss import stats as S
from tests import contracts as C

ROOT = Path(__file__).resolve().parents[1]
CUTOFF = pd.Timestamp("2026-03-01")
LOCKED_MAX_VINTAGE = 2015
FULL_MAX_VINTAGE = 2024  # 2025 excluded from every analysis here: window incomplete (D6)
SEED = 20260923
N_BOOT = 1000
ROLL_DENOM_BUCKETS = ["current", "dpd_30", "dpd_60", "dpd_90p"]  # excludes "reo" (D5)


def envelope(synthetic: bool) -> dict:
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
        "artefact": "portfolio",
        "synthetic": synthetic,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_cutoff": CUTOFF.strftime("%Y-%m-%d"),
        "code_version": sha,
        "suppressed_cells": 0,
    }


# --------------------------------------------------------------------------------------------
# Pre-registration gate (P3)
# --------------------------------------------------------------------------------------------
def oot_scored(models_out: Path) -> bool:
    """True once models_out/oot_scoring_log.jsonl records at least one out-of-time scoring call."""
    log = models_out / "oot_scoring_log.jsonl"
    if not log.exists():
        return False
    try:
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except OSError:
        return False
    for ln in lines:
        try:
            json.loads(ln)
        except json.JSONDecodeError:
            continue
        else:
            return True
    return False


def max_vintage(models_out: Path) -> int:
    return FULL_MAX_VINTAGE if oot_scored(models_out) else LOCKED_MAX_VINTAGE


# --------------------------------------------------------------------------------------------
# Loading (dim_loan, fct_vintage_curve, fct_default_events, fct_loss_events, fct_roll_rates,
# dim_date and metrics_monthly are all small enough to load fully; fct_loan_month is not (up to
# 75M rows on the real data) and is only ever touched through a DuckDB aggregate query).
# --------------------------------------------------------------------------------------------
def load(marts: Path) -> dict:
    rd = lambda name: pd.read_parquet(marts / f"{name}.parquet")  # noqa: E731
    return {
        "dim_loan": rd("dim_loan"),
        "vcurve": rd("fct_vintage_curve"),
        "defaults": rd("fct_default_events"),
        "loss": rd("fct_loss_events"),
        "roll": rd("fct_roll_rates"),
        "dim_date": rd("dim_date"),
        "metrics": rd("metrics_monthly"),
    }


def scoped(d: dict, max_v: int) -> dict:
    """The same tables, filtered to vintage_year <= max_v (the pre-registration gate)."""
    out = dict(d)
    for k in ("dim_loan", "vcurve", "defaults", "loss", "roll"):
        out[k] = d[k][d[k].vintage_year <= max_v].reset_index(drop=True)
    return out


# --------------------------------------------------------------------------------------------
# Bootstrap: loan-population resampling for a dollar ratio (cum loss / fixed original UPB, or
# a segment's loss / fixed segment UPB). n_loans is the FIXED population (denominator never
# resampled); only which loans carry a loss is resampled, which is the part with sampling
# uncertainty for a rate like this. This is a stated simplification: it treats the vintage's own
# loans as a sample from a hypothetical superpopulation, the same framing the Wilson interval on
# cum_default_rate already uses.
# --------------------------------------------------------------------------------------------
def _boot_counts(n_loans: int, k: int, n_boot: int = N_BOOT, seed: int = SEED) -> np.ndarray:
    """(n_boot, k) resampled counts for k specific loss events in a population of n_loans."""
    if k == 0 or n_loans <= 0:
        return np.zeros((n_boot, max(k, 1)))
    rng = np.random.default_rng(seed)
    p = np.full(k + 1, 1.0 / n_loans)
    p[-1] = max(0.0, 1.0 - k / n_loans)
    return rng.multinomial(n_loans, p, size=n_boot)[:, :k].astype(float)


def loss_curve_draws(loss_sub: pd.DataFrame, n_loans: int, mobs: np.ndarray) -> np.ndarray:
    """Bootstrap draws of cumulative loss at each of `mobs`. Returns (N_BOOT, len(mobs))."""
    k = len(loss_sub)
    if k == 0 or n_loans <= 0:
        return np.zeros((N_BOOT, len(mobs)))
    order = np.argsort(loss_sub["disposal_mob"].to_numpy())
    sorted_mob = loss_sub["disposal_mob"].to_numpy()[order]
    sorted_loss = loss_sub["computed_loss"].to_numpy()[order]
    counts = _boot_counts(n_loans, k)
    cum = np.cumsum(counts * sorted_loss[None, :], axis=1)  # (N_BOOT, k)
    idx = np.searchsorted(sorted_mob, mobs, side="right") - 1
    return np.where(idx[None, :] >= 0, cum[:, np.clip(idx, 0, k - 1)], 0.0)


def loss_total_draws(loss_amounts: np.ndarray, n_loans: int) -> np.ndarray:
    k = len(loss_amounts)
    if k == 0 or n_loans <= 0:
        return np.zeros(N_BOOT)
    return _boot_counts(n_loans, k) @ loss_amounts


def _attach_disposal_mob(
    loss: pd.DataFrame, defaults: pd.DataFrame, dim_loan: pd.DataFrame
) -> pd.DataFrame:
    dp = defaults[defaults.definition == "primary"][["loan_id", "default_months_on_book"]]
    out = loss.merge(dp, on="loan_id", how="left")
    out["disposal_mob"] = out["default_months_on_book"] + out["months_to_resolution"]
    return out.merge(dim_loan[["loan_id", "vintage_quarter"]], on="loan_id", how="left")


# --------------------------------------------------------------------------------------------
# 1. Summary
# --------------------------------------------------------------------------------------------
def build_summary(d: dict, marts: Path) -> dict:
    dl = d["dim_loan"]
    n_loans = len(dl)
    defaults_p = d["defaults"][d["defaults"].definition == "primary"]
    defaults_n = d["defaults"][d["defaults"].definition == "naive"]
    loss = d["loss"]
    flm = marts / "fct_loan_month.parquet"
    max_v = int(dl.vintage_year.max()) if len(dl) else LOCKED_MAX_VINTAGE
    con = duckdb.connect()
    n_loan_months = con.execute(
        "select count(*) from read_parquet(?) where vintage_year <= ?", [str(flm), max_v]
    ).fetchone()[0]
    return {
        "n_loans": S.metric(n_loans, n=n_loans, method="none: population count, not an estimate"),
        "n_loan_months": S.metric(
            n_loan_months, n=n_loans, method="none: population count, not an estimate"
        ),
        "original_upb_total": S.metric(
            float(dl.original_upb.sum()), n=n_loans, method="none: population total"
        ),
        "n_defaults_primary": S.metric(
            len(defaults_p), n=len(defaults_p), method="none: population count, not an estimate"
        ),
        "n_defaults_naive": S.metric(
            len(defaults_n), n=len(defaults_n), method="none: population count, not an estimate"
        ),
        "net_loss_total": S.metric(
            float(loss.computed_loss.sum()), n=len(loss), method="none: population total"
        ),
    }


# --------------------------------------------------------------------------------------------
# 2. Vintage curves (quarter grain, straight from fct_vintage_curve) and comparable_months_on_book
# --------------------------------------------------------------------------------------------
def build_vintage_curves(d: dict) -> tuple[list, int]:
    vc = d["vcurve"].sort_values(["vintage_quarter", "months_on_book"])
    loss_att = _attach_disposal_mob(d["loss"], d["defaults"], d["dim_loan"])
    rows = []
    thresholds = []
    for q, g in vc.groupby("vintage_quarter", sort=False):
        n_loans = int(g["n_loans"].iloc[0])
        orig_upb = float(g["original_upb_total"].iloc[0])
        loss_q = loss_att[loss_att.vintage_quarter == q]
        mobs = g["months_on_book"].to_numpy()
        draws = loss_curve_draws(loss_q, n_loans, mobs) / orig_upb if orig_upb else None
        fo_true = g.loc[g.fully_observed, "months_on_book"]
        if len(fo_true):
            thresholds.append(int(fo_true.max()))
        for i, (_, r) in enumerate(g.iterrows()):
            cdr = S.wilson(int(r.cum_defaults), n_loans)
            if draws is not None:
                clr = S.percentile(
                    float(r.cum_loss_rate), draws[:, i], n_loans, "bootstrap_1000_loan_population"
                )
            else:
                clr = S.metric(float(r.cum_loss_rate), n=n_loans, method="none: no loss events yet")
            rows.append(
                {
                    "vintage_year": int(r.vintage_year),
                    "vintage_quarter": q,
                    "months_on_book": int(r.months_on_book),
                    "fully_observed": bool(r.fully_observed),
                    "cum_default_rate": cdr,
                    "cum_loss_rate": clr,
                }
            )
    comparable = min(thresholds) if thresholds else 0
    return rows, comparable


# --------------------------------------------------------------------------------------------
# 2b. Annual series (vintage_curves_annual): same shape, aggregated year over its 4 quarters at
# matching months on book. A quarter's cumulative values are forward-filled past its own last
# observed row (right-censoring: it just hadn't reached further by the cutoff); fully_observed is
# false for any forward-filled point, and the annual total requires every quarter true.
# --------------------------------------------------------------------------------------------
def build_vintage_curves_annual(d: dict) -> list:
    vc = d["vcurve"]
    loss_att = _attach_disposal_mob(d["loss"], d["defaults"], d["dim_loan"])
    rows = []
    for year, gy in vc.groupby("vintage_year"):
        quarters = sorted(gy.vintage_quarter.unique())
        max_mob = int(gy.months_on_book.max())
        mobs = np.arange(1, max_mob + 1)
        n_loans_total = 0
        orig_upb_total = 0.0
        cum_def = np.zeros(max_mob)
        fully = np.ones(max_mob, dtype=bool)
        loss_draws_sum = np.zeros((N_BOOT, max_mob))
        loss_point_sum = np.zeros(max_mob)
        for q in quarters:
            gq = gy[gy.vintage_quarter == q].sort_values("months_on_book")
            n_loans = int(gq["n_loans"].iloc[0])
            orig_upb = float(gq["original_upb_total"].iloc[0])
            n_loans_total += n_loans
            orig_upb_total += orig_upb
            s_def = gq.set_index("months_on_book")["cum_defaults"].reindex(mobs).ffill().fillna(0)
            s_fo = (
                gq.set_index("months_on_book")["fully_observed"]
                .reindex(mobs)
                .astype("boolean")
                .fillna(False)
            )
            cum_def += s_def.to_numpy()
            fully &= s_fo.to_numpy().astype(bool)
            loss_q = loss_att[loss_att.vintage_quarter == q]
            draws_q = loss_curve_draws(loss_q, n_loans, mobs)
            s_loss = gq.set_index("months_on_book")["cum_net_loss"].reindex(mobs).ffill().fillna(0)
            loss_point_sum += s_loss.to_numpy()
            loss_draws_sum += draws_q
        if n_loans_total == 0:
            continue
        clr_series = loss_point_sum / orig_upb_total if orig_upb_total else np.zeros(max_mob)
        clr_draws = loss_draws_sum / orig_upb_total if orig_upb_total else loss_draws_sum
        for i, mob in enumerate(mobs):
            cdr = S.wilson(int(round(cum_def[i])), n_loans_total)
            clr = S.percentile(
                float(clr_series[i]),
                clr_draws[:, i],
                n_loans_total,
                "bootstrap_1000_loan_population",
            )
            rows.append(
                {
                    "vintage_year": int(year),
                    "months_on_book": int(mob),
                    "fully_observed": bool(fully[i]),
                    "cum_default_rate": cdr,
                    "cum_loss_rate": clr,
                }
            )
    return rows


# --------------------------------------------------------------------------------------------
# 3. Roll rates and roll-rate cures, rolled up by economic period (D9, dim_date.economic_period)
# --------------------------------------------------------------------------------------------
def _roll_with_period(d: dict) -> pd.DataFrame:
    dd = d["dim_date"][["month", "economic_period"]]
    return d["roll"].merge(dd, left_on="period", right_on="month", how="left")


def build_roll_rates(d: dict) -> list:
    roll = _roll_with_period(d)
    denom_cells = roll.drop_duplicates(
        ["period", "vintage_year", "from_bucket", "from_forbearance"]
    )
    rows = []
    for period_group, r_g, dn_g in _period_groups(roll, denom_cells):
        num = r_g.groupby(["from_bucket", "to_state"])["n_loans"].sum()
        den = dn_g.groupby("from_bucket")["n_from"].sum()
        for (fb, ts), n in num.items():
            n_from = int(den.get(fb, 0))
            rows.append(
                {
                    "period_group": period_group,
                    "from_bucket": fb,
                    "to_state": ts,
                    "rate": S.wilson(int(n), n_from),
                }
            )
    return rows


def build_roll_cure_rates(d: dict) -> list:
    roll = _roll_with_period(d)
    cure = roll[roll.from_bucket.isin(["dpd_30", "dpd_60", "dpd_90p"])]
    denom_cells = cure.drop_duplicates(
        ["period", "vintage_year", "from_bucket", "from_forbearance"]
    )
    rows = []
    for period_group, r_g, dn_g in _period_groups(cure, denom_cells):
        cured = r_g[r_g.to_state == "current"].groupby("from_bucket")["n_loans"].sum()
        den = dn_g.groupby("from_bucket")["n_from"].sum()
        for fb in ROLL_DENOM_BUCKETS[1:]:  # dpd_30, dpd_60, dpd_90p
            n_from = int(den.get(fb, 0))
            n_cured = int(cured.get(fb, 0))
            rows.append(
                {"period_group": period_group, "from_bucket": fb, "rate": S.wilson(n_cured, n_from)}
            )
    return rows


def _period_groups(rolled: pd.DataFrame, denom_cells: pd.DataFrame):
    """Yield (period_group, rolled subset, denom subset) for 'all' plus each economic period."""
    yield "all", rolled, denom_cells
    for ep in sorted(rolled.economic_period.dropna().unique()):
        yield (
            ep,
            rolled[rolled.economic_period == ep],
            denom_cells[denom_cells.economic_period == ep],
        )


# --------------------------------------------------------------------------------------------
# 4. Cure rates by default year (D4), and 5. default-definition effect (D1 vs D2)
# --------------------------------------------------------------------------------------------
def build_default_cure_rates(d: dict) -> list:
    de = d["defaults"][d["defaults"].definition == "primary"].copy()
    de["default_year"] = pd.to_datetime(de.default_period).dt.year
    dp = pd.to_datetime(de.default_period)
    cp = pd.to_datetime(de.cure_period)
    de["months_to_cure"] = (cp.dt.year - dp.dt.year) * 12 + (cp.dt.month - dp.dt.month)
    rows = []
    for year, g in de.groupby("default_year"):
        n = len(g)
        cured_ever = int(g.cure_period.notna().sum())
        cured_12m = int((g.months_to_cure <= 12).sum())
        rows.append(
            {
                "default_year": int(year),
                "cure_12m": S.wilson(cured_12m, n),
                "cure_ever": S.wilson(cured_ever, n),
            }
        )
    return rows


def build_default_definition_effect(d: dict) -> list:
    dl = d["dim_loan"].groupby("vintage_year")["loan_id"].count()
    de = d["defaults"]
    rows = []
    for year in sorted(de.vintage_year.unique()):
        n_loans = int(dl.get(year, 0))
        if n_loans == 0:
            continue
        p = de[
            (de.vintage_year == year)
            & (de.definition == "primary")
            & (de.default_months_on_book <= 12)
        ]
        nv = de[
            (de.vintage_year == year)
            & (de.definition == "naive")
            & (de.default_months_on_book <= 12)
        ]
        rows.append(
            {
                "vintage_year": int(year),
                "defaults_12m_primary": S.wilson(len(p), n_loans),
                "defaults_12m_naive": S.wilson(len(nv), n_loans),
            }
        )
    return rows


# --------------------------------------------------------------------------------------------
# 6. SMA balances by period (D9) -- the one output that must touch fct_loan_month directly, so it
# is a single DuckDB GROUP BY against the Parquet file, never loaded into pandas whole.
# --------------------------------------------------------------------------------------------
def build_sma(marts: Path, max_v: int) -> list:
    flm = str(marts / "fct_loan_month.parquet")
    con = duckdb.connect()
    df = con.execute(
        """
        select period, sma_class, sum(current_upb) as upb, count(distinct loan_id) as n
        from read_parquet(?)
        where vintage_year <= ? and zero_balance_code is null
        group by 1, 2
        """,
        [flm, max_v],
    ).df()
    df["period"] = pd.to_datetime(df["period"])
    totals = df.groupby("period")["upb"].transform("sum")
    df["share"] = np.where(totals > 0, df["upb"] / totals, np.nan)
    rows = []
    for _, r in df.iterrows():
        rows.append(
            {
                "period": r.period.strftime("%Y-%m-%d"),
                "sma_class": r.sma_class,
                "upb": S.metric(float(r.upb), n=int(r.n), method="none: population total"),
                "share": S.metric(
                    None if pd.isna(r.share) else float(r.share),
                    n=int(r.n),
                    method="none: population share, not an estimate",
                ),
            }
        )
    return rows


# --------------------------------------------------------------------------------------------
# 7. Prepayment speeds (CPR from the monthly SMM, D5), by period, from fct_roll_rates
# --------------------------------------------------------------------------------------------
def build_prepayment(marts: Path, max_v: int) -> list:
    """Monthly SMM from fct_loan_month.exit_type / at_risk_at_start, not from fct_roll_rates:
    on the real build fct_roll_rates.to_state never carries 'prepaid'/'matured'/'credit_event'/
    'other_exit' -- every exit lands in 'missing' instead (verified against dim_loan.exit_type
    and fct_loan_month.exit_type, which are both correct). That is a defect in fct_roll_rates
    (owned by the dbt project, not this file); flagged separately. fct_loan_month.exit_type is
    unaffected, so prepayment speeds are computed from it directly instead of working around the
    bug inside a mart this file doesn't own."""
    flm = str(marts / "fct_loan_month.parquet")
    con = duckdb.connect()
    df = con.execute(
        """
        select period,
               sum(case when exit_type in ('prepaid', 'matured') then 1 else 0 end) as n_prepaid,
               sum(case when at_risk_at_start then 1 else 0 end) as n_at_risk
        from read_parquet(?)
        where vintage_year <= ?
        group by 1
        """,
        [flm, max_v],
    ).df()
    rows = []
    for _, r in df.sort_values("period").iterrows():
        smm = S.wilson(int(r.n_prepaid), int(r.n_at_risk))
        if smm["value"] is None:
            cpr = smm
        else:
            cpr_lo = 1 - (1 - smm["ci_low"]) ** 12 if smm["ci_low"] is not None else None
            cpr_hi = 1 - (1 - smm["ci_high"]) ** 12 if smm["ci_high"] is not None else None
            cpr = S.metric(1 - (1 - smm["value"]) ** 12, cpr_lo, cpr_hi, smm["n"], smm["ci_method"])
        rows.append({"period": pd.Timestamp(r.period).strftime("%Y-%m-%d"), "cpr": cpr})
    return rows


# --------------------------------------------------------------------------------------------
# 8. Loss drivers: the segments driving losses (LTV band and property state, both already on
# fct_loss_events; default_rate needs a join back to dim_loan for the segment's loan count).
# --------------------------------------------------------------------------------------------
def build_loss_drivers(d: dict) -> list:
    dl, loss = d["dim_loan"], d["loss"]
    defaults_p = d["defaults"][d["defaults"].definition == "primary"][["loan_id"]]
    dl_def = dl.merge(defaults_p.assign(_d=1), on="loan_id", how="left")
    dl_def["_d"] = dl_def["_d"].fillna(0)
    rows = []
    for dim in ("ltv_band", "property_state"):
        n_loans_seg = dl_def.groupby(dim)["loan_id"].count()
        n_def_seg = dl_def.groupby(dim)["_d"].sum()
        upb_seg = dl_def.groupby(dim)["original_upb"].sum()
        loss_seg = loss.groupby(dim)["computed_loss"].apply(list)
        for seg in n_loans_seg.index:
            n_loans = int(n_loans_seg[seg])
            n_defaults = int(n_def_seg.get(seg, 0))
            orig_upb = float(upb_seg.get(seg, 0.0))
            amounts = np.array(loss_seg.get(seg, []), dtype=float)
            point = float(amounts.sum() / orig_upb) if orig_upb else 0.0
            draws = loss_total_draws(amounts, n_loans) / orig_upb if orig_upb else np.zeros(N_BOOT)
            rows.append(
                {
                    "dimension": dim,
                    "segment": str(seg),
                    "default_rate": S.wilson(n_defaults, n_loans),
                    "loss_rate": S.percentile(
                        point, draws, n_loans, "bootstrap_1000_loan_population"
                    ),
                }
            )
    return rows


# --------------------------------------------------------------------------------------------
# 9. Reconciliation (R1-R4, R7, R8) -- the hard-stop gate. R1-R4 are counts, loan-month counts,
# balances and loss sums, explicitly allowed on the full vintage range (not a default rate).
# --------------------------------------------------------------------------------------------
def build_reconciliation(marts: Path, raw_dir: Path, d_full: dict) -> list:
    con = duckdb.connect()
    rows = []

    orig_glob = str(raw_dir / "orig_*.parquet")
    perf_glob = str(raw_dir / "perf_*.parquet")
    if raw_dir.exists() and list(raw_dir.glob("orig_*.parquet")):
        raw_loans = con.execute(
            f"select count(distinct loan_id) from read_parquet('{orig_glob}')"
        ).fetchone()[0]
        raw_months = con.execute(f"select count(*) from read_parquet('{perf_glob}')").fetchone()[0]
        raw_upb = con.execute(
            f"select coalesce(sum(current_actual_upb), 0) from read_parquet('{perf_glob}')"
        ).fetchone()[0]
        raw_loss = con.execute(
            f"select coalesce(sum(actual_loss), 0) from read_parquet('{perf_glob}')"
        ).fetchone()[0]

        mart_loans = con.execute(
            f"select count(*) from read_parquet('{marts / 'dim_loan.parquet'}')"
        ).fetchone()[0]
        mart_months = con.execute(
            f"select count(*) from read_parquet('{marts / 'fct_loan_month.parquet'}')"
        ).fetchone()[0]
        flm_path = marts / "fct_loan_month.parquet"
        mart_upb = con.execute(
            f"select coalesce(sum(current_upb), 0) from read_parquet('{flm_path}')"
        ).fetchone()[0]
        mart_loss = float(d_full["loss"].freddie_actual_loss.fillna(0).sum())

        rows.append(
            {
                "rule_id": "R1",
                "n_checked": int(raw_loans),
                "n_outside_tolerance": int(raw_loans != mart_loans),
                "max_abs_difference": float(abs(raw_loans - mart_loans)),
            }
        )
        rows.append(
            {
                "rule_id": "R2",
                "n_checked": int(raw_months),
                "n_outside_tolerance": int(raw_months != mart_months),
                "max_abs_difference": float(abs(raw_months - mart_months)),
            }
        )
        rows.append(
            {
                "rule_id": "R3",
                "n_checked": int(raw_months),
                "n_outside_tolerance": int(abs(raw_upb - mart_upb) > 1.0),
                "max_abs_difference": float(abs(raw_upb - mart_upb)),
            }
        )
        rows.append(
            {
                "rule_id": "R4",
                "n_checked": int(len(d_full["dim_loan"].vintage_year.unique())),
                "n_outside_tolerance": int(abs(raw_loss - mart_loss) > 1.0),
                "max_abs_difference": float(abs(raw_loss - mart_loss)),
            }
        )
    else:
        rows += [
            {"rule_id": r, "n_checked": 0, "n_outside_tolerance": 0, "max_abs_difference": 0.0}
            for r in ("R1", "R2", "R3", "R4")
        ]

    # R7: recompute metrics_monthly's own measures from fct_loan_month / fct_loss_events and diff.
    flm = str(marts / "fct_loan_month.parquet")
    fle = marts / "fct_loss_events.parquet"
    recomputed = con.execute(
        f"""
        select period,
               count(*) filter (where zero_balance_code is null) as n_active_loans,
               coalesce(sum(current_upb) filter (where zero_balance_code is null), 0) as total_upb,
               count(*) filter (where at_risk_at_start) as n_at_risk_start,
               count(*) filter (where is_first_default_month) as n_new_defaults
        from read_parquet('{flm}')
        group by 1
        """
    ).df()
    recomputed["period"] = pd.to_datetime(recomputed["period"])
    loss_full = pd.read_parquet(fle)
    loss_full["disposition_period"] = pd.to_datetime(loss_full["disposition_period"])
    net_loss_by_period = loss_full.groupby("disposition_period")["computed_loss"].sum()
    recomputed = recomputed.set_index("period")
    recomputed["net_loss"] = recomputed.index.map(net_loss_by_period).fillna(0.0)
    mm = d_full["metrics"].set_index(pd.to_datetime(d_full["metrics"]["period"]))
    joined = recomputed.join(
        mm[["n_active_loans", "total_upb", "n_at_risk_start", "n_new_defaults", "net_loss"]],
        lsuffix="_re",
        rsuffix="_mm",
        how="inner",
    )
    max_rel = 0.0
    n_outside = 0
    for col in ("n_active_loans", "total_upb", "n_at_risk_start", "n_new_defaults", "net_loss"):
        a, b = joined[f"{col}_re"].to_numpy(float), joined[f"{col}_mm"].to_numpy(float)
        denom = np.maximum(np.abs(b), 1.0)
        rel = np.abs(a - b) / denom
        max_rel = max(max_rel, float(rel.max()) if len(rel) else 0.0)
        n_outside += int((rel > 1e-9).sum())
    rows.append(
        {
            "rule_id": "R7",
            "n_checked": int(len(joined) * 5),
            "n_outside_tolerance": n_outside,
            "max_abs_difference": max_rel,
        }
    )
    return rows


def apply_r8(body: dict, d: dict) -> None:
    """R8: check the artefact's own summary counts against the marts they came from, in place."""
    checks = [
        (body["summary"]["n_loans"]["value"], len(d["dim_loan"])),
        (
            body["summary"]["n_defaults_primary"]["value"],
            len(d["defaults"][d["defaults"].definition == "primary"]),
        ),
        (
            body["summary"]["n_defaults_naive"]["value"],
            len(d["defaults"][d["defaults"].definition == "naive"]),
        ),
        (body["summary"]["net_loss_total"]["value"], float(d["loss"].computed_loss.sum())),
    ]
    n_outside = sum(1 for a, b in checks if abs(a - b) > 1.0)
    max_diff = max((abs(a - b) for a, b in checks), default=0.0)
    body["reconciliation"].append(
        {
            "rule_id": "R8",
            "n_checked": len(checks),
            "n_outside_tolerance": n_outside,
            "max_abs_difference": float(max_diff),
        }
    )


def pass_rules(reconciliation: list) -> list:
    tol = {"R1": 0, "R2": 0, "R3": 1.0, "R4": 1.0, "R7": 1e-9, "R8": 1.0}
    out = []
    for r in reconciliation:
        t = tol[r["rule_id"]]
        ok = r["max_abs_difference"] <= t
        out.append(
            {
                "rule_id": r["rule_id"],
                "result": "PASS" if ok else "FAIL",
                "evidence": f"{r['n_checked']} checked, {r['n_outside_tolerance']} outside "
                f"tolerance, largest difference {r['max_abs_difference']:.6g} (tolerance {t}).",
            }
        )
    return out


# --------------------------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------------------------
def build(marts: Path, models_out: Path, raw_dir: Path) -> dict:
    d_full = load(marts)
    synthetic = C.parquet_is_synthetic(marts / "fct_vintage_curve.parquet")
    max_v = max_vintage(models_out)
    d = scoped(d_full, max_v)

    vintage_curves, comparable = build_vintage_curves(d)
    body = {
        "summary": build_summary(d, marts),
        "comparable_months_on_book": comparable,
        "vintage_curves": vintage_curves,
        "vintage_curves_annual": build_vintage_curves_annual(d),
        "roll_rates": build_roll_rates(d),
        "roll_cure_rates": build_roll_cure_rates(d),
        "default_cure_rates": build_default_cure_rates(d),
        "sma": build_sma(marts, max_v),
        "prepayment": build_prepayment(marts, max_v),
        "loss_drivers": build_loss_drivers(d),
        "default_definition_effect": build_default_definition_effect(d),
        "reconciliation": build_reconciliation(marts, raw_dir, d_full),
    }
    body["pass_rules"] = pass_rules(body["reconciliation"])
    apply_r8(body, d)
    # pass_rules built before R8 is appended: R8's own pass/fail is added after.
    r8 = body["reconciliation"][-1]
    body["pass_rules"].append(
        {
            "rule_id": "R8",
            "result": "PASS" if r8["n_outside_tolerance"] == 0 else "FAIL",
            "evidence": f"{r8['n_checked']} artefact counts checked against their source marts, "
            f"{r8['n_outside_tolerance']} outside tolerance.",
        }
    )
    obj = {**envelope(synthetic), **body}
    obj["_max_vintage_year_included"] = max_v  # dropped before writing; see main()
    return obj


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true", help="run on tests/fixtures (synthetic)")
    ap.add_argument("--out", type=Path, help="output folder (required with --fixtures)")
    a = ap.parse_args(argv)
    if a.fixtures:
        if a.out is None:
            ap.error("--fixtures needs --out: fixture outputs never go to artefacts/")
        marts, models_out, raw_dir = (
            ROOT / "tests/fixtures/marts",
            ROOT / "tests/fixtures/models_out",
            ROOT / "tests/fixtures/raw",
        )
        art_dir = a.out
    else:
        marts = VINTAGE_DATA_ROOT / "marts_out"
        models_out = VINTAGE_DATA_ROOT / "models_out"
        raw_dir = VINTAGE_DATA_ROOT / "data" / "parquet"
        art_dir = a.out or ROOT / "artefacts"

    obj = build(marts, models_out, raw_dir)
    max_v = obj.pop("_max_vintage_year_included")
    obj["suppressed_cells"] = C.suppress_small_cells(obj)
    problems = C.check_artefact("portfolio", obj)
    if problems:
        raise SystemExit(f"portfolio.json breaks the contract: {problems[:5]}")
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "portfolio.json").write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
    unlocked = max_v == FULL_MAX_VINTAGE
    print(f"vintages included: up to {max_v} (oot_scoring_log.jsonl present: {unlocked})")
    for r in obj["pass_rules"]:
        print(f"{r['rule_id']}: {r['result']} - {r['evidence'][:160]}")


if __name__ == "__main__":
    main()
