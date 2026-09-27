"""Site checks that need no browser: plain-language rule names, and the calculator against the
Python scorecard."""

import json
import math
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_every_published_rule_has_a_plain_name():
    rules_ts = (ROOT / "web" / "src" / "lib" / "rules.ts").read_text(encoding="utf-8")
    block = rules_ts.split("RULE_NAMES", 1)[1].split("};", 1)[0]
    named = set(re.findall(r"^\s*([A-Z]\d+[a-z]?):", block, flags=re.M))
    published = set()
    paths = [*(ROOT / "tests" / "fixtures" / "artefacts").glob("*.json")]
    paths += [*(ROOT / "artefacts").glob("*.json")]
    for path in paths:
        for rule in json.loads(path.read_text(encoding="utf-8")).get("pass_rules", []):
            published.add(rule.get("rule_id") or rule.get("id"))
    assert published, "no pass rules found in the artefacts"
    assert published <= named, f"rules without a plain name: {sorted(published - named)}"


# ---------------------------------------------------------------------------------------------
# The site's calculator (web/src/lib/calculator.ts) against the Python scorecard
# ---------------------------------------------------------------------------------------------
def _model_from_points_table(art: dict) -> dict:
    """The scorecard as scorecard.score() takes it, rebuilt from the published points table."""
    binnings = {}
    for f in dict.fromkeys(b["feature"] for b in art["points_table"]):
        bins = [dict(b) for b in art["points_table"] if b["feature"] == f]
        numeric = any(not b["is_missing_bin"] and not b["categories"] for b in bins)
        splits = [b["upper"] for b in bins if not b["is_missing_bin"]][:-1] if numeric else []
        binnings[f] = {"numeric": numeric, "splits": splits, "bins": bins}
    for b in (b for bs in binnings.values() for b in bs["bins"]):
        b["is_other_bin"] = False  # the calculator only offers published categories
    return {
        "model_id": art["model_id"],
        "features": list(binnings),
        "binnings": binnings,
        "grades": art["grades"],
    }


def _synthetic_loans(model: dict, n: int) -> list[dict]:
    """Seeded attribute combinations: bin edges, just either side of them, in-range values,
    every published category and missing values."""
    rng = random.Random(20260927)
    loans = []
    for i in range(n):
        loan = {}
        for f in model["features"]:
            b = model["binnings"][f]
            if rng.random() < 0.12:
                loan[f] = None
            elif b["numeric"]:
                s = b["splits"]
                edge = rng.choice(s)
                lo, hi = s[0] - 3 * abs(s[0]) - 1, s[-1] + 3 * abs(s[-1]) + 1
                loan[f] = rng.choice(
                    [edge, edge - 0.001, edge + 0.001, round(rng.uniform(lo, hi), 2)]
                )
            else:
                cats = [c for bin_ in b["bins"] for c in bin_["categories"]]
                loan[f] = rng.choice(cats)
        loans.append(loan)
    return loans


def test_calculator_matches_python_scorecard():
    """Score, grade, PD and reason codes from the site's calculator equal scorecard.score() on 60
    synthetic attribute combinations. Uses the fitted model when it is on disk, else the model
    rebuilt from the published points table (the published table is the whole model)."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    sys.path.insert(0, str(ROOT))
    from config import VINTAGE_DATA_ROOT
    from models.pd import scorecard as sc

    art = json.loads((ROOT / "artefacts" / "pd_models.json").read_text(encoding="utf-8"))
    fitted = Path(VINTAGE_DATA_ROOT) / "models_out" / "scorecard.json"
    if (
        fitted.exists()
        and json.loads(fitted.read_text(encoding="utf-8"))["model_id"] == art["model_id"]
    ):
        model = json.loads(fitted.read_text(encoding="utf-8"))
    else:
        model = _model_from_points_table(art)
    loans = _synthetic_loans(model, 60)

    df = pd.DataFrame(loans, columns=model["features"])
    df["loan_id"] = [f"t{i}" for i in range(len(df))]
    df["sample"] = "dev_test"
    py = sc.score(model, df)

    script = (
        "import { readFileSync } from 'node:fs';"
        "import { pathToFileURL } from 'node:url';"
        "const [calc, art, loans] = process.argv.slice(1);"
        "const { calculate } = await import(pathToFileURL(calc).href);"
        "const model = JSON.parse(readFileSync(art, 'utf8'));"
        "const out = JSON.parse(readFileSync(loans, 'utf8')).map((l) => {"
        "  const input = Object.fromEntries("
        "    Object.entries(l).map(([k, v]) => [k, v ?? 'unknown']));"
        "  const r = calculate(model, input);"
        "  const reasons = r.reasonCodes.map((c) => c.feature);"
        "  return { score: r.score, pd: r.pd12m, grade: r.grade, reasons };"
        "});"
        "console.log(JSON.stringify(out));"
    )
    with tempfile.TemporaryDirectory() as tmp:
        loans_path = Path(tmp) / "loans.json"
        loans_path.write_text(json.dumps(loans), encoding="utf-8")
        run = subprocess.run(
            [
                node,
                "--experimental-strip-types",
                "--input-type=module",
                "-e",
                script,
                str(ROOT / "web" / "src" / "lib" / "calculator.ts"),
                str(ROOT / "artefacts" / "pd_models.json"),
                str(loans_path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    js = json.loads(run.stdout)

    assert len(js) == len(py) == 60
    for (_, p), j, loan in zip(py.iterrows(), js, loans):
        reasons = [r for r in (p.reason_1, p.reason_2, p.reason_3) if r is not None]
        assert j["score"] == p.score, loan
        assert j["grade"] == p.grade, loan
        assert j["reasons"] == reasons, loan
        assert math.isclose(j["pd"], p.pd_12m, rel_tol=1e-12), loan
    assert len({j["grade"] for j in js}) >= 4, "the combinations should span several grades"
