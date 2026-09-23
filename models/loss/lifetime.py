"""Lifetime PD (VALIDATION_PLAN L1 to L3).

L1: discrete-time multinomial logit {stay, default, prepay} on loan-months, fitted on cell counts
aggregated in DuckDB. L2: behavioural 12-month PD, a logit on loan-quarter rows, also fitted on
cell counts. L3: combines them into monthly marginal default and prepayment paths.
"""

import duckdb
import numpy as np
import pandas as pd

from . import stats as S

GRADES = list("ABCDEFG")
MERGE_ORDER = list("AGBFCED")
AGE_BANDS = ["1_12", "13_24", "25_36", "37_60", "61_120", "121p"]
AGE_EDGES = [12, 24, 36, 60, 120]
INC_BANDS = ["lt_m05", "m05_05", "05_15", "gt_15"]
BEHAVIOUR = ["clean", "recent_dpd", "dpd_30", "dpd_60p"]
L2_COLS = [
    ("grade", GRADES),
    ("age_band", AGE_BANDS),
    ("behaviour_state", BEHAVIOUR),
    ("modified", ["N", "Y"]),
]
L1_FIT_END = "2016-12-01"
L2_FIT = ("1999-03-01", "2015-12-01")
MOB_CAP = 121  # from months on book 121 the age band never changes again


def age_index(mob):
    return np.searchsorted(AGE_EDGES, np.maximum(mob, 1), side="left")


def inc_band(x: pd.Series) -> pd.Series:
    b = np.select([x < -0.5, x <= 0.5, x <= 1.5], INC_BANDS[:3], INC_BANDS[3])
    return pd.Series(np.where(x.isna(), "m05_05", b), index=x.index)


def merge_grades(by_grade: pd.DataFrame, ok) -> dict:
    """Merge grades that fail `ok` (no events, so no finite estimate) into the surviving
    neighbour nearer grade D, in the order A, G, B, F, C, E, D (VALIDATION_PLAN section 10).
    D itself merges into the neighbour with more rows (C on a tie). Returns grade -> model grade."""
    groups = {g: [g] for g in GRADES if g in by_grade.index}
    size = by_grade.sum(1)
    changed = True
    while changed and len(groups) > 1:
        changed = False
        for g in MERGE_ORDER:
            if g not in groups or ok(by_grade.loc[groups[g]].sum()):
                continue
            alive = sorted(groups)
            i = alive.index(g)
            left, right = alive[:i], alive[i + 1 :]
            if g < "D":
                target = right[0] if right else left[-1]
            elif g > "D":
                target = left[-1] if left else right[0]
            else:
                cands = ([left[-1]] if left else []) + ([right[0]] if right else [])
                target = max(cands, key=lambda c: (size[groups[c]].sum(), c == "C"))
            groups[target] += groups.pop(g)
            changed = True
            break
    out = {g: t for t, members in groups.items() for g in members}
    alive = sorted(groups)
    for g in GRADES:  # a grade with no rows at all takes its nearest surviving grade towards D
        if g not in out and alive:
            side = [a for a in alive if (a > g if g < "D" else a < g)] or alive
            out[g] = min(side, key=lambda a: abs(ord(a) - ord(g)))
    return out


def merge_levels(tot: pd.DataFrame, order: list, ok) -> dict:
    """Ordered bands (age, incentive, behaviour): a level failing `ok` (no events of an outcome)
    is pooled with the level before it (the next one for the first level), repeated until every
    pooled level passes. The plan's merge rule names grades only; this is the same rule applied
    to the other ordered factors, and every pooling is reported. Levels with no rows at all take
    their nearest present level. Returns level -> model level."""
    present = [lev for lev in order if lev in tot.index]
    groups = [[lev] for lev in present]
    while len(groups) > 1:
        bad = [i for i, g in enumerate(groups) if not ok(tot.loc[g].sum())]
        if not bad:
            break
        i = bad[0]
        if i > 0:
            groups[i - 1] += groups.pop(i)
        else:
            groups[1] = groups.pop(0) + groups[0]
    out = {lev: g[0] for g in groups for lev in g}
    for k, lev in enumerate(order):
        if lev not in out and present:
            out[lev] = out[min(present, key=lambda p: abs(order.index(p) - k))]
    return out


