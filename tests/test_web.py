"""Site checks that need no browser: every published pass rule has a plain-language name."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_every_published_rule_has_a_plain_name():
    rules_ts = (ROOT / "web" / "src" / "lib" / "rules.ts").read_text(encoding="utf-8")
    block = rules_ts.split("RULE_NAMES", 1)[1].split("};", 1)[0]
    named = set(re.findall(r"^\s*([A-Z]\d+[a-z]?):", block, flags=re.M))
    published = set()
    for path in (ROOT / "tests" / "fixtures" / "artefacts").glob("*.json"):
        for rule in json.loads(path.read_text(encoding="utf-8")).get("pass_rules", []):
            published.add(rule.get("rule_id") or rule.get("id"))
    assert published, "no pass rules found in the artefact fixtures"
    assert published <= named, f"rules without a plain name: {sorted(published - named)}"
