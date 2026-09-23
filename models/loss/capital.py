"""Basel IRB residential-mortgage capital, illustrative (VALIDATION_PLAN section 9)."""

import numpy as np
import pandas as pd
from scipy import stats

from . import stats as S

R, CONF, PD_FLOOR, LGD_FLOOR = 0.15, 0.999, 0.0005, 0.05
LONG_RUN_DATES = [pd.Timestamp(f"{y}-12-01") for y in range(1999, 2016)]
LIMITS = [
    "Illustrative only; not a regulatory capital calculation.",
    "No 1.06 scaling factor and no output floor against the standardised approach.",
    "US banks hold these loans under the standardised approach, and RBI has not implemented "
    "IRB for Indian banks.",
    "Defaulted exposures are not given a K; their exposure and ECL are in ecl.json (stage 3).",
    "Shown next to ECL to compare expected and unexpected loss, nothing more.",
]


def k_irb(pd_, lgd, r=R):
    """K = LGD * N(G(PD) / sqrt(1 - R) + sqrt(R / (1 - R)) * G(0.999)) - PD * LGD."""
    n = stats.norm
    pd_ = np.asarray(pd_, float)
    return lgd * n.cdf(n.ppf(pd_) / np.sqrt(1 - r) + np.sqrt(r / (1 - r)) * n.ppf(CONF)) - pd_ * lgd


def long_run_pd(si: pd.DataFrame) -> pd.DataFrame:
    """Mean of the annual 12-month default rates at the 17 year-ends 1999-12 to 2015-12, by
    grade, floored at 0.05%, with a t interval over the years used."""
    x = si[si.reporting_date.isin(LONG_RUN_DATES) & si.default_next_12m.notna()]
    annual = x.groupby(["grade", "reporting_date"])["default_next_12m"].mean()
    loans = x.groupby("grade")["loan_id"].nunique()
    out = []
    for g, rates in annual.groupby(level=0):
        v, k = float(rates.mean()), len(rates)
        if k > 1:
            half = stats.t.ppf(0.975, k - 1) * rates.std(ddof=1) / np.sqrt(k)
            lo, hi = max(v - half, PD_FLOOR), max(v + half, PD_FLOOR)
        else:
            lo = hi = None
        out.append(
            {"grade": g, "pd": max(v, PD_FLOOR), "lo": lo, "hi": hi, "years": k, "n": int(loans[g])}
        )
    return pd.DataFrame(out).set_index("grade")


def build(si, latest: pd.DataFrame, downturn, ecl_by_grade) -> dict:
    """latest: staged rows at the latest reporting date. downturn: SegmentLGD of the downturn
    lgd_gross_of_mi (or None). ecl_by_grade: grade -> (point, draws) of stage 1+2 ECL."""
    body = {
        "status": "not_run",
        "parameters": {
            "correlation": R,
            "confidence": CONF,
            "pd_floor": PD_FLOOR,
            "lgd_floor": LGD_FLOOR,
            "lgd_basis": "downturn_gross_of_mi",
        },
        "reporting_date": None,
        "by_grade": [],
        "totals": {"ead": None, "rwa": None, "capital": None, "ecl": None},
        "limits": LIMITS,
    }
    if downturn is None or latest.empty:
        body["limits"] = LIMITS + ["Not run: no defaults dated 2008-01 to 2011-12 or no book."]
        return body
    lr = long_run_pd(si)
    book = latest[latest.stage < 3]
    lgd = np.maximum(downturn.segment_of(book["ltv_band"]).map(downturn.value), LGD_FLOOR)
    book = book.assign(lgd=lgd.to_numpy(), pd=book["grade"].map(lr["pd"]))
    book = book[book["pd"].notna()]
    book["cap"] = k_irb(book["pd"], book["lgd"]) * book["current_upb"]
    none = "none: illustrative, computed from point estimates"
    tot_draws = 0
    for g, x in book.groupby("grade"):
        ead, cap = x.current_upb.sum(), x.cap.sum()
        p, dr = ecl_by_grade.get(g, (0.0, np.zeros(1)))
        tot_draws = tot_draws + dr
        r = lr.loc[g]
        n = len(x)
        body["by_grade"].append(
            {
                "grade": g,
                "n_loans": n,
                "ead": S.metric(ead, n=n, method="none: population total"),
                "pd": S.metric(
                    r["pd"],
                    r["lo"],
                    r["hi"],
                    int(r["n"]),
                    "t_interval_years" if r["lo"] is not None else "none: one year only",
                ),
                "lgd": S.metric(
                    float((x.lgd * x.current_upb).sum() / ead),
                    n=n,
                    method="none: EAD-weighted downturn segment means; intervals in lgd_ead.json",
                ),
                "k": S.metric(cap / ead, n=n, method=none),
                "rwa": S.metric(12.5 * cap, n=n, method=none),
                "capital": S.metric(cap, n=n, method=none),
                "ecl": S.percentile(p, dr, n, "parameter_draws_1000"),
            }
        )
    n = len(book)
    ecl_tot = sum(v[0] for g, v in ecl_by_grade.items() if g in set(book.grade))
    body.update(
        {
            "status": "run",
            "reporting_date": latest.reporting_date.iloc[0].strftime("%Y-%m-%d"),
            "totals": {
                "ead": S.metric(book.current_upb.sum(), n=n, method="none: population total"),
                "rwa": S.metric(12.5 * book.cap.sum(), n=n, method=none),
                "capital": S.metric(book.cap.sum(), n=n, method=none),
                "ecl": S.percentile(ecl_tot, tot_draws, n, "parameter_draws_1000"),
            },
        }
    )
    return body
