// Client-side scorecard calculator. Exact port of models/pd/scorecard.py's score()/pd_from_score()/
// grade_of() — same formulas, same tie-breaks — so it must agree with the Python scorecard (tested
// in the real-data release against the real points table; here it's tested against the fixture points table).
import type { PdModelsArtefact, PointsBin, Grade } from "./types";

export interface CalcInput {
  [feature: string]: string | number | "unknown";
}

export interface FeatureContribution {
  feature: string;
  bin: PointsBin;
  points: number;
  maxPoints: number;
  shortfall: number;
}

export interface CalcResult {
  score: number;
  pd12m: number;
  grade: string;
  pdLabel: string;
  contributions: FeatureContribution[];
  reasonCodes: FeatureContribution[];
}

function binsFor(model: PdModelsArtefact, feature: string): PointsBin[] {
  return model.points_table.filter((b) => b.feature === feature);
}

/** Pick the bin for one feature's value, "unknown" -> the missing bin. */
export function pickBin(bins: PointsBin[], value: string | number | "unknown"): PointsBin {
  if (value === "unknown" || value === "" || value === null || value === undefined) {
    return bins.find((b) => b.is_missing_bin) ?? bins[0];
  }
  if (typeof value === "number") {
    const numeric = bins.filter((b) => !b.is_missing_bin && b.categories.length === 0);
    const hit = numeric.find(
      (b) => (b.lower === null || value >= b.lower) && (b.upper === null || value < b.upper)
    );
    return hit ?? bins.find((b) => b.is_missing_bin) ?? bins[0];
  }
  const hit = bins.find((b) => b.categories.includes(String(value)));
  return hit ?? bins.find((b) => b.is_missing_bin) ?? bins[0];
}

export function pdFromScore(score: number, offset: number, factor: number): number {
  return 1 / (1 + Math.exp((score - offset) / factor));
}

/** Master-scale grade lookup by PD, following merged_into (scorecard.py grade_of). */
export function gradeOfPd(pdValue: number, grades: Grade[]): string {
  // grades are ordered A..G by pd_low ascending in the artefact
  const hit = grades.find((g) => pdValue >= g.pd_low && pdValue < g.pd_high) ?? grades[grades.length - 1];
  return hit.merged_into ?? hit.grade;
}

export function featureList(model: PdModelsArtefact): string[] {
  return [...new Set(model.points_table.map((b) => b.feature))];
}

export function calculate(model: PdModelsArtefact, input: CalcInput): CalcResult {
  const features = featureList(model);
  const contributions: FeatureContribution[] = features.map((feature) => {
    const bins = binsFor(model, feature);
    const bin = pickBin(bins, input[feature] ?? "unknown");
    const maxPoints = Math.max(...bins.map((b) => b.points));
    return { feature, bin, points: bin.points, maxPoints, shortfall: maxPoints - bin.points };
  });

  const score = contributions.reduce((sum, c) => sum + c.points, 0);
  const { offset, factor, pd_label } = model.scaling;
  const pd12m = pdFromScore(score, offset, factor);
  const grade = gradeOfPd(pd12m, model.grades);

  const reasonCodes = [...contributions]
    .filter((c) => c.shortfall > 0)
    .sort((a, b) => b.shortfall - a.shortfall)
    .slice(0, 3);

  return { score, pd12m, grade, pdLabel: pd_label, contributions, reasonCodes };
}
