import type { Artefacts } from "../lib/artefacts";
import { VintageCurveChart } from "../components/VintageCurveChart";
import { DefinitionDumbbell } from "../components/DefinitionDumbbell";
import { LossDrivers } from "../components/LossDrivers";
import { fmtPct } from "../lib/format";

export function Vintages({ data }: { data: Artefacts }) {
  const { portfolio } = data;
  // Each vintage at the latest observed month on book up to the comparable month.
  const N = portfolio.comparable_months_on_book;
  const latest = new Map<number, (typeof portfolio.vintage_curves_annual)[number]>();
  for (const r of portfolio.vintage_curves_annual) {
    const cur = latest.get(r.vintage_year);
    if (r.months_on_book <= N && (!cur || r.months_on_book > cur.months_on_book)) latest.set(r.vintage_year, r);
  }
  const atComparable = [...latest.values()].sort((a, b) => (b.cum_default_rate.value ?? 0) - (a.cum_default_rate.value ?? 0));
  const rankMob = Math.max(0, ...atComparable.map((r) => r.months_on_book));

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">Vintages</h1>
      <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        Cumulative default rate by months on book, per origination vintage. Compare vintages only left
        of the dashed line, where every vintage has been observed.
      </p>

      <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-12">
        <div className="lg:col-span-8">
          <VintageCurveChart rows={portfolio.vintage_curves_annual} comparableMonths={portfolio.comparable_months_on_book} />
        </div>
        <div className="lg:col-span-4">
          <h3 className="text-sm" style={{ color: "var(--ink-2)" }}>
            Ranked at month {rankMob}
          </h3>
          <ul className="mt-2 space-y-1">
            {atComparable.map((r) => (
              <li key={r.vintage_year} className="flex items-center justify-between border-b py-1 text-sm" style={{ borderColor: "var(--border)" }}>
                <span className="font-mono">{r.vintage_year}</span>
                <span className="tabular">
                  {fmtPct(r.cum_default_rate.value ?? 0)}{" "}
                  <span style={{ color: "var(--ink-3)" }}>
                    [{fmtPct(r.cum_default_rate.ci_low ?? 0)}–{fmtPct(r.cum_default_rate.ci_high ?? 0)}]
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Definition effect</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Defaults within 12 months under the primary definition against the naive one, per vintage. The gap is what the definition choice moves.
        </p>
        <div className="mt-6">
          <DefinitionDumbbell rows={portfolio.default_definition_effect as unknown as { vintage_year: number; defaults_12m_primary: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string }; defaults_12m_naive: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string } }[]} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Loss drivers</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Lifetime default rate by segment, with 95% intervals.
        </p>
        <div className="mt-6">
          <LossDrivers rows={portfolio.loss_drivers as unknown as { dimension: string; segment: string; default_rate: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string }; loss_rate: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string } }[]} />
        </div>
      </section>
    </div>
  );
}
