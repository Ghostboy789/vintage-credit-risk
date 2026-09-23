// Minimal shapes for the six CONTRACTS.md artefacts — only the fields the site actually reads.
// Kept intentionally small: no full schema mirror; extend a field here only when a page needs it.
export interface Estimate {
  value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  n: number;
  ci_method: string;
}

export interface ArtefactBase {
  schema_version: string;
  artefact: string;
  synthetic: boolean;
  generated_at: string;
  data_cutoff: string;
  code_version: string;
  suppressed_cells: number;
}

export interface PassRule {
  rule_id?: string;
  id?: string;
  result: "PASS" | "FAIL" | "AMBER" | "INSUFFICIENT" | "NOT_RUN" | string;
  evidence?: string;
  [key: string]: unknown;
}

export interface VintageCurveRow {
  vintage_year: number;
  vintage_quarter?: string;
  months_on_book: number;
  fully_observed: boolean;
  cum_default_rate: Estimate;
  cum_loss_rate?: Estimate;
  n_loans?: number;
}

export interface PortfolioArtefact extends ArtefactBase {
  summary: Record<string, Estimate>;
  comparable_months_on_book: number;
  vintage_curves: VintageCurveRow[];
  vintage_curves_annual: VintageCurveRow[];
  roll_rates?: unknown[];
  at_risk_at_start?: unknown[];
  n_at_risk_start?: unknown[];
  roll_cure_rates?: unknown[];
  sma?: unknown[];
  pass_rules?: PassRule[];
  [key: string]: unknown;
}

export interface PointsBin {
  feature: string;
  bin: string;
  lower: number | null;
  upper: number | null;
  categories: string[];
  is_missing_bin: boolean;
  woe: number;
  points: number;
  default_rate_dev_train: Estimate;
}

export interface Grade {
  grade: string;
  pd_low: number;
  pd_high: number;
  score_min: number | null;
  score_max: number | null;
  merged_into: string | null;
}

export interface Scaling {
  base_score: number;
  base_odds: number;
  pdo: number;
  factor: number;
  offset: number;
  intercept: number;
  pd_label: string;
}

export interface PdModelsArtefact extends ArtefactBase {
  model_id: string;
  scaling: Scaling;
  points_table: PointsBin[];
  grades: Grade[];
  samples?: unknown[];
  discrimination?: unknown;
  calibration?: unknown[];
  gini_drop?: unknown[];
  pass_rules?: PassRule[];
  challenger?: { status?: string; [key: string]: unknown };
  [key: string]: unknown;
}

export type LgdEadArtefact = ArtefactBase & Record<string, unknown>;
export type EclArtefact = ArtefactBase & Record<string, unknown>;
export type CapitalArtefact = ArtefactBase & Record<string, unknown>;
export type MonitoringArtefact = ArtefactBase & Record<string, unknown>;
