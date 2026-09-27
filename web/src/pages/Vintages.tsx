import type { Artefacts } from "../lib/artefacts";
import { VintageCurveChart } from "../components/VintageCurveChart";
import { DefinitionDumbbell } from "../components/DefinitionDumbbell";
import { LossDrivers } from "../components/LossDrivers";
import { useState } from "react";
import { fmtInt, fmtPct } from "../lib/format";
import { COMPARE_MOB, rowsAt } from "../lib/vintage";
import { CrisisStory } from "../components/CrisisStory";

export function Vintages({ data }: { data: Artefacts }) {
  const { portfolio } = data;
  const rows = portfolio.vintage_curves_annual;
  const ranked = [...rowsAt(rows)].sort((a, b) => (b.cum_default_rate.value ?? 0) - (a.cum_default_rate.value ?? 0));
  const hi = Math.max(0.001, ...ranked.map((r) => r.cum_default_rate.ci_high ?? r.cum_default_rate.value ?? 0));
  const ns = ranked.map((r) => r.cum_default_rate.n);
  const nRange = Math.min(...ns) === Math.max(...ns) ? fmtInt(ns[0] ?? 0) : `${fmtInt(Math.min(...ns))}–${fmtInt(Math.max(...ns))}`;
  const [brush, setBrush] = useState<number | null>(null);

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">Vintages</h1>
      <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        Cumulative default rate by months on book, one line per origination year. Vintages are compared at month{" "}
        {COMPARE_MOB}, and only those fully observed that long; a dashed line means not every loan in that vintage has
        been on book that long yet.
      </p>

      <section className="mt-12">
        <h2 className="font-display text-2xl">Through the crisis, one step at a time</h2>
        <div className="mt-4">
          <CrisisStory rows={rows} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Every vintage</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Pick a period, hover or use the arrow keys to read any line. Hovering the ranking highlights its line.
        </p>
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="min-w-0 lg:col-span-8">
            <VintageCurveChart rows={rows} highlight={brush === null ? undefined : [brush]} />
          </div>
          <div className="lg:col-span-4">
            <h3 className="text-sm" style={{ color: "var(--ink-2)" }}>
              Ranked at month {COMPARE_MOB} ({ranked.length} vintages observed that long)
            </h3>
            <ul className="mt-2" onMouseLeave={() => setBrush(null)}>
              {ranked.map((r) => {
                const e = r.cum_default_rate;
                const p = (v: number) => `${(v / hi) * 100}%`;
                const crisis = r.vintage_year === 2006 || r.vintage_year === 2007;
                return (
                  <li
                    key={r.vintage_year}
                    onMouseEnter={() => setBrush(r.vintage_year)}
                    className="grid grid-cols-[3.2rem_1fr_4.2rem] items-center gap-2 rounded px-1 py-[3px] text-sm transition-colors"
                    style={{ background: brush === r.vintage_year ? "color-mix(in srgb, var(--accent) 12%, transparent)" : undefined }}
                  >
                    <span className="font-mono" style={{ color: crisis ? "var(--crisis)" : undefined }}>
                      {r.vintage_year}
                    </span>
                    <span className="relative h-3" aria-hidden>
                      <span className="absolute top-1/2 h-px w-full" style={{ background: "var(--ink-muted)" }} />
                      {e.ci_low !== null && e.ci_high !== null && (
                        <span className="absolute top-1/2 h-0.5 -translate-y-1/2" style={{ left: p(e.ci_low), width: `calc(${p(e.ci_high)} - ${p(e.ci_low)} + 2px)`, background: "var(--ink-2)" }} />
                      )}
                      <span
                        className="absolute top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full"
                        style={{ left: p(e.value ?? 0), background: crisis ? "var(--crisis)" : "var(--ink)" }}
                      />
                    </span>
                    <span className="tabular text-right">{fmtPct(e.value ?? 0, 1)}</span>
                  </li>
                );
              })}
            </ul>
            <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
              dot: rate · bar: 95% Wilson interval · n = {nRange} loans per vintage
            </p>
          </div>
        </div>
      </section>

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
