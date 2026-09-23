import type { Artefacts } from "../lib/artefacts";
import { VintageCurveChart } from "../components/VintageCurveChart";
import { fmtPct, fmtInt } from "../lib/format";

export function Vintages({ data }: { data: Artefacts }) {
  const { portfolio } = data;
  const atComparable = portfolio.vintage_curves_annual
    .filter((r) => r.months_on_book === portfolio.comparable_months_on_book)
    .sort((a, b) => (b.cum_default_rate.value ?? 0) - (a.cum_default_rate.value ?? 0));

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
            Ranked at month {portfolio.comparable_months_on_book}
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
        <h2 className="font-display text-2xl">Loss drivers</h2>
        <p className="text-sm" style={{ color: "var(--ink-3)" }}>
          n = {fmtInt(portfolio.summary.n_defaults_primary.value ?? 0)} primary defaults across the portfolio.
        </p>
      </section>
    </div>
  );
}
