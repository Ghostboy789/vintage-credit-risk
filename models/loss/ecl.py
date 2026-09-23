"""IFRS 9 / Ind AS 109 staging, ECL, backtest and ECL intervals (VALIDATION_PLAN E1 to E6, L3).

Timing conventions (stated in docs/LOSS_AND_ECL.md): projection month m = 1, 2, ... after the
reporting date; a default in month m has exposure equal to the contractual balance at the start
of month m (after m - 1 scheduled payments) and is discounted by (1 + note rate / 1200) ^ -m.
"""

import numpy as np
import pandas as pd
import scipy.sparse as sp
from scipy import stats

from . import lifetime as LT
from . import stats as S
from .macro import WEIGHTS

RATIO, ABSOLUTE = 2.0, 0.002
STAGES = [1, 2, 3]
IN_SAMPLE_END = pd.Timestamp("2016-12-01")
BACKTEST_DATES = [pd.Timestamp(f"{y}-12-01") for y in range(2016, 2025)]
COVID_DATES = {pd.Timestamp("2019-12-01"), pd.Timestamp("2020-12-01")}
RHO = 0.15


def month_int(ts) -> np.ndarray:
    ts = pd.DatetimeIndex(pd.to_datetime(np.atleast_1d(ts)))
    return np.asarray(ts.year * 12 + ts.month - 1)


