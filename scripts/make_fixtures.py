"""Generate the SYNTHETIC test fixtures that follow CONTRACTS.md.

Everything written here is made up by a small simulation with a fixed seed. No value, row or
distribution is copied from the Freddie Mac data. Every fixture is marked as synthetic: Parquet
files carry the file-metadata key `synthetic = true`, JSON artefacts carry `"synthetic": true`,
and every loan identifier has an `S` in position 6 (for example `F07Q1S000123`), which no real
Freddie Mac identifier has.

Output, under tests/fixtures/:
  raw/sample_orig_YYYY.txt, raw/sample_perf_YYYY.txt   raw-layout files for the extractor and
                                                          the dbt CI build (a few vintages)
  marts/<mart>.parquet                                    every dbt mart in the contract
  models_out/<name>.parquet                               loan_scores and ecl_results
  artefacts/<name>.json                                   every published JSON artefact

The marts are derived from the simulated panel with pandas, following the definitions in
VALIDATION_PLAN.md, so they are coherent with each other and with the raw files. This is fixture
code only: the real marts are built by the dbt project.

Run:  python scripts/make_fixtures.py
"""

import hashlib
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "extract"))
import build_parquet  # noqa: E402

from tests import contracts as C  # noqa: E402

OUT = ROOT / "tests" / "fixtures"
SEED = 20260923
N_LOANS = 4000
RAW_VINTAGES = [2005, 2007, 2019, 2022]
RAW_LOANS_PER_VINTAGE = 12


def mi(y: int, m: int) -> int:
    """Month index: months since year 0. Dates are handled as month indices throughout."""
    return y * 12 + m - 1


