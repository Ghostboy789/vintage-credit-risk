import type { Artefacts } from "./artefacts";
import type { Estimate } from "./types";
import { eclDates, stageTotals, type EclRow } from "./ecl";
import { rowsAt, COMPARE_MOB } from "./vintage";

type Seg = { dimension: string; segment: string; lgd_economic: Estimate };
type Roll = { period_group: string; from_bucket: string; to_state: string; rate: Estimate };
type Disc = { sample: string; definition: string; model: string; gini: Estimate };
type Tot = { reporting_date: string; scenario: string; ecl: Estimate };

/** The artefact figures the Overview's loan journey and risk desk quote. Missing pieces are undefined. */
export function overviewFigures(data: Artefacts) {
  const { portfolio, pd_models, lgd_ead, ecl, capital } = data;
  const rolls = (portfolio.roll_rates ?? []) as Roll[];
  const roll = (from: string, to: string) => rolls.find((r) => r.period_group === "crisis" && r.from_bucket === from && r.to_state === to)?.rate;
  const at72 = rowsAt(portfolio.vintage_curves_annual, COMPARE_MOB);
  const v2006 = at72.find((r) => r.vintage_year === 2006);
  const lgd = ((lgd_ead.lgd_segments ?? []) as Seg[]).find((s) => s.dimension === "overall")?.lgd_economic;
  const ead = (lgd_ead.ead as { mean_ead?: Estimate } | undefined)?.mean_ead;
  const disc = (pd_models.discrimination ?? []) as Disc[];
  const gini = disc.find((d) => d.sample === "oot" && d.definition === "primary" && d.model === "champion")?.gini;
  const totals = ((ecl as { scenario_totals?: Tot[] }).scenario_totals ?? []).filter((t) => t.scenario === "final");
  const final = totals.sort((a, b) => b.reporting_date.localeCompare(a.reporting_date))[0];
  const rows = ((ecl as { by_date?: EclRow[] }).by_date ?? []) as EclRow[];
  const date = final?.reporting_date ?? eclDates(rows).at(-1);
  const stages = date ? stageTotals(rows, date) : [];
  const cap = (capital as { totals?: Record<string, Estimate> }).totals;
  return {
    at72,
    v2006,
    cure30: roll("dpd_30", "current"),
    stay90: roll("dpd_90p", "dpd_90p"),
    lgd,
    ead,
    gini,
    ecl: final?.ecl,
    eclDate: date,
    stages,
    capital: cap?.capital,
    rwa: cap?.rwa,
  };
}
