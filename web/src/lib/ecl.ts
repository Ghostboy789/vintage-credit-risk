import type { Estimate } from "./types";

export interface EclRow {
  reporting_date: string;
  stage: string;
  grade: string;
  n_loans: number;
  ead: { value: number | null; n: number };
  ecl: Estimate;
}

/** Every distinct reporting date, ascending — backs the date picker. */
export function eclDates(rows: EclRow[]): string[] {
  return [...new Set(rows.map((r) => r.reporting_date))].sort();
}

export interface StageTotal {
  stage: string;
  n: number;
  ecl: number;
}

/** Stage-mix totals (n loans, ECL) at one reporting date, straight off the raw rows. */
export function stageTotals(rows: EclRow[], date: string): StageTotal[] {
  const atDate = rows.filter((r) => r.reporting_date === date);
  return ["1", "2", "3"].map((stage) => ({
    stage,
    n: atDate.filter((r) => r.stage === stage).reduce((sum, r) => sum + r.n_loans, 0),
    ecl: atDate.filter((r) => r.stage === stage).reduce((sum, r) => sum + (r.ecl.value ?? 0), 0),
  }));
}
