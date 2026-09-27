import type { CapitalArtefact, Estimate } from "./types";

export interface CapitalGradeRow {
  grade: string;
  n_loans: number;
  ead: Estimate;
  pd: Estimate;
  lgd: Estimate;
  rwa: Estimate;
  capital: Estimate;
}

export interface CapitalTotals {
  ead: Estimate;
  rwa: Estimate;
  capital: Estimate;
  ecl: Estimate;
}

export interface CapitalView {
  status?: string;
  parameters: Record<string, number | string>;
  limits: string[];
  byGrade: CapitalGradeRow[];
  totals: CapitalTotals | null;
}

/** The exact fields Capital.tsx renders, pulled straight from the artefact (never recomputed —
 * `totals` is the artefact's own published figure, with its own ci_method). */
export function selectCapital(capital: CapitalArtefact): CapitalView {
  const c = capital as unknown as {
    status?: string;
    parameters: Record<string, number | string>;
    limits?: string[];
    by_grade?: CapitalGradeRow[];
    totals?: CapitalTotals;
  };
  return {
    status: c.status,
    parameters: c.parameters ?? {},
    limits: c.limits ?? [],
    byGrade: c.by_grade ?? [],
    totals: c.totals ?? null,
  };
}