def to_date(i: int) -> date:
    return date(i // 12, i % 12 + 1, 1)


CUTOFF = mi(2026, 3)
DATA_START = mi(1999, 1)
COVID = (mi(2020, 4), mi(2021, 3))
DISASTER = (mi(2017, 9), mi(2017, 11))
ELTV_FROM = mi(2017, 1)

# Synthetic market-rate path (percent); only its shape matters for the fixtures.
MARKET = {
    1999: 7.4,
    2000: 8.0,
    2001: 7.0,
    2002: 6.5,
    2003: 5.8,
    2004: 5.8,
    2005: 5.9,
    2006: 6.4,
    2007: 6.3,
    2008: 6.0,
    2009: 5.0,
    2010: 4.7,
    2011: 4.5,
    2012: 3.7,
    2013: 4.0,
    2014: 4.2,
    2015: 3.9,
    2016: 3.7,
    2017: 4.0,
    2018: 4.5,
    2019: 4.0,
    2020: 3.1,
    2021: 3.0,
    2022: 5.3,
    2023: 6.8,
    2024: 6.7,
    2025: 6.6,
    2026: 6.3,
}
STATES = ["CA", "TX", "FL", "IL", "NY", "OH", "GA", "AZ", "WA", "NJ"]
CREDIT_EVENT_ZBC = {2, 3, 9, 15}


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# ---------------------------------------------------------------------------------------------
# 1. Loans
# ---------------------------------------------------------------------------------------------
def make_loans(rng: np.random.Generator) -> pd.DataFrame:
    years = np.arange(1999, 2026)
    w = np.where(years <= 2015, 2.0, 1.0)
    vy = rng.choice(years, size=N_LOANS, p=w / w.sum())
    q = rng.integers(1, 5, size=N_LOANS)
    rows = []
    for i in range(N_LOANS):
        y, qq = int(vy[i]), int(q[i])
        fpd = mi(y, 3 * (qq - 1) + 1) + 2
        term = int(rng.choice([360, 180, 240], p=[0.8, 0.18, 0.02]))
        ltv = int(
            rng.choice(
                [55, 65, 75, 80, 85, 90, 95, 97], p=[0.08, 0.1, 0.17, 0.3, 0.07, 0.12, 0.1, 0.06]
            )
        )
        fico = int(np.clip(rng.normal(735, 50), 550, 840))
        dti = int(np.clip(rng.normal(34, 9), 5, 65))
        occ = str(rng.choice(["P", "S", "I"], p=[0.88, 0.05, 0.07]))
        purpose = str(rng.choice(["P", "C", "N"], p=[0.45, 0.25, 0.3]))
        crisis = 1.0 if 2005 <= y <= 2008 else 0.0
        lp = (
            -4.9
            - 0.018 * (fico - 735)
            + 0.045 * (ltv - 80)
            + 0.03 * (dti - 34)
            + 0.6 * (occ == "I")
            + 0.4 * (purpose == "C")
            + crisis
        )
        rate = (
            MARKET[y] + (-0.5 if term <= 180 else 0.0) + 0.004 * (740 - fico) + rng.normal(0, 0.3)
        )
        rows.append(
            {
                "loan_id": f"F{y % 100:02d}Q{qq}S{i:06d}",
                "vintage_year": y,
                "quarter": qq,
                "fpd": fpd,
                "term": term,
                "upb": float(max(30, round(rng.lognormal(12.1, 0.45) / 1000)) * 1000),
                "rate": round(float(rate), 3),
                "fico": None if rng.random() < 0.004 else fico,
                "ltv": ltv,
                "cltv": ltv + (5 if rng.random() < 0.1 else 0),
                "dti": None if rng.random() < 0.07 else dti,
                "mi": 0 if ltv <= 80 else {85: 12, 90: 25, 95: 30, 97: 35}[ltv],
                "units": 1 if rng.random() < 0.97 else 2,
                "occ": occ,
                "purpose": purpose,
                "channel": str(rng.choice(["R", "B", "C", "T"], p=[0.55, 0.1, 0.2, 0.15])),
                "ptype": str(
                    rng.choice(["SF", "PU", "CO", "MH", "CP"], p=[0.7, 0.2, 0.07, 0.02, 0.01])
                ),
                "state": str(rng.choice(STATES)),
                "fthb": str(rng.choice(["Y", "N"], p=[0.15, 0.85])),
                "borrowers": int(rng.choice([1, 2], p=[0.45, 0.55])),
                "super": bool(rng.random() < 0.02),
                "harp": bool(2010 <= y <= 2016 and rng.random() < 0.08),
                "lp": lp,
                "workout": int(rng.integers(4, 20)),
            }
        )
    return pd.DataFrame(rows)


def annuity(upb: float, rate_pct: float, n: int) -> float:
    r = rate_pct / 1200
    return upb / n if r == 0 else upb * r / (1 - (1 + r) ** -n)


# ---------------------------------------------------------------------------------------------
# 2. Monthly panel (raw performance fields)
# ---------------------------------------------------------------------------------------------
def simulate(L: dict, rng: np.random.Generator) -> list[dict]:
    rows = []
    upb, nib = L["upb"], 0.0
    pay = annuity(upb, L["rate"], L["term"])
    status, months_90, forb_left, dis_left, ra_left = 0, 0, 0, 0, 0
    mod_state, def_state, age_offset = None, None, 0
    p_enter = sigmoid(L["lp"])
    for p in range(L["fpd"] - 1, CUTOFF + 1):
        mob = p - L["fpd"] + 1
        bap = disaster = zbc = None
        new_mod = new_def = False
        if mob >= 1:
            r = rng.random()
            if status == "RA":
                ra_left -= 1
                if ra_left <= 0:
                    zbc = 9
            elif forb_left > 0:
                bap, status, forb_left = "F", min(99, status + 1), forb_left - 1
                if forb_left == 0:
                    nib += pay * status
                    upb += 0.0
                    status, new_def = 0, True
            elif dis_left > 0:
                disaster, status, dis_left = "Y", min(99, status + 1), dis_left - 1
                if dis_left == 0:
                    status = 0
            elif status == 0:
                incentive = L["rate"] - MARKET[min(2026, p // 12)]
                p_prepay = 0.02 + 0.04 * sigmoid(3 * (incentive - 0.75))
                if COVID[0] <= p <= COVID[1] and r < 0.03:
                    forb_left = int(rng.integers(4, 10)) - 1
                    bap, status = "F", 1
                elif DISASTER[0] <= p <= DISASTER[1] and r < 0.01:
                    dis_left, disaster, status = 2, "Y", 1
                elif r < p_enter:
                    status = 1
                elif r < p_enter + p_prepay:
                    zbc = 1
                elif r < p_enter + p_prepay + 0.0004:
                    zbc = 96
                elif mod_state and r > 0.99:
                    zbc = 16
                else:
                    interest = upb * L["rate"] / 1200
                    upb = max(0.0, upb - max(0.0, pay - interest))
                    if mob >= L["term"] - age_offset and upb < 1:
                        zbc = 1
            elif status == 1:
                status = 0 if r < 0.45 else 2
            elif status == 2:
                status = 0 if r < 0.25 else 3
            else:
                months_90 += 1
                if months_90 >= L["workout"]:
                    kind = rng.choice(["RA", 3, 2, 15], p=[0.55, 0.28, 0.12, 0.05])
                    if kind == "RA":
                        status, ra_left = "RA", int(rng.integers(1, 4))
                    else:
                        zbc = int(kind)
                elif r < 0.05:
                    status, months_90, new_mod, age_offset = 0, 0, True, mob
                    nib += pay * 3
                elif r < 0.08:
                    status, months_90 = 0, 0
                else:
                    status = min(99, status + 1)
        mod_flag = "Y" if new_mod else ("P" if mod_state else None)
        mod_state = mod_state or new_mod
        def_flag = "C" if new_def else ("P" if def_state else None)
        def_state = def_state or new_def
        shown = (
            "XX"
            if (status == 0 and mob >= 1 and rng.random() < 0.0008)
            else ("RA" if status == "RA" else f"{status:02d}")
        )
        row = {
            "loan_id": L["loan_id"],
            "period": p,
            "status": shown,
            "loan_age": mob - age_offset if mob >= 1 else 0,
            "remaining": max(0, L["term"] - mob),
            "mod_flag": mod_flag,
            "zbc": zbc,
            "zb_date": p if zbc else None,
            "current_rate": L["rate"],
            "nib": round(nib, 2),
            "deferral": def_flag,
            "bap": bap,
            "disaster": disaster,
            "eltv": (
                int(round(L["ltv"] * upb / L["upb"] * rng.uniform(0.75, 1.0)))
                if p >= ELTV_FROM
                else None
            ),
        }
        if zbc:
            row.update(current_upb=0.0, ib=0.0, removal_upb=round(upb + nib, 2))
            if zbc in CREDIT_EVENT_ZBC:
                row.update(loss_fields(L, upb + nib, months_90, p, rng))
        else:
            row.update(current_upb=round(upb + nib, 2), ib=round(upb, 2), removal_upb=None)
        rows.append(row)
        if zbc:
            break
    return rows


def loss_fields(L: dict, bal: float, months_delinquent: int, p: int, rng) -> dict:
    legal, maint = round(rng.uniform(2000, 5000), 2), round(rng.uniform(1000, 4000), 2)
    taxes, misc = round(rng.uniform(2000, 6000), 2), round(rng.uniform(500, 2000), 2)
    nsp = -round(bal * rng.uniform(0.55, 0.9), 2)
    dai = round(bal * L["rate"] / 1200 * (months_delinquent + 3), 2)
    mi_rec = -round(L["mi"] / 100 * (bal + dai) * 0.8, 2) if L["mi"] else 0.0
    non_mi = -round(rng.uniform(0, 2000), 2)
    total = round(legal + maint + taxes + misc, 2)
    loss = round(bal + nsp + dai + total + mi_rec + non_mi, 2)
    return {
        "legal": legal,
        "maint": maint,
        "taxes": taxes,
        "misc": misc,
        "nsp": nsp,
        "dai": dai,
        "mi_rec": mi_rec,
        "non_mi": non_mi,
        "total_exp": total,
        # Freddie Mac nulls actual loss for dispositions in the last three months.
        "actual_loss": None if p > CUTOFF - 3 else loss,
    }


# ---------------------------------------------------------------------------------------------
# 3. Derivations (fixture-only pandas version of the plan's definitions)
# ---------------------------------------------------------------------------------------------
def age_band(mob: int) -> str:
    if mob <= 0:
        return "pre"
    for hi, name in [(12, "1_12"), (24, "13_24"), (36, "25_36"), (60, "37_60"), (120, "61_120")]:
        if mob <= hi:
            return name
    return "121p"


def ltv_band(v) -> str:
    if v is None or pd.isna(v):
        return "missing"
    return (
        "le_60"
        if v <= 60
        else "60_80"
        if v <= 80
        else "80_90"
        if v <= 90
        else ("90_95" if v <= 95 else "gt_95")
    )


def fico_band(v) -> str:
    if v is None or pd.isna(v):
        return "missing"
    for hi, name in [
        (620, "lt_620"),
        (660, "620_659"),
        (700, "660_699"),
        (740, "700_739"),
        (780, "740_779"),
    ]:
        if v < hi:
            return name
    return "ge_780"


def term_band(t: int) -> str:
    return "le_180" if t <= 180 else "181_240" if t <= 240 else "gt_240"


def exit_type(zbc, mob, term):
    if zbc is None or pd.isna(zbc):
        return None
    zbc = int(zbc)
    if zbc == 1:
        return "matured" if mob >= term - 1 else "prepaid"
    return "credit_event" if zbc in CREDIT_EVENT_ZBC else "other_exit"


BUCKET_SMA = {
    "current": "standard_or_sma_0",
    "dpd_30": "sma_1",
    "dpd_60": "sma_2",
    "dpd_90p": "npa",
    "reo": "npa",
    "unknown": "unknown",
}


def bucket(s: str) -> str:
    if s == "RA":
        return "reo"
    if s == "XX":
        return "unknown"
    n = int(s)
    return "current" if n == 0 else "dpd_30" if n == 1 else "dpd_60" if n == 2 else "dpd_90p"


def episodes(triggers, statuses, zbcs):
    """Per-row in_default and cure flags for one loan (D4: three consecutive `00` months)."""
    in_def, streak, out_in, out_cure = False, 0, [], []
    for trig, s, z in zip(triggers, statuses, zbcs):
        cure = False
        if trig:
            in_def, streak = True, 0
        elif in_def:
            streak = streak + 1 if (s == "00" and z is None) else 0
            if streak == 3:
                in_def, cure = False, True
        out_in.append(in_def)
        out_cure.append(cure)
    return out_in, out_cure


def derive(loans: pd.DataFrame, panel: pd.DataFrame) -> dict[str, pd.DataFrame]:
    L = loans.set_index("loan_id")
    lm = panel.copy()
    lm["zbc"] = lm["zbc"].astype("object").where(lm["zbc"].notna(), None)
    lm["fpd"] = lm["loan_id"].map(L["fpd"])
    lm["term"] = lm["loan_id"].map(L["term"])
    lm["vintage_year"] = lm["loan_id"].map(L["vintage_year"])
    lm["months_on_book"] = lm["period"] - lm["fpd"] + 1
    lm["age_band"] = lm["months_on_book"].map(age_band)
    lm["dpd_bucket"] = lm["status"].map(bucket)
    lm["sma_class"] = lm["dpd_bucket"].map(BUCKET_SMA)
    dpd_num = pd.to_numeric(lm["status"], errors="coerce")
    lm["forbearance_flag"] = (lm["bap"] == "F") | (lm["disaster"] == "Y")
    credit = lm["zbc"].isin(list(CREDIT_EVENT_ZBC))
    naive = (dpd_num >= 3) | (lm["status"] == "RA") | credit
    lm["default_exempt"] = (dpd_num >= 3) & lm["forbearance_flag"]
    lm["default_trigger"] = naive & ~lm["default_exempt"] | (lm["status"] == "RA") | credit
    lm["naive_trigger"] = naive
    lm["exit_type"] = [
        exit_type(z, m, t) for z, m, t in zip(lm["zbc"], lm["months_on_book"], lm["term"])
    ]

    # Market rate: median note rate of >240-month loans by first-payment month, with the last
    # available value carried forward (L1).
    months = list(range(DATA_START, CUTOFF + 1))
    mkt_obs = loans[loans["term"] > 240].groupby("fpd")["rate"].median().reindex(months)
    mkt = mkt_obs.ffill()
    lm["rate_incentive_pct"] = lm["current_rate"] - lm["period"].map(mkt)

    parts = []
    for _, g in lm.groupby("loan_id", sort=False):
        g = g.sort_values("period").copy()
        trig = g["default_trigger"].tolist()
        g["in_default"], g["is_cure_month"] = episodes(
            trig, g["status"].tolist(), g["zbc"].tolist()
        )
        first = next((i for i, t in enumerate(trig) if t), None)
        g["is_first_default_month"] = [i == first for i in range(len(g))]
        prev_exit = g["zbc"].shift(1).tolist()
        g["at_risk_at_start"] = [
            i > 0 and pd.isna(prev_exit[i]) and (first is None or first >= i) for i in range(len(g))
        ]
        late = (pd.to_numeric(g["status"], errors="coerce") >= 1) | (g["status"] == "RA")
        g["recent_dpd30_12m"] = (
            late.astype(int).shift(1).rolling(12, min_periods=1).max().fillna(0).astype(bool)
        )
        cure_period = g["period"].where(g["is_cure_month"])
        last_cure = cure_period.ffill()
        g["cured_within_6m"] = (g["period"] - last_cure <= 5) & ~g["in_default"]
        parts.append(g)
    lm = pd.concat(parts, ignore_index=True)

    # ---- dim_date
    dim_date = pd.DataFrame({"month": months})
    dim_date["year"] = dim_date["month"] // 12
    dim_date["quarter"] = (dim_date["month"] % 12) // 3 + 1
    dim_date["year_quarter"] = dim_date["year"].astype(str) + "Q" + dim_date["quarter"].astype(str)
    dim_date["is_quarter_end"] = dim_date["month"] % 3 == 2
    dim_date["economic_period"] = dim_date["month"].map(economic_period)
    dim_date["market_rate_pct"] = dim_date["month"].map(mkt)
    dim_date["market_rate_carried_forward"] = dim_date["month"].map(mkt_obs.isna() & mkt.notna())

    # ---- dim_loan
    last = lm.groupby("loan_id").tail(1).set_index("loan_id")
    spread_key = loans["fpd"].astype(str) + (loans["term"] <= 180).map({True: "s", False: "l"})
    spread = loans["rate"] - loans.groupby(spread_key)["rate"].transform("median")
    dim_loan = pd.DataFrame(
        {
            "loan_id": loans["loan_id"],
            "vintage_year": loans["vintage_year"],
            "vintage_quarter": loans["vintage_year"].astype(str)
            + "Q"
            + loans["quarter"].astype(str),
            "first_payment_date": loans["fpd"],
            "maturity_date": loans["fpd"] + loans["term"] - 1,
            "original_upb": loans["upb"],
            "original_loan_term": loans["term"],
            "term_band": loans["term"].map(term_band),
            "note_rate_pct": loans["rate"],
            "rate_spread_pct": spread.round(4),
            "fico": loans["fico"],
            "fico_band": loans["fico"].map(fico_band),
            "ltv_pct": loans["ltv"],
            "ltv_band": loans["ltv"].map(ltv_band),
            "cltv_pct": loans["cltv"],
            "dti_pct": loans["dti"],
            "mi_pct": loans["mi"],
            "number_of_units": loans["units"],
            "occupancy_status": loans["occ"],
            "channel": loans["channel"],
            "loan_purpose": loans["purpose"],
            "property_type": loans["ptype"],
            "property_state": loans["state"],
            "first_time_homebuyer": loans["fthb"],
            "number_of_borrowers": loans["borrowers"],
            "super_conforming": loans["super"],
            "harp_flag": loans["harp"],
        }
    )
    dim_loan["last_period"] = dim_loan["loan_id"].map(last["period"])
    dim_loan["terminal_zero_balance_code"] = dim_loan["loan_id"].map(last["zbc"])
    dim_loan["exit_type"] = dim_loan["loan_id"].map(last["exit_type"])
    defect = lm.dropna(subset=["defect_date"]).groupby("loan_id")["defect_date"].min()
    dim_loan["defect_settlement_date"] = dim_loan["loan_id"].map(defect)

    # ---- fct_loan_month
    fct_loan_month = lm.rename(
        columns={
            "ib": "interest_bearing_upb",
            "nib": "non_interest_bearing_upb",
            "current_rate": "current_rate_pct",
            "status": "dpd_status_raw",
            "bap": "assistance_plan",
            "eltv": "eltv_pct",
            "zbc": "zero_balance_code",
        }
    )
    fct_loan_month["payment_deferral"] = lm["deferral"].notna()
    fct_loan_month["modified"] = lm["mod_flag"].notna()

    # ---- fct_default_events
    events = []
    for definition, col in [("primary", "default_trigger"), ("naive", "naive_trigger")]:
        for loan_id, g in lm[lm[col]].groupby("loan_id"):
            events.append(
                default_event(loan_id, definition, g.iloc[0], lm, last, L, defect.get(loan_id))
            )
    fct_default_events = pd.DataFrame(events)

    # ---- fct_loss_events
    prim = fct_default_events[
        (fct_default_events["definition"] == "primary")
        & fct_default_events["resolution"].isin(["credit_event_loss", "paid_off"])
    ]
    fct_loss_events = pd.DataFrame(
        [loss_event(e, last.loc[e.loan_id], L.loc[e.loan_id]) for e in prim.itertuples()]
    )

    return {
        "lm": lm,
        "dim_date": dim_date,
        "dim_loan": dim_loan,
        "fct_loan_month": fct_loan_month,
        "fct_default_events": fct_default_events,
        "fct_loss_events": fct_loss_events,
    }


def economic_period(m: int) -> str:
    if m <= mi(2006, 12):
        return "pre_crisis"
    if m <= mi(2011, 12):
        return "crisis"
    if m <= mi(2020, 2):
        return "recovery"
    if m <= mi(2021, 12):
        return "covid"
    return "recent"


def default_event(loan_id, definition, row, lm, last, L, defect_date) -> dict:
    g = lm[lm["loan_id"] == loan_id].sort_values("period")
    p0 = int(row["period"])
    before = g[(g["period"] < p0) & (g["period"] >= p0 - 12)]
    ead = row["current_upb"] if row["current_upb"] > 0 else row["removal_upb"]
    if ead is None or pd.isna(ead) or ead <= 0:
        pos = before[before["current_upb"] > 0]["current_upb"]
        ead = float(pos.iloc[-1]) if len(pos) else float(L.loc[loan_id, "upb"])
    trigger = (
        "credit_event_zbc"
        if row["zbc"] in CREDIT_EVENT_ZBC
        else "reo"
        if row["status"] == "RA"
        else "dpd90"
    )
    after = g[g["period"] > p0]
    cures = after[after["is_cure_month"]]["period"]
    cure = int(cures.iloc[0]) if len(cures) else None
    end = last.loc[loan_id]
    z = end["zbc"]
    if z in CREDIT_EVENT_ZBC and defect_date is not None:
        res = "defect_settlement"
    elif z in CREDIT_EVENT_ZBC:
        res = (
            "open"
            if end["actual_loss"] is None or pd.isna(end["actual_loss"])
            else "credit_event_loss"
        )
    elif z == 1:
        res = "paid_off"
    elif z in (16, 96):
        res = "other_exit"
    else:
        res = "cured_active" if cure is not None else "open"
    return {
        "loan_id": loan_id,
        "definition": definition,
        "vintage_year": int(L.loc[loan_id, "vintage_year"]),
        "default_period": p0,
        "default_months_on_book": int(row["months_on_book"]),
        "default_trigger": trigger,
        "ead": float(ead),
        "forbearance_before_default": bool(before["forbearance_flag"].any()),
        "cure_period": cure,
        "resolution": res,
        "resolution_period": int(end["period"])
        if res in ("defect_settlement", "credit_event_loss", "paid_off", "other_exit")
        else None,
        "defect_settlement_date": defect_date,
    }


DISPOSITION = {
    1: "paid_off",
    2: "third_party_sale",
    3: "short_sale_chargeoff",
    9: "reo_disposition",
    15: "whole_loan_sale",
}


def loss_event(e, end, loan) -> dict:
    z = int(end["zbc"])
    months = int(end["period"]) - int(e.default_period)
    comp = {
        k: 0.0 if z == 1 else float(end[k])
        for k in ["nsp", "mi_rec", "non_mi", "legal", "maint", "taxes", "misc", "total_exp", "dai"]
    }
    df = (1 + loan["rate"] / 1200) ** -months
    if z == 1:
        computed, net_rec, lgd_e, lgd_u, lgd_g = 0.0, float(e.ead), 0.0, 0.0, 0.0
    else:
        computed = (
            end["removal_upb"]
            + comp["nsp"]
            + comp["dai"]
            + comp["total_exp"]
            + comp["mi_rec"]
            + comp["non_mi"]
        )
        net_rec = -(comp["nsp"] + comp["mi_rec"] + comp["non_mi"] + comp["total_exp"])
        lgd_e = (e.ead - net_rec * df) / e.ead
        lgd_u = computed / e.ead
        lgd_g = (e.ead - (net_rec + comp["mi_rec"]) * df) / e.ead
    return {
        "loan_id": e.loan_id,
        "vintage_year": e.vintage_year,
        "default_period": e.default_period,
        "disposition_period": int(end["period"]),
        "months_to_resolution": months,
        "zero_balance_code": z,
        "disposition_type": DISPOSITION[z],
        "ltv_band": ltv_band(loan["ltv"]),
        "property_state": loan["state"],
        "note_rate_pct": loan["rate"],
        "ead": e.ead,
        "removal_upb": float(end["removal_upb"]),
        "net_sales_proceeds": comp["nsp"],
        "mi_recoveries": comp["mi_rec"],
        "non_mi_recoveries": comp["non_mi"],
        "legal_costs": comp["legal"],
        "maintenance_and_preservation_costs": comp["maint"],
        "taxes_and_insurance": comp["taxes"],
        "miscellaneous_expenses": comp["misc"],
        "total_expenses": comp["total_exp"],
        "delinquent_accrued_interest": comp["dai"],
        "freddie_actual_loss": None if z == 1 else end["actual_loss"],
        "computed_loss": round(float(computed), 2),
        "net_recovery": round(float(net_rec), 2),
        "discount_factor": df,
        "lgd_economic": lgd_e,
        "lgd_undiscounted": lgd_u,
        "lgd_gross_of_mi": lgd_g,
        "in_lgd_sample": int(e.default_period) <= CUTOFF - 36,
    }


def derive_rest(loans: pd.DataFrame, d: dict) -> None:
    lm, dim_loan = d["lm"], d["dim_loan"]
    dl = dim_loan.set_index("loan_id")
    prim = d["fct_default_events"][d["fct_default_events"]["definition"] == "primary"]
    first_def = prim.set_index("loan_id")["default_period"]
    first_def_mob = prim.set_index("loan_id")["default_months_on_book"]
    losses = d["fct_loss_events"]
    credit_losses = losses[losses["disposition_type"] != "paid_off"]

    # ---- fct_vintage_curve
    lm_v = lm.merge(dim_loan[["loan_id", "vintage_quarter", "first_payment_date"]], on="loan_id")
    loss_mob = credit_losses.merge(
        lm_v[["loan_id", "period", "months_on_book"]].rename(
            columns={"period": "disposition_period"}
        ),
        on=["loan_id", "disposition_period"],
    )
    curves = []
    for vq, g in lm_v[lm_v["months_on_book"] >= 1].groupby("vintage_quarter"):
        members = dim_loan[dim_loan["vintage_quarter"] == vq]
        n, orig = len(members), float(members["original_upb"].sum())
        last_fpd = int(members["first_payment_date"].max())
        cum_d = cum_p = 0
        cum_l = 0.0
        for mob in range(1, int(g["months_on_book"].max()) + 1):
            at = g[g["months_on_book"] == mob]
            fd = first_def_mob.reindex(at["loan_id"])
            n_at_risk = int((fd.isna() | (fd.values >= mob)).sum())
            n_def = int(at["is_first_default_month"].sum())
            n_pre = int((at["exit_type"] == "prepaid").sum())
            nl = float(
                loss_mob[
                    (loss_mob["months_on_book"] == mob)
                    & loss_mob["loan_id"].isin(members["loan_id"])
                ]["computed_loss"].sum()
            )
            cum_d, cum_p, cum_l = cum_d + n_def, cum_p + n_pre, cum_l + nl
            curves.append(
                {
                    "vintage_year": int(vq[:4]),
                    "vintage_quarter": vq,
                    "months_on_book": mob,
                    "n_loans": n,
                    "original_upb_total": orig,
                    "n_at_risk": n_at_risk,
                    "n_defaults": n_def,
                    "cum_defaults": cum_d,
                    "cum_default_rate": cum_d / n,
                    "n_prepaid": n_pre,
                    "cum_prepaid": cum_p,
                    "net_loss": nl,
                    "cum_net_loss": cum_l,
                    "cum_loss_rate": cum_l / orig,
                    "upb_outstanding": float(at["current_upb"].sum()),
                    "fully_observed": mob <= CUTOFF - last_fpd + 1,
                }
            )
    d["fct_vintage_curve"] = pd.DataFrame(curves)

    # ---- fct_roll_rates
    s = lm.sort_values(["loan_id", "period"])
    nxt = s.groupby("loan_id").shift(-1)
    frm = s[s["zbc"].isna() & s["dpd_bucket"].isin(C.ROLL_FROM) & (s["period"] < CUTOFF)].copy()
    n2 = nxt.loc[frm.index]
    frm["to_state"] = np.where(
        n2["period"].isna(),
        "missing",
        np.where(n2["exit_type"].notna(), n2["exit_type"], n2["dpd_bucket"]),
    )
    rr = (
        frm.groupby(["period", "vintage_year", "dpd_bucket", "forbearance_flag", "to_state"])
        .agg(n_loans=("loan_id", "size"), upb=("current_upb", "sum"))
        .reset_index()
    )
    rr = rr.rename(columns={"dpd_bucket": "from_bucket", "forbearance_flag": "from_forbearance"})
    rr["n_from"] = rr.groupby(["period", "vintage_year", "from_bucket", "from_forbearance"])[
        "n_loans"
    ].transform("sum")
    rr["roll_rate"] = rr["n_loans"] / rr["n_from"]
    d["fct_roll_rates"] = rr

    # ---- fct_scorecard_base
    exits = lm[lm["exit_type"].notna()].set_index("loan_id")
    naive = d["fct_default_events"][d["fct_default_events"]["definition"] == "naive"]
    naive_mob = naive.set_index("loan_id")["default_months_on_book"]
    covid_fpd = (mi(2019, 4), mi(2021, 12))  # months on book 1-12 overlap 2020-03..2021-12
    rows = []
    for r in dim_loan.itertuples():
        mob_last = int(r.last_period) - int(r.first_payment_date) + 1
        fdm = first_def_mob.get(r.loan_id)
        d12 = fdm is not None and 1 <= fdm <= 12
        ndm = naive_mob.get(r.loan_id)
        d12_naive = ndm is not None and 1 <= ndm <= 12
        ex = exits["exit_type"].get(r.loan_id)
        ex_mob = int(exits["months_on_book"].get(r.loan_id)) if ex is not None else None
        early_exit = ex is not None and ex_mob <= 12 and not d12
        reason = None
        if r.harp_flag:
            reason = "harp"
        elif r.vintage_year == 2025 or (mob_last < 12 and ex is None and not d12):
            reason = "window_incomplete"
        elif early_exit and ex == "other_exit":
            reason = "indeterminate_exit"
        y = r.vintage_year
        if y <= 2015:
            h = hashlib.md5((r.loan_id + "split-v1").encode()).hexdigest()[:2]
            base = "dev_train" if h < "b3" else "dev_test"
        elif y == 2016:
            base = "gap"
        elif y == 2025:
            base = "out_of_scope"
        elif covid_fpd[0] <= r.first_payment_date <= covid_fpd[1]:
            base = "covid"
        else:
            base = "oot"
        sample = "excluded" if reason else base
        rows.append(
            {
                "loan_id": r.loan_id,
                "vintage_year": y,
                "vintage_quarter": r.vintage_quarter,
                "sample": sample,
                "sample_before_exclusion": base,
                "exit_code_12m": r.terminal_zero_balance_code
                if reason == "indeterminate_exit"
                else None,
                "exclusion_reason": reason,
                "default_12m": None if reason else int(d12),
                "default_12m_naive": None if reason else int(d12_naive),
                "default_months_on_book": int(fdm) if fdm is not None else None,
                "prepaid_12m": bool(early_exit and ex in ("prepaid", "matured")),
                "fico": r.fico,
                "ltv_pct": r.ltv_pct,
                "cltv_pct": r.cltv_pct,
                "dti_pct": r.dti_pct,
                "mi_pct": r.mi_pct,
                "rate_spread_pct": r.rate_spread_pct,
                "note_rate_pct": r.note_rate_pct,
                "original_upb": r.original_upb,
                "original_loan_term": r.original_loan_term,
                "term_band": r.term_band,
                "loan_purpose": r.loan_purpose,
                "occupancy_status": r.occupancy_status,
                "property_type": r.property_type,
                "number_of_units": r.number_of_units,
                "channel": r.channel,
                "first_time_homebuyer": r.first_time_homebuyer,
                "super_conforming": r.super_conforming,
                "number_of_borrowers": r.number_of_borrowers,
                "property_state": r.property_state,
            }
        )
    d["fct_scorecard_base"] = pd.DataFrame(rows)

    # ---- fct_stage_inputs (quarter-end rows for loans still on book at month end)
    si = lm[(lm["period"] % 3 == 2) & lm["zbc"].isna()].copy()
    si["reporting_date"] = si["period"]
    si["note_rate_pct"] = si["loan_id"].map(dl["note_rate_pct"])
    si["ltv_band"] = si["loan_id"].map(dl["ltv_band"])
    si["property_state"] = si["loan_id"].map(dl["property_state"])
    si["modified"] = si["mod_flag"].notna()
    si["behaviour_state"] = [behaviour(r) for r in si.itertuples()]
    floors = [stage_floor(r) for r in si.itertuples()]
    si["stage_floor"] = [f[0] for f in floors]
    si["stage_floor_reason"] = [f[1] for f in floors]
    fd = si["loan_id"].map(first_def)
    complete = si["period"] + 12 <= CUTOFF
    already = fd.notna() & (fd <= si["period"])
    si["defaulted_before"] = already
    si["default_next_12m"] = pd.Series(
        (fd > si["period"]) & (fd <= si["period"] + 12), index=si.index, dtype="boolean"
    )
    si.loc[~complete | already, "default_next_12m"] = pd.NA
    ex_p = exits["period"]
    ex_t = exits["exit_type"]
    pp = si["loan_id"].map(ex_p.where(ex_t.isin(["prepaid", "matured"])))
    si["prepaid_next_12m"] = pd.Series(
        (pp > si["period"]) & (pp <= si["period"] + 12), index=si.index, dtype="boolean"
    )
    si.loc[~complete, "prepaid_next_12m"] = pd.NA
    si = si.rename(
        columns={
            "remaining": "remaining_term",
            "ib": "interest_bearing_upb",
            "nib": "non_interest_bearing_upb",
            "current_rate": "current_rate_pct",
            "bap": "assistance_plan",
            "eltv": "eltv_pct",
        }
    )
    d["fct_stage_inputs"] = si

    # ---- metrics_monthly
    act = lm[lm["zbc"].isna()]
    late30 = act["dpd_bucket"].isin(["dpd_30", "dpd_60", "dpd_90p", "reo"])
    late90 = act["dpd_bucket"].isin(["dpd_90p", "reo"])
    g = pd.DataFrame(
        {
            "n_active_loans": act.groupby("period").size(),
            "total_upb": act.groupby("period")["current_upb"].sum(),
            "n_dpd30p": act[late30].groupby("period").size(),
            "upb_dpd30p": act[late30].groupby("period")["current_upb"].sum(),
            "n_dpd90p": act[late90].groupby("period").size(),
            "upb_dpd90p": act[late90].groupby("period")["current_upb"].sum(),
            "n_at_risk_start": lm.groupby("period")["at_risk_at_start"].sum(),
            "n_new_defaults": lm.groupby("period")["is_first_default_month"].sum(),
            "n_prepaid": lm[lm["exit_type"] == "prepaid"].groupby("period").size(),
            "upb_prepaid": lm[lm["exit_type"] == "prepaid"].groupby("period")["removal_upb"].sum(),
            "n_credit_event_exits": lm[lm["exit_type"] == "credit_event"].groupby("period").size(),
            "net_loss": credit_losses.groupby("disposition_period")["computed_loss"].sum(),
        }
    ).fillna(0)
    g.index.name = "period"
    g = g.reset_index()
    for c in [
        "n_active_loans",
        "n_dpd30p",
        "n_dpd90p",
        "n_at_risk_start",
        "n_new_defaults",
        "n_prepaid",
        "n_credit_event_exits",
    ]:
        g[c] = g[c].astype(int)
    div = g["total_upb"].where(g["total_upb"] > 0)
    g["delinquency_rate_30p"] = g["upb_dpd30p"] / div
    g["delinquency_rate_90p"] = g["upb_dpd90p"] / div
    g["default_rate"] = g["n_new_defaults"] / g["n_at_risk_start"].where(g["n_at_risk_start"] > 0)
    g["loss_rate"] = g["net_loss"] / div
    d["metrics_monthly"] = g


def behaviour(r) -> str:
    if r.in_default:
        return "default"
    if r.dpd_bucket == "dpd_60" or (r.dpd_bucket == "dpd_90p" and r.default_exempt):
        return "dpd_60p"
    if r.dpd_bucket in ("dpd_30", "unknown"):
        return "dpd_30"
    return "recent_dpd" if r.recent_dpd30_12m else "clean"


def stage_floor(r) -> tuple[int, str | None]:
    if r.in_default:
        return 3, "default"
    if r.dpd_bucket in ("dpd_30", "dpd_60", "dpd_90p"):
        return 2, "dpd30_backstop"
    if r.dpd_bucket == "unknown":
        return 2, "unknown_status"
    if r.forbearance_flag:
        return 2, "forbearance"
    if r.bap in ("R", "T"):
        return 2, "assistance_plan"
    if r.cured_within_6m:
        return 2, "cure_probation"
    return 1, None


# ---------------------------------------------------------------------------------------------
# 4. Model outputs (synthetic scores and ECL; not fitted models)
# ---------------------------------------------------------------------------------------------
FACTOR = 20 / math.log(2)
OFFSET = 600 - FACTOR * math.log(50)
GRADE_EDGES = [0.001, 0.002, 0.004, 0.008, 0.016, 0.032]


def grade_of(pd12: float) -> str:
    return C.GRADES[sum(pd12 >= e for e in GRADE_EDGES)]


def model_outputs(loans, d, rng) -> None:
    sb = d["fct_scorecard_base"].set_index("loan_id")
    pd12 = 1 - (1 - loans["lp"].map(sigmoid) * 0.45) ** 12
    noisy = np.log(pd12 / (1 - pd12)) + rng.normal(0, 0.35, len(loans))
    score = np.round(OFFSET - FACTOR * noisy).astype(int)
    pd_s = 1 / (1 + np.exp((score - OFFSET) / FACTOR))
    feats = ["fico", "ltv_pct", "dti_pct", "rate_spread_pct", "occupancy_status", "loan_purpose"]
    reasons = [rng.choice(feats, 3, replace=False) for _ in range(len(loans))]
    d["loan_scores"] = pd.DataFrame(
        {
            "loan_id": loans["loan_id"],
            "sample": loans["loan_id"].map(sb["sample"]),
            "model_id": "fixture-scorecard",
            "score": score,
            "pd_12m": pd_s,
            "grade": [grade_of(p) for p in pd_s],
            "reason_1": [r[0] for r in reasons],
            "reason_2": [r[1] for r in reasons],
            "reason_3": [r[2] for r in reasons],
        }
    )
    sc = d["loan_scores"].set_index("loan_id")
    si = d["fct_stage_inputs"]
    grade = si["loan_id"].map(sc["grade"])
    p = si["loan_id"].map(sc["pd_12m"])
    stage = np.maximum(si["stage_floor"], np.where(rng.random(len(si)) < 0.02, 2, 1))
    pd_used = np.where(stage == 3, 1.0, np.where(stage == 2, np.minimum(1, p * 5), p))
    ecl = pd_used * 0.25 * si["current_upb"]
    base = pd.DataFrame(
        {
            "reporting_date": si["reporting_date"],
            "grade": grade,
            "stage": stage,
            "ead": si["current_upb"],
            "ecl": ecl,
            "reason": np.where(
                (stage == 2) & (si["stage_floor"] == 1),
                "pd_deterioration",
                si["stage_floor_reason"],
            ),
            "cured": si["defaulted_before"] & ~si["in_default"],
            "predicted_prepay": 0.08 + 0.02 * rng.random(len(si)),
            "prepaid_next_12m": si["prepaid_next_12m"],
        }
    )
    d["ecl_rows"] = base
    agg = (
        base.groupby(["reporting_date", "grade", "stage"])
        .agg(n_loans=("ead", "size"), ead=("ead", "sum"), ecl=("ecl", "sum"))
        .reset_index()
    )
    frames = []
    for scen, mult in [
        ("base", 1.0),
        ("adverse", 1.6),
        ("upside", 0.8),
        ("final", 0.6 + 0.25 * 1.6 + 0.15 * 0.8),
    ]:
        f = agg.copy()
        f["scenario"] = scen
        f["ecl"] = f["ecl"] * mult
        frames.append(f)
    ecl_results = pd.concat(frames, ignore_index=True)
    ecl_results["in_sample"] = ecl_results["reporting_date"] <= mi(2016, 12)
    d["ecl_results"] = ecl_results
    d["fct_ecl"] = ecl_results


# ---------------------------------------------------------------------------------------------
# 5. Artefacts (JSON), built from the fixture marts where that is easy
# ---------------------------------------------------------------------------------------------
def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    mid = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, mid - half), min(1.0, mid + half)


def rate_metric(k, n) -> dict:
    k, n = int(k), int(n)
    if n == 0:
        return C.metric(None, n=0, ci_method="none: no observations")
    lo, hi = wilson(k, n)
    return C.metric(k / n, lo, hi, n, "wilson_95")


def jeffreys_metric(k, n) -> dict:
    from scipy.stats import beta

    k, n = int(k), int(n)
    if n == 0:
        return C.metric(None, n=0, ci_method="none: no observations")
    lo = 0.0 if k == 0 else float(beta.ppf(0.025, k + 0.5, n - k + 0.5))
    hi = 1.0 if k == n else float(beta.ppf(0.975, k + 0.5, n - k + 0.5))
    return C.metric(k / n, lo, hi, n, "jeffreys_95")


def count_metric(v, n=None) -> dict:
    return C.metric(float(v), n=int(v if n is None else n))


def synth_metric(v, half, n) -> dict:
    return C.metric(
        float(v), float(v - half), float(v + half), int(n), "synthetic fixture interval"
    )


def envelope(name: str) -> dict:
    return {
        "schema_version": C.SCHEMA_VERSION,
        "artefact": name,
        "synthetic": True,
        "generated_at": "2026-09-23T00:00:00Z",
        "data_cutoff": str(to_date(CUTOFF)),
        "code_version": "fixture",
        "suppressed_cells": 0,
    }


def artefacts(d: dict) -> dict:
    dl, lm, vc = d["dim_loan"], d["lm"], d["fct_vintage_curve"]
    de, le, rr, sb = (
        d["fct_default_events"],
        d["fct_loss_events"],
        d["fct_roll_rates"],
        d["fct_scorecard_base"],
    )
    credit = le[le["disposition_type"] != "paid_off"]
    prim, naive = de[de["definition"] == "primary"], de[de["definition"] == "naive"]
    comparable = int(vc[vc["fully_observed"]].groupby("vintage_year")["months_on_book"].max().min())

    rr_p = rr.merge(
        pd.DataFrame({"period": range(DATA_START, CUTOFF + 1)}).assign(
            period_group=lambda x: x["period"].map(economic_period)
        ),
        on="period",
    )
    roll, cure = [], []
    for grp, g in rr_p.groupby("period_group"):
        tot = g.groupby("from_bucket")["n_loans"].sum()
        for (fb, ts), k in g.groupby(["from_bucket", "to_state"])["n_loans"].sum().items():
            roll.append(
                {
                    "period_group": grp,
                    "from_bucket": fb,
                    "to_state": ts,
                    "rate": rate_metric(k, tot[fb]),
                }
            )
        for fb in ["dpd_30", "dpd_60", "dpd_90p"]:
            k = g[(g["from_bucket"] == fb) & (g["to_state"] == "current")]["n_loans"].sum()
            cure.append(
                {"period_group": grp, "from_bucket": fb, "rate": rate_metric(k, tot.get(fb, 0))}
            )

    act = lm[lm["zbc"].isna() & (lm["period"] % 12 == 11)]
    sma = []
    for per, g in act.groupby("period"):
        total = g["current_upb"].sum()
        for cls, u in g.groupby("sma_class")["current_upb"].sum().items():
            n = int((g["sma_class"] == cls).sum())
            sma.append(
                {
                    "period": str(to_date(per)),
                    "sma_class": cls,
                    "upb": C.metric(float(u), n=n),
                    "share": C.metric(
                        float(u / total),
                        n=len(g),
                        ci_method="none: balance share of the whole book",
                    ),
                }
            )
    mm = d["metrics_monthly"]
    prev = mm["total_upb"].shift(1)
    smm = (mm["upb_prepaid"] / prev).where(prev > 0)
    prepay = [
        {
            "period": str(to_date(p)),
            "cpr": C.metric(
                float(1 - (1 - s) ** 12),
                n=int(n),
                ci_method="none: balance-weighted rate of the whole book",
            ),
        }
        for p, s, n in zip(mm["period"], smm, mm["n_active_loans"])
        if pd.notna(s) and p % 12 == 11
    ]
    drivers = []
    for band, g in dl.groupby("ltv_band"):
        k = prim["loan_id"].isin(g["loan_id"]).sum()
        loss = credit[credit["loan_id"].isin(g["loan_id"])]["computed_loss"].sum()
        drivers.append(
            {
                "dimension": "ltv_band",
                "segment": band,
                "default_rate": rate_metric(k, len(g)),
                "loss_rate": C.metric(
                    float(loss / g["original_upb"].sum()),
                    n=len(g),
                    ci_method="none: synthetic fixture",
                ),
            }
        )
    effect = []
    for y, g in sb.groupby("vintage_year"):
        ids = g["loan_id"]
        p12 = prim[prim["loan_id"].isin(ids) & (prim["default_months_on_book"].between(1, 12))]
        n12 = naive[naive["loan_id"].isin(ids) & (naive["default_months_on_book"].between(1, 12))]
        effect.append(
            {
                "vintage_year": int(y),
                "defaults_12m_primary": count_metric(len(p12), len(g)),
                "defaults_12m_naive": count_metric(len(n12), len(g)),
            }
        )
    curves = [
        {
            "vintage_year": int(r.vintage_year),
            "vintage_quarter": r.vintage_quarter,
            "months_on_book": int(r.months_on_book),
            "fully_observed": bool(r.fully_observed),
            "cum_default_rate": rate_metric(r.cum_defaults, r.n_loans),
            "cum_loss_rate": C.metric(
                float(r.cum_loss_rate), n=int(r.n_loans), ci_method="none: synthetic fixture"
            ),
        }
        for r in vc[vc["months_on_book"] % 6 == 0].itertuples()
        if r.months_on_book <= 36
    ]
    portfolio = {
        **envelope("portfolio"),
        "summary": {
            "n_loans": count_metric(len(dl)),
            "n_loan_months": count_metric(len(lm)),
            "original_upb_total": C.metric(float(dl["original_upb"].sum()), n=len(dl)),
            "n_defaults_primary": count_metric(len(prim), len(dl)),
            "n_defaults_naive": count_metric(len(naive), len(dl)),
            "net_loss_total": C.metric(float(credit["computed_loss"].sum()), n=len(credit)),
        },
        "comparable_months_on_book": comparable,
        "vintage_curves": curves,
        "roll_rates": roll,
        "roll_cure_rates": cure,
        "default_cure_rates": [
            {
                "default_year": int(y),
                "cure_12m": rate_metric(
                    (g["cure_period"] - g["default_period"] <= 12).sum(), len(g)
                ),
                "cure_ever": rate_metric(g["cure_period"].notna().sum(), len(g)),
            }
            for y, g in prim.assign(y=prim["default_period"] // 12).groupby("y")
        ],
        "sma": sma,
        "prepayment": prepay,
        "loss_drivers": drivers,
        "default_definition_effect": effect,
        "reconciliation": [
            {"rule_id": r, "n_checked": n, "n_outside_tolerance": 0, "max_abs_difference": 0.0}
            for r, n in [
                ("R1", dl["vintage_year"].nunique()),
                ("R2", dl["vintage_year"].nunique()),
                ("R3", lm["period"].nunique()),
                ("R4", dl["vintage_year"].nunique()),
                ("R7", 8 * lm["period"].nunique()),
                ("R8", 120),
            ]
        ],
        "pass_rules": [
            {"rule_id": r, "result": "pending", "evidence": "synthetic fixture"}
            for r in ["R1", "R2", "R3", "R4", "R7", "R8"]
        ],
    }

    # pd_models: shapes only. Numbers are synthetic, not a fitted scorecard.
    sc = d["loan_scores"].merge(sb[["loan_id", "default_12m", "default_12m_naive"]], on="loan_id")
    # D1a: loans modified before (or without) a primary default, against primary defaults.
    first_mod = lm[lm["mod_flag"].notna()].groupby("loan_id")["period"].min()
    first_def = prim.set_index("loan_id")["default_period"]
    mod_first = first_mod[
        first_def.reindex(first_mod.index).isna() | (first_mod < first_def.reindex(first_mod.index))
    ].index
    d1a = []
    for s, g in [("all", sb)] + list(sb.groupby("sample")):
        k = int(g["loan_id"].isin(mod_first).sum())
        n = int(g["loan_id"].isin(first_def.index).sum())
        d1a.append(
            {
                "sample": s,
                "modified_before_default": count_metric(k, len(g)),
                "primary_defaults": count_metric(n, len(g)),
                "ratio": C.metric(
                    k / n if n else None,
                    n=n,
                    ci_method="none: ratio of counts, not a proportion",
                ),
            }
        )
    samples = []
    for s, g in sb.groupby("sample"):
        k = g["default_12m"].fillna(0).sum()
        samples.append(
            {
                "sample": s,
                "vintages": sorted(int(v) for v in g["vintage_year"].unique()),
                "n_loans": count_metric(len(g)),
                "default_rate": rate_metric(k, len(g)),
            }
        )
    points = []
    for feat, bins in [
        ("fico", [(None, 680, 0), (680, 740, 22), (740, None, 41)]),
        ("ltv_pct", [(None, 80, 35), (80, 90, 20), (90, None, 8)]),
        ("dti_pct", [(None, 36, 30), (36, None, 15)]),
    ]:
        for lo, hi, pts in bins:
            points.append(
                {
                    "feature": feat,
                    "bin": f"[{lo}, {hi})",
                    "lower": lo,
                    "upper": hi,
                    "categories": [],
                    "is_missing_bin": False,
                    "woe": round((pts - 20) / 30, 3),
                    "points": pts,
                    "default_rate_dev_train": synth_metric(0.02, 0.005, 300),
                }
            )
        points.append(
            {
                "feature": feat,
                "bin": "missing",
                "lower": None,
                "upper": None,
                "categories": [],
                "is_missing_bin": True,
                "woe": -0.4,
                "points": 5,
                "default_rate_dev_train": synth_metric(0.03, 0.01, 60),
            }
        )
    points.append(
        {
            "feature": "occupancy_status",
            "bin": "P",
            "lower": None,
            "upper": None,
            "categories": ["P"],
            "is_missing_bin": False,
            "woe": 0.1,
            "points": 25,
            "default_rate_dev_train": synth_metric(0.02, 0.004, 900),
        }
    )
    points.append(
        {
            "feature": "occupancy_status",
            "bin": "other",
            "lower": None,
            "upper": None,
            "categories": ["S", "I"],
            "is_missing_bin": False,
            "woe": -0.5,
            "points": 10,
            "default_rate_dev_train": synth_metric(0.04, 0.01, 150),
        }
    )
    edges = [0.0] + GRADE_EDGES + [1.0]
    grades = []
    for i, gr in enumerate(C.GRADES):
        hi_pd, lo_pd = edges[i + 1], edges[i]
        smin = None if hi_pd >= 1 else math.ceil(OFFSET + FACTOR * math.log((1 - hi_pd) / hi_pd))
        smax = None if lo_pd <= 0 else math.floor(OFFSET + FACTOR * math.log((1 - lo_pd) / lo_pd))
        grades.append(
            {
                "grade": gr,
                "pd_low": lo_pd,
                "pd_high": hi_pd,
                "score_min": smin,
                "score_max": smax,
                "merged_into": None,
            }
        )
    calib, citl = [], []
    combos = [
        ("dev_test", "primary"),
        ("oot", "primary"),
        ("covid", "primary"),
        ("oot_and_covid", "primary"),
        ("oot", "naive"),
    ]
    for s, definition in combos:
        g = sc[sc["sample"].isin(["oot", "covid"] if s == "oot_and_covid" else [s])]
        target = "default_12m" if definition == "primary" else "default_12m_naive"
        for gr, gg in g.groupby("grade"):
            k, n = int(gg[target].sum()), len(gg)
            calib.append(
                {
                    "sample": s,
                    "definition": definition,
                    "grade": gr,
                    "n": n,
                    "mean_pd": float(gg["pd_12m"].mean()),
                    "realised_rate": jeffreys_metric(k, n),
                    "result": "INSUFFICIENT" if k < 20 else "FAIL",
                }
            )
        mean_pd = float(g["pd_12m"].mean())
        real = jeffreys_metric(g[target].sum(), len(g))
        citl.append(
            {
                "sample": s,
                "definition": definition,
                "mean_pd": mean_pd,
                "realised_rate": real,
                "ratio": C.metric(
                    real["value"] / mean_pd,
                    real["ci_low"] / mean_pd,
                    real["ci_high"] / mean_pd,
                    len(g),
                    "jeffreys_95_over_mean_pd",
                ),
            }
        )
    disc = [
        {
            "sample": s,
            "definition": definition,
            "model": "champion",
            "auc": synth_metric(0.78, 0.03, 500),
            "gini": synth_metric(0.56, 0.06, 500),
            "ks": synth_metric(0.42, 0.05, 500),
        }
        for s, definition in [
            ("dev_train", "primary"),
            ("dev_test", "primary"),
            ("oot", "primary"),
            ("covid", "primary"),
            ("oot_and_covid", "primary"),
            ("dev_test", "naive"),
            ("oot", "naive"),
        ]
    ]
    feats = [
        {
            "feature": f,
            "iv": synth_metric(iv, 0.02, 2000),
            "selected": sel,
            "drop_reason": reason,
            "coefficient": coef,
        }
        for f, iv, sel, reason, coef in [
            ("fico", 0.45, True, None, -0.9),
            ("ltv_pct", 0.2, True, None, -0.8),
            ("dti_pct", 0.08, True, None, -0.7),
            ("occupancy_status", 0.05, True, None, -0.6),
            ("cltv_pct", 0.19, False, "correlation above 0.7 with ltv_pct", None),
            ("channel", 0.01, False, "IV below 0.02", None),
        ]
    ]
    rules = [
        {"rule_id": r, "result": "pending", "evidence": "synthetic fixture"}
        for r in ["D1a", "S1", "S2", "S3", "S4a", "S4b", "S5", "C1"]
    ]
    pd_models = {
        **envelope("pd_models"),
        "model_id": "fixture-scorecard",
        "samples": samples,
        "exclusions": [
            {
                "reason": r,
                "sample_before_exclusion": s,
                "zero_balance_code": None if pd.isna(z) else int(z),
                "n_loans": count_metric(len(g)),
            }
            for (r, s, z), g in sb[sb["exclusion_reason"].notna()].groupby(
                ["exclusion_reason", "sample_before_exclusion", "exit_code_12m"], dropna=False
            )
        ],
        "d1a": d1a,
        "scaling": {
            "base_score": 600,
            "base_odds": 50.0,
            "pdo": 20,
            "factor": FACTOR,
            "offset": OFFSET,
            "intercept": -4.5,
            "pd_label": "12-month PD, development average (synthetic fixture)",
        },
        "features": feats,
        "points_table": points,
        "grades": grades,
        "discrimination": disc,
        "calibration": calib,
        "calibration_in_the_large": citl,
        "gini_drop": [
            {
                "definition": "primary",
                "relative": synth_metric(0.08, 0.05, 500),
                "absolute": synth_metric(0.045, 0.03, 500),
                "rag": "green",
            },
            {
                "definition": "naive",
                "relative": synth_metric(0.12, 0.05, 500),
                "absolute": synth_metric(0.065, 0.03, 500),
                "rag": "amber",
            },
        ],
        "fairness_sensitivity": [
            {
                "feature": f,
                "in_model": in_model,
                "iv": synth_metric(iv, 0.01, 2000),
                "gini_dev_test_with": synth_metric(0.57, 0.06, 500),
                "gini_dev_test_without": synth_metric(0.56, 0.06, 500),
            }
            for f, in_model, iv in [
                ("number_of_borrowers", False, 0.06),
                ("first_time_homebuyer", True, 0.03),
            ]
        ],
        "challenger": {
            "status": "not_run",
            "confirm_passed": None,
            "delta_gini_oot": None,
            "promotion_recommended": None,
            "criteria": [],
            "shap_global": [],
        },
        "oot_scoring": {"calls": 0, "scored_at": None},
        "pass_rules": rules,
    }

    monitoring = {
        **envelope("monitoring"),
        "model_id": "fixture-scorecard",
        "thresholds": {"stable_below": 0.10, "red_above": 0.25},
        "score_psi": [
            {
                "comparison": "dev_train_vs_oot",
                "n_bins": 10,
                "psi": synth_metric(0.14, 0.03, 1000),
                "rag": "amber",
            }
        ]
        + [
            {
                "comparison": f"dev_train_vs_{y}",
                "n_bins": 10,
                "psi": synth_metric(0.05 + 0.01 * i, 0.02, 150),
                "rag": "green",
            }
            for i, y in enumerate(range(2016, 2025))
        ],
        "csi": [
            {
                "feature": f,
                "comparison": "dev_train_vs_oot",
                "csi": synth_metric(v, 0.02, 1000),
                "rag": rag,
            }
            for f, v, rag in [
                ("fico", 0.18, "amber"),
                ("ltv_pct", 0.04, "green"),
                ("dti_pct", 0.27, "red"),
            ]
        ],
    }

    ls = le[le["in_lgd_sample"]]
    # D8 sensitivities on the 36-month sample.
    base_lgd = float(ls["lgd_economic"].mean())
    old = prim[prim["default_period"] <= CUTOFF - 36]
    zero = old["resolution"].eq("cured_active") | (
        old["resolution"].eq("other_exit")
        & old["loan_id"].map(dl.set_index("loan_id")["terminal_zero_balance_code"]).eq(16)
    )
    with_zero = pd.concat([ls["lgd_economic"], pd.Series(0.0, index=range(int(zero.sum())))])
    n_open = int(old["resolution"].eq("open").sum())
    p90 = ls.groupby("ltv_band")["lgd_economic"].quantile(0.9)
    open_ltv = old[old["resolution"].eq("open")]["loan_id"].map(dl.set_index("loan_id")["ltv_band"])
    with_open = pd.concat([ls["lgd_economic"], open_ltv.map(p90).fillna(p90.max())])
    run_open = n_open > 0.1 * (len(ls) + n_open)
    sensitivities = [
        {
            "name": "zero_loss_exclusions",
            "status": "run",
            "lgd_economic": synth_metric(float(with_zero.mean()), 0.02, len(with_zero)),
            "delta_vs_primary": float(with_zero.mean()) - base_lgd,
        },
        {
            "name": "open_workouts_p90",
            "status": "run" if run_open else "not_needed",
            "lgd_economic": synth_metric(float(with_open.mean()), 0.02, len(with_open))
            if run_open
            else None,
            "delta_vs_primary": float(with_open.mean()) - base_lgd if run_open else None,
        },
    ]

    def lgd_row(dim, seg, g):
        n = len(g)
        out = {"dimension": dim, "segment": seg}
        for col in ["lgd_economic", "lgd_gross_of_mi", "lgd_undiscounted"]:
            m = float(g[col].mean()) if n else None
            half = 1.96 * float(g[col].std(ddof=1)) / math.sqrt(n) if n > 1 else None
            out[col] = (
                C.metric(m, m - half, m + half, n, "normal_approx_fixture")
                if half
                else C.metric(m, n=n, ci_method="none: fewer than two defaults")
            )
        return out

    segs = [lgd_row("overall", "all", ls)] + [
        lgd_row("ltv_band", b, g) for b, g in ls.groupby("ltv_band")
    ]
    lgd_ead = {
        **envelope("lgd_ead"),
        "ead": {
            "ccf_applied": False,
            "mean_ead": synth_metric(float(prim["ead"].mean()), 5000, len(prim)),
        },
        "lgd_segments": segs,
        "downturn_lgd": [
            {"ltv_band": s["segment"], "lgd_gross_of_mi": s["lgd_gross_of_mi"]} for s in segs[1:]
        ],
        "resolution_mix": [
            {
                "default_year": int(y),
                "resolution": res,
                "n_defaults": int((g["resolution"] == res).sum()),
                "share": rate_metric((g["resolution"] == res).sum(), len(g)),
            }
            for y, g in prim.assign(y=prim["default_period"] // 12).groupby("y")
            for res in C.RESOLUTIONS
            if (g["resolution"] == res).any()
        ],
        "sensitivities": sensitivities,
        "lgd_distribution": {
            "share_above_1": rate_metric((ls["lgd_economic"] > 1).sum(), len(ls)),
            "share_below_0": rate_metric((ls["lgd_economic"] < 0).sum(), len(ls)),
        },
        "reconciliation": {
            "computed_vs_actual_within_1usd": rate_metric(
                (
                    (credit["computed_loss"] - pd.to_numeric(credit["freddie_actual_loss"])).abs()
                    <= 1
                ).sum(),
                credit["freddie_actual_loss"].notna().sum(),
            ),
            "expenses_within_1usd": rate_metric(len(credit), len(credit)),
        },
        "lgd_model": {"status": "not_run", "used_in_ecl": False, "delta_mae": None},
        "pass_rules": [
            {"rule_id": r, "result": "pending", "evidence": "synthetic fixture"}
            for r in ["R5", "R6", "G2"]
        ],
    }

    er = d["ecl_results"]
    fin = er[(er["scenario"] == "final") & (er["reporting_date"] % 12 == 11)]
    by_date = [
        {
            "reporting_date": str(to_date(r.reporting_date)),
            "in_sample": bool(r.in_sample),
            "stage": str(int(r.stage)),
            "grade": r.grade,
            "n_loans": int(r.n_loans),
            "ead": C.metric(float(r.ead), n=int(r.n_loans)),
            "ecl": synth_metric(float(r.ecl), float(r.ecl) * 0.1, int(r.n_loans)),
            "coverage": synth_metric(
                float(r.ecl / r.ead), float(r.ecl / r.ead) * 0.1, int(r.n_loans)
            ),
        }
        for r in fin.itertuples()
    ]
    totals = (
        er[er["reporting_date"] % 12 == 11]
        .groupby(["reporting_date", "scenario"])[["ecl", "n_loans"]]
        .sum()
    )
    scen = [
        {
            "reporting_date": str(to_date(p)),
            "scenario": s,
            "ecl": synth_metric(float(r.ecl), float(r.ecl) * 0.1, int(r.n_loans)),
        }
        for (p, s), r in totals.iterrows()
    ]
    rows = d["ecl_rows"]
    term = []
    for i, gr in enumerate(C.GRADES):
        cum = 0.0
        for yr in range(1, 11):
            marg = 0.0005 * (2**i) * (1.3 if yr in (3, 4, 5) else 1.0) * (1 - cum)
            cum += marg
            term.append(
                {
                    "grade": gr,
                    "year": yr,
                    "marginal_pd": synth_metric(marg, marg * 0.2, 500),
                    "cumulative_pd": synth_metric(cum, cum * 0.2, 500),
                }
            )
    backtest = []
    for y in range(2016, 2025):
        for i, gr in enumerate(C.GRADES):
            p = 0.0006 * (2**i)
            backtest.append(
                {
                    "reporting_date": f"{y}-12-01",
                    "grade": gr,
                    "n": 400,
                    "predicted_pd": p,
                    "realised_rate": synth_metric(p * 0.8, p * 0.5, 400),
                    "binomial_low": p * 0.3,
                    "binomial_high": p * 1.9,
                    "vasicek_low": p * 0.1,
                    "vasicek_high": p * 3.5,
                    "rag": "green",
                    "covid_affected": y in (2019, 2020),
                }
            )
    migration = [
        {
            "from_date": "2023-12-01",
            "to_date": "2024-12-01",
            "from_stage": a,
            "to_stage": b,
            "n": n,
            "share": rate_metric(n, tot),
        }
        for a, tot, row in [
            ("1", 1000, [("1", 900), ("2", 30), ("3", 5), ("exited", 65)]),
            ("2", 60, [("1", 25), ("2", 20), ("3", 10), ("exited", 5)]),
            ("3", 20, [("2", 4), ("3", 10), ("exited", 6)]),
        ]
        for b, n in row
    ]
    ecl = {
        **envelope("ecl"),
        "scenarios": {
            "used": True,
            "source": "synthetic fixture path",
            "weights": [
                {"scenario": "base", "weight": 0.6},
                {"scenario": "adverse", "weight": 0.25},
                {"scenario": "upside", "weight": 0.15},
            ],
        },
        "sicr": {"ratio_threshold": 2.0, "absolute_threshold": 0.002},
        "by_date": by_date,
        "scenario_totals": scen,
        "stage_migration": migration,
        "pd_term_structure": term,
        "backtest": backtest,
        "prepayment_backtest": [
            {
                "reporting_date": str(to_date(p)),
                "grade": gr,
                "n": len(g),
                "predicted_rate": float(g["predicted_prepay"].mean()),
                "realised_rate": rate_metric(g["prepaid_next_12m"].astype(bool).sum(), len(g)),
            }
            for (p, gr), g in rows[
                (rows["reporting_date"] % 12 == 11)
                & (rows["reporting_date"] >= mi(2016, 12))
                & rows["prepaid_next_12m"].notna()
            ].groupby(["reporting_date", "grade"])
        ],
        "stage2_drivers": [
            {
                "reporting_date": str(to_date(p)),
                "reason": reason,
                "n_loans": len(g),
                "share_of_stage2": rate_metric(len(g), n2),
            }
            for p, s2 in rows[(rows["stage"] == 2) & (rows["reporting_date"] % 12 == 11)].groupby(
                "reporting_date"
            )
            for n2 in [len(s2)]
            for reason, g in s2.groupby("reason")
        ],
        "cured_population": [
            {
                "reporting_date": str(to_date(p)),
                "n_loans": len(g),
                "ead": C.metric(float(g["ead"].sum()), n=len(g)),
                "ecl": synth_metric(float(g["ecl"].sum()), float(g["ecl"].sum()) * 0.2, len(g)),
            }
            for p, g in rows[rows["cured"] & (rows["reporting_date"] % 12 == 11)].groupby(
                "reporting_date"
            )
        ],
        "hazard_inputs": {
            "market_rate_carried_forward_months": int(
                d["dim_date"]["market_rate_carried_forward"].sum()
            ),
            "loan_months_without_market_rate": int(
                ((lm["months_on_book"] >= 1) & lm["rate_incentive_pct"].isna()).sum()
            ),
        },
        "pass_rules": [
            {"rule_id": r, "result": "pending", "evidence": "synthetic fixture"}
            for r in ["E3", "E4a", "E4b", "E4c"]
        ],
    }

    capital_rows = []
    for i, gr in enumerate(C.GRADES):
        pdv, lgd, ead = max(0.0005, 0.0008 * 2**i), 0.3, 5e6 / (i + 1)
        k = _basel_k(pdv, lgd)
        capital_rows.append(
            {
                "grade": gr,
                "n_loans": 100,
                "ead": C.metric(ead, n=100),
                "pd": synth_metric(pdv, pdv * 0.2, 100),
                "lgd": synth_metric(lgd, 0.05, 100),
                "k": C.metric(k, n=100, ci_method="none: formula of pd and lgd"),
                "rwa": C.metric(12.5 * k * ead, n=100, ci_method="none: formula of pd and lgd"),
                "capital": C.metric(k * ead, n=100, ci_method="none: formula of pd and lgd"),
                "ecl": synth_metric(pdv * lgd * ead, pdv * lgd * ead * 0.1, 100),
            }
        )
    capital = {
        **envelope("capital"),
        "status": "run",
        "parameters": {
            "correlation": 0.15,
            "confidence": 0.999,
            "pd_floor": 0.0005,
            "lgd_floor": 0.05,
            "lgd_basis": "downturn_gross_of_mi",
        },
        "reporting_date": "2025-12-01",
        "by_grade": capital_rows,
        "totals": {
            k: C.metric(
                sum(r[k]["value"] for r in capital_rows),
                n=700,
                ci_method="none: sum of grade values",
            )
            for k in ["ead", "rwa", "capital", "ecl"]
        },
        "limits": [
            "Illustrative only; not a regulatory capital calculation.",
            "Synthetic fixture values.",
        ],
    }
    return {
        "portfolio": portfolio,
        "pd_models": pd_models,
        "monitoring": monitoring,
        "lgd_ead": lgd_ead,
        "ecl": ecl,
        "capital": capital,
    }


def _basel_k(pd_: float, lgd: float, r: float = 0.15) -> float:
    from statistics import NormalDist

    n = NormalDist()
    return (
        lgd * n.cdf(n.inv_cdf(pd_) / math.sqrt(1 - r) + math.sqrt(r / (1 - r)) * n.inv_cdf(0.999))
        - pd_ * lgd
    )


# ---------------------------------------------------------------------------------------------
# 6. Writers
# ---------------------------------------------------------------------------------------------
ARROW = {
    "string": pa.string(),
    "int": pa.int64(),
    "float": pa.float64(),
    "bool": pa.bool_(),
    "date": pa.date32(),
}


def _clean(v, typ):
    if v is None or v is pd.NA or (isinstance(v, float) and math.isnan(v)):
        return None
    return {
        "int": int,
        "float": float,
        "bool": bool,
        "string": str,
        "date": lambda x: to_date(int(x)),
    }[typ](v)


def write_parquet(df: pd.DataFrame, spec: dict, path: Path) -> None:
    cols = spec["columns"]
    arrays = [
        pa.array([_clean(v, typ) for v in df[c].tolist()], ARROW[typ])
        for c, (typ, *_r) in cols.items()
    ]
    schema = pa.schema(
        [(c, ARROW[typ]) for c, (typ, *_r) in cols.items()], metadata={C.SYNTHETIC_KEY: b"true"}
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_arrays(arrays, schema=schema), path)


def raw_value(v, kind: str = "") -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)) or v is pd.NA:
        return ""
    if kind == "date":
        return to_date(int(v)).strftime("%Y%m")
    return str(v)


def write_raw(loans: pd.DataFrame, panel: pd.DataFrame, rng) -> None:
    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    ends = panel.groupby("loan_id").tail(1).set_index("loan_id")
    forborne = set(panel[panel["bap"].notna() | panel["disaster"].notna()]["loan_id"])
    modified = set(panel[panel["mod_flag"].notna()]["loan_id"])
    settled = set(panel[panel["defect_date"].notna()]["loan_id"])
    for y in RAW_VINTAGES:
        pool = loans[loans["vintage_year"] == y]["loan_id"].tolist()
        z = ends["zbc"].reindex(pool)
        pick = (
            [i for i in pool if i in settled][:1]
            + [i for i in pool if z[i] in CREDIT_EVENT_ZBC and i not in settled][:3]
            + [i for i in pool if i in forborne][:2]
            + [i for i in pool if i in modified][:1]
            + [i for i in pool if z[i] in (16, 96)][:1]
        )
        pick += [i for i in pool if i not in pick][: RAW_LOANS_PER_VINTAGE - len(pick)]
        sel = loans[loans["loan_id"].isin(pick)]
        orig_lines = []
        for L in sel.itertuples():
            v = {
                "classic_fico": 9999 if L.fico is None or pd.isna(L.fico) else int(L.fico),
                "first_payment_date": raw_value(L.fpd, "date"),
                "first_time_homebuyer_indicator": L.fthb,
                "maturity_date": raw_value(L.fpd + L.term - 1, "date"),
                "msa_or_md": "",
                "mi_percent": int(L.mi),
                "number_of_units": int(L.units),
                "occupancy_status": L.occ,
                "cltv": int(L.cltv),
                "dti": 999 if L.dti is None or pd.isna(L.dti) else int(L.dti),
                "original_upb": int(L.upb),
                "ltv": int(L.ltv),
                "original_interest_rate": L.rate,
                "channel": L.channel,
                "prepayment_penalty_indicator": "N",
                "amortization_type": "FRM",
                "property_state": L.state,
                "property_type": L.ptype,
                "postal_code": "99900",
                "loan_id": L.loan_id,
                "loan_purpose": L.purpose,
                "original_loan_term": int(L.term),
                "number_of_borrowers": int(L.borrowers),
                "seller_name": "Synthetic Seller",
                "super_conforming_flag": "Y" if L.super else "",
                "pre_harp_loan_sequence_number": f"F00Q1S{int(L.Index):06d}" if L.harp else "",
                "special_eligibility_program": "9",
                "harp_indicator": "Y" if L.harp else "N",
                "property_valuation_method": 9,
                "interest_only_indicator": "N",
                "vantage_score_4_0": 9999,
            }
            orig_lines.append("|".join(str(v[n]) for _, n, _ in build_parquet.ORIGINATION_COLUMNS))
        perf_lines = []
        for r in panel[panel["loan_id"].isin(pick)].itertuples():
            v = {
                "loan_id": r.loan_id,
                "period": raw_value(r.period, "date"),
                "current_actual_upb": f"{r.current_upb:.2f}",
                "current_loan_delinquency_status": r.status,
                "loan_age": r.loan_age,
                "remaining_months_to_legal_maturity": r.remaining,
                "underwriting_defect_settlement_date": raw_value(r.defect_date, "date"),
                "modification_flag": raw_value(r.mod_flag),
                "zero_balance_code": "" if pd.isna(r.zbc) else f"{int(r.zbc):02d}",
                "zero_balance_effective_date": raw_value(r.zb_date, "date"),
                "current_interest_rate": r.current_rate,
                "current_non_interest_bearing_upb": f"{r.nib:.2f}",
                "due_date_of_last_paid_installment": "",
                "mi_recoveries": raw_value(r.mi_rec),
                "net_sales_proceeds": raw_value(r.nsp),
                "non_mi_recoveries": raw_value(r.non_mi),
                "total_expenses": raw_value(r.total_exp),
                "legal_costs": raw_value(r.legal),
                "maintenance_and_preservation_costs": raw_value(r.maint),
                "taxes_and_insurance": raw_value(r.taxes),
                "miscellaneous_expenses": raw_value(r.misc),
                "actual_loss": raw_value(r.actual_loss),
                "cumulative_modification_costs": "0.00",
                "interest_rate_step_indicator": "N" if r.mod_flag else "",
                "payment_deferral_flag": raw_value(r.deferral),
                "eltv": 999 if r.eltv is None or pd.isna(r.eltv) else int(r.eltv),
                "zero_balance_removal_upb": raw_value(r.removal_upb),
                "delinquent_accrued_interest": raw_value(r.dai),
                "delinquency_due_to_disaster": raw_value(r.disaster),
                "borrower_assistance_plan": raw_value(r.bap),
                "current_period_modification_costs": "",
                "current_interest_bearing_upb": f"{r.ib:.2f}",
                "mortgage_insurance_cancellation_indicator": "",
                "servicer_name": "Synthetic Servicer",
                "bankruptcy_cramdown_costs": "",
            }
            perf_lines.append("|".join(str(v[n]) for _, n, _ in build_parquet.PERFORMANCE_COLUMNS))
        (raw / f"sample_orig_{y}.txt").write_text("\n".join(orig_lines) + "\n", encoding="utf-8")
        (raw / f"sample_perf_{y}.txt").write_text("\n".join(perf_lines) + "\n", encoding="utf-8")


def main() -> None:
    rng = np.random.default_rng(SEED)
    loans = make_loans(rng)
    panel_rows = []
    for L in loans.to_dict("records"):
        panel_rows.extend(simulate(L, rng))
    panel = pd.DataFrame(panel_rows)
    for col in [
        "legal",
        "maint",
        "taxes",
        "misc",
        "nsp",
        "dai",
        "mi_rec",
        "non_mi",
        "total_exp",
        "actual_loss",
    ]:
        if col not in panel:
            panel[col] = None
    panel = panel.astype({"actual_loss": "object"})
    panel["actual_loss"] = panel["actual_loss"].where(panel["actual_loss"].notna(), None)
    # Some credit-event exits are settled as underwriting or servicing defects: the settlement
    # date is set and Freddie Mac reports no actual loss (D8, resolution defect_settlement).
    settled = (
        panel["zbc"].isin(list(CREDIT_EVENT_ZBC))
        & panel["actual_loss"].notna()
        & panel["loan_id"].map(lambda i: int(hashlib.md5(i.encode()).hexdigest()[:2], 16) < 24)
    )
    panel["defect_date"] = panel["period"].astype(object).where(settled, None)
    panel.loc[settled, "actual_loss"] = None

    d = derive(loans, panel)
    derive_rest(loans, d)
    model_outputs(loans, d, rng)

    for name, spec in C.MARTS.items():
        write_parquet(d[name], spec, OUT / "marts" / f"{name}.parquet")
    for name, spec in C.MODEL_OUTPUTS.items():
        write_parquet(d[name], spec, OUT / "models_out" / f"{name}.parquet")
    art_dir = OUT / "artefacts"
    art_dir.mkdir(parents=True, exist_ok=True)
    for name, obj in artefacts(d).items():
        obj["suppressed_cells"] = C.suppress_small_cells(obj)
        (art_dir / f"{name}.json").write_text(json.dumps(obj, indent=1) + "\n", encoding="utf-8")
    write_raw(loans, panel, rng)
    print(f"{len(loans)} synthetic loans, {len(panel)} synthetic loan-months -> {OUT}")


if __name__ == "__main__":
    main()