# --- exposure, discounting and the single-loan ECL ------------------------------------------
def weights(upb, nib, rate_pct, note_rate_pct, rem, horizon, months):
    """EAD(m) x discount factor(m) for m = 1..months, zero beyond each row's horizon (D7, E2).

    The interest-bearing balance amortises at the current rate over the remaining term; the
    non-interest-bearing (deferred) balance stays until maturity."""
    upb, rem = np.asarray(upb, float), np.maximum(np.asarray(rem, float), 1)
    nib = np.minimum(np.nan_to_num(np.asarray(nib, float)), upb)
    ib = upb - nib
    r = np.asarray(rate_pct, float)[:, None] / 1200
    k = np.arange(months)[None, :]  # payments made before month k + 1
    n = rem[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        grow_n, grow_k = (1 + r) ** n, (1 + r) ** k
        bal = np.where(
            r > 0, ib[:, None] * (grow_n - grow_k) / (grow_n - 1), ib[:, None] * (1 - k / n)
        )
    ead = np.where(k < n, bal + nib[:, None], 0.0)
    df = (1 + np.asarray(note_rate_pct, float)[:, None] / 1200) ** -(k + 1)
    return ead * df * (k < np.asarray(horizon)[:, None])


def loan_ecl(stage, pd12, hd, hp, lgd, upb, nib, rate_pct, note_rate_pct, rem):
    """ECL of one loan from its hazards (hd, hp over the remaining term), used by E4a."""
    if stage == 3:
        return lgd * upb
    horizon = min(12, rem) if stage == 1 else rem
    w = weights([upb], [nib], [rate_pct], [note_rate_pct], [rem], [horizon], len(hd))[0]
    md, _, _ = LT.paths(np.array([pd12]), np.asarray(hd)[None, :], np.asarray(hp)[None, :])
    return float(lgd * md[0] @ w)


# --- the engine --------------------------------------------------------------------------------
class Engine:
    """Stages and ECL at each reporting date, with the point estimate at draw 0 and parameter
    draws 1..n (L1 and L2 coefficients from their normal sampling distributions, LTV-band LGD
    means from their bootstrap). The portfolio and its stages are held fixed across draws."""

    def __init__(self, l1, l2, lgd, macro=None, n_draws=1000, seed=S.SEED):
        self.l1, self.l2, self.lgd, self.macro = l1, l2, lgd, macro
        self.scen = list(WEIGHTS) if macro else ["final"]
        self.w = np.array([WEIGHTS[s] for s in self.scen]) if macro else np.ones(1)
        self.p1 = [l1.model.beta, *l1.model.draws(n_draws, seed)]
        self.p2 = [l2.model.beta, *l2.model.draws(n_draws, seed + 1)]
        self.segs = [*lgd.labels, "overall", "g2"]
        self.p3 = [np.array([lgd.value.get(s, 1.0) for s in self.segs])]
        self.p3 += [
            np.array([lgd.draws[s][d] if s in lgd.draws else 1.0 for s in self.segs])
            for d in range(n_draws)
        ]
        self.n_draws = n_draws
        self.c1 = [l1.coefs(b) for b in self.p1]
        self.c2 = [l2.coefs(b) for b in self.p2]

    # scenario covariates at a reporting date
    def xpath(self, month, s, months):
        return self.macro.x_paths(month, self.scen[s], months) if self.macro else None

    def xbar(self, month, s):
        return float(self.xpath(month, s, 12).mean()) if self.macro else None

    def stage(self, rows: pd.DataFrame, month: int) -> pd.DataFrame:
        """E1: stage = max(dbt stage floor, PD-deterioration flag); adds pd12, pd12_ref."""
        f = LT.l2_frame(rows)
        pd12 = sum(w * self.l2.pd12(f, self.xbar(month, s)) for s, w in enumerate(self.w))
        ref_x = rows["x_orig"].to_numpy() if self.macro else None
        ref = self.l2.pd12(f.assign(behaviour_state="clean", modified="N"), ref_x)
        sicr = (pd12 >= RATIO * ref) & (pd12 - ref >= ABSOLUTE)
        out = rows.assign(pd12=pd12, pd12_ref=ref, sicr=sicr)
        out["stage"] = np.where(
            rows["in_default"], 3, np.maximum(rows["stage_floor"], np.where(sicr, 2, 1))
        )
        return out

    def date(self, rows: pd.DataFrame, month: int):
        """ECL at one reporting date. rows: that date's stage-input rows, already staged.
        Returns (point, draws, row_extra): point/draws hold, per scenario, the ECL by
        (grade, stage) group and for cured loans."""
        rows = rows.reset_index(drop=True)
        seg = rows["lgd_seg"].map({s: i for i, s in enumerate(self.segs)}).to_numpy()
        grade_i = rows["grade"].map({g: i for i, g in enumerate(LT.GRADES)}).to_numpy()
        group = grade_i * 3 + rows["stage"].to_numpy() - 1
        cured = (rows["defaulted_before"] & ~rows["in_default"]).to_numpy()

        nd = rows["stage"].to_numpy() < 3
        r = rows[nd]
        rem = np.maximum(r["remaining_term"].to_numpy(), 1)
        horizon = np.where(r["stage"].to_numpy() == 1, np.minimum(12, rem), rem)
        months = int(max(12, horizon.max())) if len(r) else 12
        W = (
            weights(
                r["current_upb"],
                r["non_interest_bearing_upb"],
                r["current_rate_pct"].fillna(r["note_rate_pct"]),
                r["note_rate_pct"],
                rem,
                horizon,
                months,
            )
            * r["lgd_row"].to_numpy()[:, None]
        )
        mob = np.clip(r["months_on_book"].to_numpy(), 0, LT.MOB_CAP)
        k1 = pd.DataFrame(
            {"grade": r["grade"].to_numpy(), "mob": mob, "inc": r["inc_band"].to_numpy()}
        )
        l1_id = k1.groupby(list(k1), sort=False).ngroup().to_numpy()
        l1_keys = k1.groupby(l1_id).first()
        fk = LT.l2_frame(r).reset_index(drop=True).assign(l1=l1_id)
        f_id = fk.groupby(list(fk), sort=False).ngroup().to_numpy()
        f_keys = fk.groupby(f_id).first()
        uk = pd.DataFrame({"f": f_id, "seg": seg[nd], "g": group[nd], "c": cured[nd]})
        u_id = uk.groupby(list(uk), sort=False).ngroup().to_numpy()
        u_keys = uk.groupby(u_id).first()
        agg = sp.csr_matrix((np.ones(len(r)), (u_id, np.arange(len(r)))))
        WU = np.asarray(agg @ W)
        u_f, u_seg = u_keys["f"].to_numpy(), u_keys["seg"].to_numpy()
        u_l1 = f_keys["l1"].to_numpy()[u_f]
        s3 = rows[~nd]
        s3k = pd.DataFrame(
            {
                "seg": seg[~nd],
                "g": group[~nd],
                "c": cured[~nd],
                "upb": s3["current_upb"].to_numpy() * s3["lgd_row"].to_numpy(),
            }
        )
        s3k = s3k.groupby(["seg", "g", "c"], as_index=False)["upb"].sum()

        g1 = LT.codes(l1_keys["grade"], LT.GRADES)
        i1 = LT.codes(l1_keys["inc"], LT.INC_BANDS)
        m1 = l1_keys["mob"].to_numpy()
        fcodes = self.l2.codes(f_keys)
        f_l1 = f_keys["l1"].to_numpy()
        xp = [self.xpath(month, s, months) for s in range(len(self.scen))]
        xb = [self.xbar(month, s) for s in range(len(self.scen))]
        g_code, c_mask = u_keys["g"].to_numpy(), u_keys["c"].to_numpy()
        # Only units with exposure beyond month 12 (stage 2) need hazards over the whole term.
        long_u = np.flatnonzero(WU[:, 12:].any(1)) if months > 12 else np.array([], int)
        long_l1 = np.unique(u_l1[long_u])
        pos = np.searchsorted(long_l1, u_l1[long_u])
        WL, uf_long = WU[long_u, 12:], u_f[long_u]

        def run(d):
            lg = self.p3[d]
            res, extra = [], []
            for s in range(len(self.scen)):
                x12 = None if xp[s] is None else xp[s][:12]
                hd, hp = self.l1.hazards(g1, m1, i1, 12, x12, coefs=self.c1[d])
                pd12 = self.l2.pd12(x=xb[s], coefs=self.c2[d], fcodes=fcodes)
                md12, mp12, s12 = LT.paths(pd12, hd[f_l1], hp[f_l1])
                e = np.einsum("um,um->u", md12[u_f], WU[:, :12])
                if len(long_u):
                    hd, hp = self.l1.hazards(
                        g1[long_l1], m1[long_l1], i1[long_l1], months, xp[s], coefs=self.c1[d]
                    )
                    live = np.cumprod(1 - hd[:, 12:] - hp[:, 12:], axis=1)
                    g = hd[:, 12:] * np.column_stack([np.ones(len(hd)), live[:, :-1]])
                    e[long_u] += s12[uf_long] * np.einsum("um,um->u", g[pos], WL)
                e = e * lg[u_seg]
                e3 = lg[s3k["seg"].to_numpy()] * s3k["upb"].to_numpy()
                by_group = np.bincount(g_code, e, 21) + np.bincount(s3k["g"], e3, 21)
                cur = e[c_mask].sum() + e3[s3k["c"].to_numpy()].sum()
                res.append(np.append(by_group, cur))
                extra.append(mp12.sum(1))
            return np.array(res), extra

        point, extra = run(0)
        draws = np.array([run(d)[0] for d in range(1, self.n_draws + 1)])
        prepay12 = sum(w * x for w, x in zip(self.w, extra))[f_id]
        return point, draws, pd.Series(prepay12, index=r.index)

    def term_structure(self, grade, month, years=30, d=0):
        """Marginal and cumulative default probability by year for a new loan (clean, not
        modified, middle incentive band), weighted over the scenarios at `month`."""
        months = years * 12
        md_w, total = np.zeros(months), 0.0
        for s, w in enumerate(self.w):
            hd, hp = self.l1.hazards(
                [grade],
                np.array([0]),
                ["m05_05"],
                months,
                self.xpath(month, s, months),
                coefs=self.c1[d],
            )
            f = pd.DataFrame(
                {
                    "grade": [grade],
                    "age_band": ["1_12"],
                    "behaviour_state": ["clean"],
                    "modified": ["N"],
                }
            )
            pd12 = self.l2.pd12(f, self.xbar(month, s), coefs=self.c2[d])
            md, mp, surv = LT.paths(pd12, hd, hp)
            md_w += w * md[0]
            total = max(total, abs(md.sum() + mp.sum() + surv[0] - 1))
        annual = md_w.reshape(years, 12).sum(1)
        return annual, np.cumsum(annual), total


# --- backtests and descriptive tables ----------------------------------------------------------
def rag(realised, n, p):
    lo, hi = stats.binom.ppf(0.025, n, p) / n, stats.binom.ppf(0.975, n, p) / n
    vlo, vhi = S.vasicek_quantile(0.025, p, RHO), S.vasicek_quantile(0.975, p, RHO)
    colour = "green" if lo <= realised <= hi else ("amber" if vlo <= realised <= vhi else "red")
    return colour, float(lo), float(hi), float(vlo), float(vhi)


def backtest(staged: pd.DataFrame) -> tuple[list[dict], dict]:
    """E3: predicted mean PD12 against realised 12-month first defaults, stage 1 and 2 loans."""
    rows, verdict = [], {}
    b = staged[
        staged.reporting_date.isin(BACKTEST_DATES)
        & (staged.stage < 3)
        & staged.default_next_12m.notna()
    ]
    for (dt, g), x in b.groupby(["reporting_date", "grade"]):
        n, k, p = len(x), int(x.default_next_12m.astype(bool).sum()), float(x.pd12.mean())
        colour, lo, hi, vlo, vhi = rag(k / n, n, p)
        rows.append(
            {
                "reporting_date": dt.strftime("%Y-%m-%d"),
                "grade": g,
                "n": n,
                "predicted_pd": p,
                "realised_rate": S.jeffreys(k, n),
                "binomial_low": lo,
                "binomial_high": hi,
                "vasicek_low": vlo,
                "vasicek_high": vhi,
                "rag": colour,
                "covid_affected": dt in COVID_DATES,
            }
        )
        verdict.setdefault(dt, []).append((colour, k / n > p))
    return rows, verdict


def backtest_rule(verdict: dict) -> dict:
    counted = [d for d in BACKTEST_DATES if d not in COVID_DATES]
    parts, failed, missing = [], [], []
    for d in counted:
        v = verdict.get(d)
        if not v:
            missing.append(d)
            continue
        reds = [above for c, above in v if c == "red"]
        if reds:
            direction = "cycle" if len(set(reds)) == 1 else "ranking"
            side = (
                "under-predicted" if all(reds) else "over-predicted" if not any(reds) else "mixed"
            )
            failed.append(d)
            parts.append(f"{d:%Y-%m} Red in {len(reds)} grade(s), {side} ({direction})")
        else:
            parts.append(f"{d:%Y-%m} no Red")
    result = "FAIL" if failed else ("INSUFFICIENT" if missing else "PASS")
    ev = "; ".join(parts) or "no held-out date"
    if missing:
        ev += "; no stage 1/2 loans with an observed outcome at " + ", ".join(
            f"{d:%Y-%m}" for d in missing
        )
    ev += ". 2019-12 and 2020-12 are shown but not counted (forbearance period)."
    return {"rule_id": "E3", "result": result, "evidence": ev}


def prepayment_backtest(staged: pd.DataFrame) -> list[dict]:
    b = staged[
        staged.reporting_date.isin(BACKTEST_DATES)
        & (staged.stage < 3)
        & staged.prepaid_next_12m.notna()
    ]
    out = []
    for (dt, g), x in b.groupby(["reporting_date", "grade"]):
        out.append(
            {
                "reporting_date": dt.strftime("%Y-%m-%d"),
                "grade": g,
                "n": len(x),
                "predicted_rate": float(x.prepay12.mean()),
                "realised_rate": S.wilson(x.prepaid_next_12m.astype(bool).sum(), len(x)),
            }
        )
    return out


def migration(staged: pd.DataFrame) -> list[dict]:
    """Stage moves between consecutive quarter-ends (to 'exited' if the loan left the book)."""
    dates = sorted(staged.reporting_date.unique())
    st = staged.set_index(["reporting_date", "loan_id"])["stage"]
    out = []
    for a, b in zip(dates, dates[1:]):
        fr = st.loc[a]
        to = st.loc[b].reindex(fr.index)
        to = to.map(lambda v: "exited" if pd.isna(v) else str(int(v)))
        tab = pd.crosstab(fr, to)
        for s_from, row in tab.iterrows():
            tot = int(row.sum())
            for s_to, n in row.items():
                if n:
                    out.append(
                        {
                            "from_date": pd.Timestamp(a).strftime("%Y-%m-%d"),
                            "to_date": pd.Timestamp(b).strftime("%Y-%m-%d"),
                            "from_stage": str(s_from),
                            "to_stage": s_to,
                            "n": int(n),
                            "share": S.wilson(n, tot),
                        }
                    )
    return out


def stage2_drivers(staged: pd.DataFrame) -> list[dict]:
    s2 = staged[staged.stage == 2]
    reason = s2.stage_floor_reason.where(s2.stage_floor == 2, "pd_deterioration")
    out = []
    for (dt, rsn), n in s2.groupby([s2.reporting_date, reason]).size().items():
        tot = int((s2.reporting_date == dt).sum())
        out.append(
            {
                "reporting_date": dt.strftime("%Y-%m-%d"),
                "reason": rsn,
                "n_loans": int(n),
                "share_of_stage2": S.wilson(n, tot),
            }
        )
    return out
