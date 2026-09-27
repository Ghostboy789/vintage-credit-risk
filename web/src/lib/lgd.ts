import type { Estimate, LgdEadArtefact } from "./types";

export interface LgdSegmentRow {
  dimension: string;
  segment: string;
  lgd_economic: Estimate;
  lgd_gross_of_mi: Estimate;
  lgd_undiscounted: Estimate;
}

export interface DownturnLgdRow {
  ltv_band: string;
  lgd_gross_of_mi: Estimate;
}

export interface LgdEadView {
  meanEad: Estimate;
  overall: LgdSegmentRow | null;
  segments: LgdSegmentRow[];
  dimensions: string[];
  downturn: DownturnLgdRow[];
  modelUsed: boolean;
}

/** The fields the LGD & EAD section renders, read straight from lgd_ead.json. */
export function selectLgdEad(lgd: LgdEadArtefact): LgdEadView {
  const l = lgd as unknown as {
    ead: { mean_ead: Estimate };
    lgd_segments: LgdSegmentRow[];
    downturn_lgd?: DownturnLgdRow[];
    lgd_model?: { used_in_ecl?: boolean };
  };
  const segments = l.lgd_segments ?? [];
  const overall = segments.find((s) => s.dimension === "overall") ?? null;
  const dimensions = [...new Set(segments.map((s) => s.dimension))].filter((d) => d !== "overall");
  return {
    meanEad: l.ead.mean_ead,
    overall,
    segments,
    dimensions,
    downturn: l.downturn_lgd ?? [],
    modelUsed: l.lgd_model?.used_in_ecl ?? false,
  };
}
