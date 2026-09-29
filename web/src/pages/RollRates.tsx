import type { Artefacts } from "../lib/artefacts";
import { RollRateHeatmap } from "../components/RollRateHeatmap";
import { Term } from "../components/Term";

export function RollRates({ data }: { data: Artefacts }) {
  const rows = (data.portfolio.roll_rates ?? []) as {
    period_group: string;
    from_bucket: string;
    to_state: string;
    rate: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string };
  }[];

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">Roll rates</h1>
      <p className="mt-3 max-w-[68ch] text-lg" style={{ color: "var(--ink-2)" }}>
        A <Term k="roll rate">roll rate</Term> is the share of loans that move from one stage of lateness to another in a month. It shows how
        quickly a slip into arrears turns into a default, and how that changed through the crisis.
      </p>
      <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        How to read it: each row is where loans started the month, each column is where they ended up. The darker the cell, the larger the
        share. The outlined cell on the diagonal is loans staying put. The last column checks every row totals 100%. Pick an economic period
        above the grid to compare. Hover a cell for its 95% <Term k="Wilson interval">interval</Term>; <Term k="REO">REO</Term> means
        the lender has repossessed the home.
      </p>
      <div className="mt-6">
        <RollRateHeatmap rows={rows} />
      </div>

      <section className="mt-16">
        <h2 className="font-display text-2xl">RBI SMA mapping</h2>
        <table className="mt-4 w-full max-w-lg text-sm">
          <thead>
            <tr style={{ color: "var(--ink-3)" }}>
              <th className="text-left">SMA class</th>
              <th className="text-left">Days past due</th>
            </tr>
          </thead>
          <tbody>
            {[
              ["Standard / SMA-0", "0–30"],
              ["SMA-1", "31–60"],
              ["SMA-2", "61–90"],
              ["NPA", "90+"],
            ].map(([label, dpd]) => (
              <tr key={label} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="py-1">{label}</td>
                <td className="font-mono py-1">{dpd}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