class Logit:
    """A fitted (multinomial) logit on categorical cells plus an optional continuous covariate."""

    def __init__(self, cells: pd.DataFrame, cats: dict, counts: list[str], cont=()):
        self.cats, self.cont = cats, list(cont)
        X, self.names = S.design(cells, cats, self.cont)
        self.beta, self.cov, self.converged = S.fit_mnlogit(X, cells[counts].to_numpy(float))
        if not self.converged:
            raise RuntimeError(f"logit on {counts} did not converge")

    def draws(self, n, seed):
        rng = np.random.default_rng(seed)
        flat = rng.multivariate_normal(self.beta.ravel(), self.cov, n, method="eigh")
        return flat.reshape(n, *self.beta.shape)

    def vec(self, beta, k, col, order, level_map) -> np.ndarray:
        """Coefficient of each level in order, through the level merge map."""
        c = self.coef(beta, col, k)
        return np.array([c[level_map[lev]] for lev in order])

    def coef(self, beta, col, k=0) -> dict:
        """Level -> coefficient for one categorical column (reference level 0)."""
        out = {lev: 0.0 for lev in self.cats[col]}
        for j, name in enumerate(self.names):
            if name.startswith(col + "="):
                out[name[len(col) + 1 :]] = beta[k, j]
        return out


# --- L1 --------------------------------------------------------------------------------------
L1_SQL = """
with fd as (select loan_id, default_period from '{fde}' where definition = 'primary'),
rs as (
  select s.grade, m.age_band, m.period, m.rate_incentive_pct, m.is_first_default_month,
         m.exit_type, m.loan_id, dd.market_rate_pct
  from '{flm}' m
  join '{scores}' s on s.loan_id = m.loan_id
  left join fd on fd.loan_id = m.loan_id
  left join '{dim_date}' dd on dd.month = m.period
  where m.months_on_book >= 1 and m.period <= DATE '{end}' and s.grade is not null
    and (fd.default_period is null or m.period <= fd.default_period)
    and not (coalesce(m.exit_type, '') in ('other_exit', 'matured')
             and not m.is_first_default_month)
)
select grade, age_band,
  case when rate_incentive_pct is null then 'm05_05'
       when rate_incentive_pct < -0.5 then 'lt_m05'
       when rate_incentive_pct <= 0.5 then 'm05_05'
       when rate_incentive_pct <= 1.5 then '05_15' else 'gt_15' end as inc_band,
  {month_expr} as month,
  count(*) as n,
  sum(case when is_first_default_month then 1 else 0 end) as n_default,
  sum(case when not is_first_default_month and exit_type = 'prepaid' then 1 else 0 end)
    as n_prepay,
  sum(case when market_rate_pct is null then 1 else 0 end) as n_no_market_rate
from rs group by all
"""


def l1_cells(paths: dict, by_month: bool, temp_dir=None) -> tuple[pd.DataFrame, pd.Series]:
    """Cell counts for L1 and the distinct loans per grade in its risk set."""
    con = duckdb.connect()
    if temp_dir:
        con.execute(f"set temp_directory = '{temp_dir}'")
    month = "year(period) * 12 + month(period) - 1" if by_month else "0"
    fmt = {k: str(v).replace("\\", "/") for k, v in paths.items()}
    cells = con.execute(L1_SQL.format(**fmt, end=L1_FIT_END, month_expr=month)).df()
    loans = con.execute(
        f"""select s.grade, count(distinct m.loan_id) n from '{fmt["flm"]}' m
        join '{fmt["scores"]}' s on s.loan_id = m.loan_id
        where m.months_on_book >= 1 and m.period <= DATE '{L1_FIT_END}' and s.grade is not null
        group by 1"""
    ).df()
    return cells, loans.set_index("grade")["n"]


