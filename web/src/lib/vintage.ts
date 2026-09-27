import type { VintageCurveRow } from "./types";

// Cross-vintage comparisons are made at one months-on-book point, only among vintages whose row is
// fully observed there. The artefact's portfolio-wide comparable_months_on_book is the minimum over
// every vintage, and the newest vintage has barely a month on book, so it is too early to compare at.
export const COMPARE_MOB = 72;

export function byYear(rows: VintageCurveRow[]): Map<number, VintageCurveRow[]> {
  const map = new Map<number, VintageCurveRow[]>();
  for (const r of rows) {
    if (!map.has(r.vintage_year)) map.set(r.vintage_year, []);
    map.get(r.vintage_year)!.push(r);
  }
  for (const arr of map.values()) arr.sort((a, b) => a.months_on_book - b.months_on_book);
  return new Map([...map.entries()].sort(([a], [b]) => a - b));
}

/** Each vintage's row at `mob`, for vintages fully observed there. */
export function rowsAt(rows: VintageCurveRow[], mob = COMPARE_MOB): VintageCurveRow[] {
  return rows.filter((r) => r.months_on_book === mob && r.fully_observed && r.cum_default_rate.value !== null);
}

export function rowAt(rows: VintageCurveRow[], year: number, mob = COMPARE_MOB): VintageCurveRow | undefined {
  return rowsAt(rows, mob).find((r) => r.vintage_year === year);
}

const WORDS = ["Twenty", "Twenty-one", "Twenty-two", "Twenty-three", "Twenty-four", "Twenty-five", "Twenty-six", "Twenty-seven", "Twenty-eight", "Twenty-nine"];
/** "Twenty-six" for 26; digits outside 20-29. */
export const countWord = (n: number) => WORDS[n - 20] ?? String(n);
