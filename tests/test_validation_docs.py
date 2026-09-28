"""Every number in the validation report, issue ledger and committee memo must come from
artefacts/.

Two checks:
1. Headline figures are formatted from their exact artefact keys and must appear verbatim.
2. Every other number in the three docs must match some artefact value (or a sum/count derived
   from one, listed in `derived()`), within the rounding of the digits written, allowing for
   %, bp, $m and $bn scaling. Skipped: dates and years, bare integers under 10 (small counts
   such as "six of seven grades") and digits inside identifiers (V-05, S4b, PD12, ab76eef).
   A number with few significant digits can match by chance; check 1 is what pins the headlines.
"""

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
ARTEFACTS = ROOT / "artefacts"
DOCS = [ROOT / "docs" / f for f in ("VALIDATION_REPORT.md", "VALIDATION_ISSUES.md",
                                    "COMMITTEE_MEMO.md")]
SCALES = (1, 100, 1e4, 1e-3, 1e-6, 1e-9)
DOC_NUMBER = re.compile(
    r"(?<![\w./])(?<!\w-)(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?(?:m|bn|bp|x)?(?![\w\-]|\.\d)"
)
DATE = re.compile(r"\b(?:19|20)\d\d(?:-\d\d){1,2}\b|\b(?:19|20)\d\d-(?:19|20)?\d\d\b")
ANY_NUMBER = re.compile(r"\d+(?:\.\d+)?(?:e-?\d+)?")


def load(name):
    return json.loads((ARTEFACTS / f"{name}.json").read_text(encoding="utf-8"))


def walk(obj):
    if isinstance(obj, dict):
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v)
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        yield abs(float(obj))
    elif isinstance(obj, str):
        yield from (float(x) for x in ANY_NUMBER.findall(obj))


def derived(ecl):
    """Totals the docs quote that no artefact stores directly."""
    out = []
    stage_sums = Counter()
    for r in ecl["by_date"]:
        d = r["reporting_date"]
        for key, val in (("ecl", r["ecl"]["value"]), ("ead", r["ead"]["value"]),
                         ("n", r["n_loans"])):
            stage_sums[(d, r["stage"], key)] += val
            stage_sums[(d, "all", key)] += val
    out += stage_sums.values()
    counted = [b for b in ecl["backtest"] if not b["covid_affected"]]
    n = sum(b["n"] for b in counted)
    out += [len(counted), n, *Counter(b["rag"] for b in counted).values(),
            sum(b["predicted_pd"] > b["realised_rate"]["value"] for b in counted),
            sum(b["predicted_pd"] * b["n"] for b in counted) / n,
            sum(b["realised_rate"]["value"] * b["n"] for b in counted) / n]
    return out


@pytest.fixture(scope="module")
def artefacts():
    return {n: load(n) for n in ("pd_models", "ecl", "lgd_ead", "capital", "monitoring",
                                 "portfolio")}


@pytest.fixture(scope="module")
def pool(artefacts):
    values = [v for a in artefacts.values() for v in walk(a)] + derived(artefacts["ecl"])
    return np.unique(np.array(values, dtype=float))


def doc_numbers(text):
    text = DATE.sub(" ", text)
    for m in DOC_NUMBER.finditer(text):
        whole, frac = m.group(1).replace(",", ""), m.group(2) or ""
        x = float(whole + frac)
        if not frac and (x < 10 or (1990 <= x <= 2030 and "," not in m.group(1))):
            continue
        yield m.group(0), x, len(frac) - 1 if frac else 0


def in_pool(pool, x, decimals):
    tol = 0.5 * 10 ** -decimals + 1e-9 * x
    for s in SCALES:
        lo, hi = (x - tol) / s, (x + tol) / s
        i = np.searchsorted(pool, lo)
        if i < len(pool) and pool[i] <= hi:
            return True
    return False


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: p.name)
def test_every_number_is_in_the_artefacts(doc, pool):
    missing = [raw for raw, x, d in doc_numbers(doc.read_text(encoding="utf-8"))
               if not in_pool(pool, x, d)]
    assert not missing, f"{doc.name}: numbers not found in artefacts/: {missing}"


def fmt(v, d):
    """Regex for 'value [low, high]' as written in the docs; a % or m unit may follow the value."""
    val, lo, hi = (re.escape(f"{v[k]:.{d}f}") for k in ("value", "ci_low", "ci_high"))
    return rf"{val}[%m]?\s+\[{lo}, {hi}\]"


def test_headline_numbers_match_their_keys(artefacts):
    pd_, ecl, mon = artefacts["pd_models"], artefacts["ecl"], artefacts["monitoring"]
    gini = {(r["sample"], r["model"]): r["gini"] for r in pd_["discrimination"]
            if r["definition"] == "primary"}
    citl = {r["sample"]: r["ratio"] for r in pd_["calibration_in_the_large"]
            if r["definition"] == "primary"}
    final = next(s["ecl"] for s in ecl["scenario_totals"]
                 if s["reporting_date"] == "2026-03-01" and s["scenario"] == "final")
    ecl_m = {k: final[k] / 1e6 for k in ("value", "ci_low", "ci_high")}
    psi = next(r["psi"] for r in mon["score_psi"] if r["comparison"] == "dev_train_vs_oot")
    s2 = next(r for r in ecl["stage2_drivers"] if r["reporting_date"] == "2026-03-01"
              and r["reason"] == "pd_deterioration")["share_of_stage2"]
    s2_pct = {k: s2[k] * 100 for k in ("value", "ci_low", "ci_high")}
    headlines = {
        "oot Gini": fmt(gini[("oot", "champion")], 4),
        "oot calibration ratio": fmt(citl["oot"], 3),
        "score PSI": fmt(psi, 4),
        "challenger gain": fmt(pd_["challenger"]["delta_gini_oot"], 4),
        "ECL 2026-03 $m": fmt(ecl_m, 1),
        "stage 2 from PD rule %": fmt(s2_pct, 1),
    }
    report, _, memo = (" ".join(p.read_text(encoding="utf-8").split()) for p in DOCS)
    for label, pattern in headlines.items():
        assert re.search(pattern, report), f"{label}: {pattern} not in the report"
        assert re.search(pattern, memo), f"{label}: {pattern} not in the memo"