class L1:
    def __init__(self, cells: pd.DataFrame, macro=None):
        cells = cells.copy()
        tot = cells.groupby("grade")[["n_default", "n_prepay"]].sum()
        self.grade_map = merge_grades(tot, lambda r: r["n_default"] > 0 and r["n_prepay"] > 0)
        cells["grade"] = cells["grade"].map(self.grade_map)
        ok = lambda r: r["n_default"] > 0 and r["n_prepay"] > 0  # noqa: E731
        self.age_map = merge_levels(
            cells.groupby("age_band")[["n_default", "n_prepay"]].sum(), AGE_BANDS, ok
        )
        self.inc_map = merge_levels(
            cells.groupby("inc_band")[["n_default", "n_prepay"]].sum(), INC_BANDS, ok
        )
        cells["age_band"] = cells["age_band"].map(self.age_map)
        cells["inc_band"] = cells["inc_band"].map(self.inc_map)
        cont = []
        if macro is not None:
            cells["x"] = macro.x(cells["month"].to_numpy())
            cells = cells[cells["x"].notna()]
            cont = ["x"]
        cells["n_stay"] = cells["n"] - cells["n_default"] - cells["n_prepay"]
        keys = ["grade", "age_band", "inc_band"] + cont
        cells = cells.groupby(keys, as_index=False)[["n_stay", "n_default", "n_prepay"]].sum()
        cats = {
            c: list(cells.groupby(c)["n_stay"].sum().sort_values(ascending=False).index)
            for c in ("grade", "age_band", "inc_band")
        }
        self.model = Logit(cells, cats, ["n_stay", "n_default", "n_prepay"], cont)
        self.macro = macro is not None

    def coefs(self, beta=None):
        """Per outcome (default, prepay): intercept, then coefficient vectors over GRADES,
        AGE_BANDS and INC_BANDS (after merging), and the macro coefficient."""
        beta, m = (self.model.beta if beta is None else beta), self.model
        return [
            (
                beta[k, 0],
                m.vec(beta, k, "grade", GRADES, self.grade_map),
                m.vec(beta, k, "age_band", AGE_BANDS, self.age_map),
                m.vec(beta, k, "inc_band", INC_BANDS, self.inc_map),
                beta[k, -1] if self.macro else 0.0,
            )
            for k in range(2)
        ]

    def hazards(self, grade, mob0, inc, months, x=None, beta=None, coefs=None):
        """Monthly default and prepayment probabilities (n x months) for loans starting at
        months on book mob0 (the incentive band is held at its current value)."""
        coefs = self.coefs(beta) if coefs is None else coefs
        gi, ii = codes(grade, GRADES), codes(inc, INC_BANDS)
        age = age_index(np.asarray(mob0)[:, None] + np.arange(1, months + 1)[None, :])
        etas = []
        for a0, cg, ca, ci, bx in coefs:
            e = (a0 + cg[gi] + ci[ii])[:, None] + ca[age]
            if x is not None:
                e = e + bx * x
            etas.append(e)
        ed, ep = np.exp(np.minimum(etas[0], 50)), np.exp(np.minimum(etas[1], 50))
        den = 1 + ed + ep
        return ed / den, ep / den


def codes(values, order) -> np.ndarray:
    """Positions of values in order (values may already be integer codes)."""
    v = np.asarray(values)
    if v.dtype.kind in "iu":
        return v
    return pd.Categorical(v, categories=order).codes.astype(np.int64)


# --- L2 --------------------------------------------------------------------------------------
def l2_frame(si: pd.DataFrame) -> pd.DataFrame:
    """L2 covariates for stage-input rows: the 'pre' age band is pooled with 1_12."""
    return pd.DataFrame(
        {
            "grade": si["grade"].to_numpy(),
            "age_band": si["age_band"].replace("pre", "1_12").to_numpy(),
            "behaviour_state": si["behaviour_state"].to_numpy(),
            "modified": si["modified"].map({True: "Y", False: "N"}).to_numpy(),
        },
        index=si.index,
    )


