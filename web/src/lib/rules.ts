import type { Artefacts } from "./artefacts";

// Plain-language names for the pre-registered pass rules (ids as in VALIDATION_PLAN.md).
export const RULE_NAMES: Record<string, string> = {
  D1a: "Few loans modified before default",
  S1: "Points move the right way in every feature",
  S2: "Discrimination holds out of time",
  S3: "Grades rank risk in order out of time",
  S4a: "Grades calibrated on the test sample",
  S4b: "Grades calibrated out of time",
  S5: "Applicant population is stable",
  C1: "Challenger beats the champion",
  R1: "Loan counts reconcile to source",
  R2: "Loan-months reconcile to source",
  R3: "Balances reconcile to source",
  R4: "Losses reconcile to source",
  R5: "Computed losses match reported losses",
  R6: "Expense components add up",
  R7: "Metrics layer matches the marts",
  R8: "Every published count matches its mart",
  G1: "Segment LGD estimated",
  G2: "LGD model beats segment averages",
  E3: "ECL backtest inside its bands",
  E4a: "Hand-worked ECL loan matches",
  E4b: "Staging edge cases behave",
  E4c: "Lifetime probabilities sum to one",
};

export interface Rule {
  rule_id: string;
  result: string;
  evidence?: string;
  artefact: string;
}

// FAIL first, then the other results that need attention; never sorted last.
const ORDER = ["FAIL", "AMBER", "INSUFFICIENT", "PASS", "NOT_RUN", "pending"];
const rank = (r: string) => {
  const i = ORDER.indexOf(r);
  return i === -1 ? ORDER.length : i;
};

export function sortRules(rules: Rule[]): Rule[] {
  return [...rules].sort((a, b) => rank(a.result) - rank(b.result));
}

export function collectRules(data: Artefacts, only?: (keyof Artefacts)[]): Rule[] {
  const names = only ?? (["portfolio", "pd_models", "lgd_ead", "ecl", "capital", "monitoring"] as (keyof Artefacts)[]);
  return names.flatMap((artefact) =>
    (((data[artefact] as { pass_rules?: unknown }).pass_rules ?? []) as { rule_id?: string; id?: string; result: string; evidence?: string }[]).map(
      (r) => ({ rule_id: String(r.rule_id ?? r.id ?? "?"), result: r.result, evidence: r.evidence, artefact })
    )
  );
}