class L2:
    def __init__(self, si: pd.DataFrame, xbar=None):
        rd = si["reporting_date"]
        fit = si[
            (rd >= L2_FIT[0])
            & (rd <= L2_FIT[1])
            & si["default_next_12m"].notna()
            & si["grade"].notna()
        ]
        f = l2_frame(fit)
        f["y"] = fit["default_next_12m"].astype(bool).to_numpy()
        cont = []
        if xbar is not None:
            f["x"] = xbar.loc[fit.index].to_numpy()
            f = f[f["x"].notna()]
            cont = ["x"]
        tot = f.groupby("grade")["y"].agg(["sum", "size"])
        tot["non"] = tot["size"] - tot["sum"]
        self.grade_map = merge_grades(tot[["sum", "non"]], lambda r: r["sum"] > 0 and r["non"] > 0)
        f["grade"] = f["grade"].map(self.grade_map)
        ok = lambda r: r["sum"] > 0 and r["non"] > 0  # noqa: E731
        self.maps = {}
        for col, order in [
            ("age_band", AGE_BANDS),
            ("behaviour_state", BEHAVIOUR),
            ("modified", ["N", "Y"]),
        ]:
            t = f.groupby(col)["y"].agg(["sum", "size"])
            t["non"] = t["size"] - t["sum"]
            self.maps[col] = merge_levels(t[["sum", "non"]], order, ok)
            f[col] = f[col].map(self.maps[col])
        keys = ["grade", "age_band", "behaviour_state", "modified"] + cont
        cells = f.groupby(keys, as_index=False)["y"].agg(n_def="sum", n="size")
        cells["n_non"] = cells["n"] - cells["n_def"]
        cats = {}
        for col, levels in [
            ("grade", GRADES),
            ("age_band", AGE_BANDS),
            ("behaviour_state", BEHAVIOUR),
            ("modified", ["N", "Y"]),
        ]:
            size = cells.groupby(col)["n"].sum().sort_values(ascending=False)
            ordered = [lev for lev in size.index if lev in levels]
            if col in ("behaviour_state", "modified"):  # interpretable reference levels
                ordered = sorted(ordered, key=lambda v: v != levels[0])
            cats[col] = ordered
        self.model = Logit(cells, cats, ["n_non", "n_def"], cont)
        self.macro = xbar is not None
        self.n_fit = len(f)

    def coefs(self, beta=None):
        beta, m = (self.model.beta if beta is None else beta), self.model
        vecs = [m.vec(beta, 0, "grade", GRADES, self.grade_map)]
        vecs += [m.vec(beta, 0, col, order, self.maps[col]) for col, order in L2_COLS[1:]]
        return beta[0, 0], vecs, (beta[0, -1] if self.macro else 0.0)

    @staticmethod
    def codes(f: pd.DataFrame):
        """Integer codes of the l2_frame columns (the 'default' state, never scored, gets 0)."""
        return [np.maximum(codes(f[col], order), 0) for col, order in L2_COLS]

    def pd12(self, f=None, x=None, beta=None, coefs=None, fcodes=None):
        """12-month PD for rows of l2_frame (x: the macro covariate, if the model has it)."""
        b0, vecs, bx = self.coefs(beta) if coefs is None else coefs
        fcodes = self.codes(f) if fcodes is None else fcodes
        eta = b0 + sum(v[c] for v, c in zip(vecs, fcodes))
        if self.macro:
            eta = eta + bx * np.asarray(x)
        return 1 / (1 + np.exp(-eta))


# --- L3 --------------------------------------------------------------------------------------
def paths(pd12, hd, hp):
    """Marginal default and prepayment probabilities by month (L3), and final survival.

    Months 1-12: default is PD12 / 12 a month (L2 spread evenly), prepayment is the L1 prepayment
    probability applied to survivors. From month 13 both come from L1, applied to survivors. The
    month-1-12 default is capped at the survivors left after prepayment, so survival never goes
    negative; by construction sum(md) + sum(mp) + survival = 1.
    """
    n, months = hd.shape
    md, mp = np.empty((n, months)), np.empty((n, months))
    s = np.ones(n)
    monthly = np.asarray(pd12, float) / 12
    for m in range(months):
        mp[:, m] = s * hp[:, m]
        md[:, m] = np.minimum(monthly, s - mp[:, m]) if m < 12 else s * hd[:, m]
        s = np.maximum(s - md[:, m] - mp[:, m], 0.0)  # rounding below 0 once exhausted
    return md, mp, s
