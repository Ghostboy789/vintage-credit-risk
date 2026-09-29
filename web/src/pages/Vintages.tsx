import type { Artefacts } from "../lib/artefacts";
import { VintageCurveChart } from "../components/VintageCurveChart";
import { DefinitionDumbbell } from "../components/DefinitionDumbbell";
import { LossDrivers } from "../components/LossDrivers";
import { useState } from "react";
import { fmtInt, fmtPct } from "../lib/format";
import { COMPARE_MOB, rowsAt } from "../lib/vintage";
import { CrisisStory } from "../components/CrisisStory";
import { Term } from "../components/Term";

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
      <p className="mt-3 max-w-[68ch] text-lg" style={{ color: "var(--ink-2)" }}>
        A <Term k="vintage">vintage</Term> is all the loans made in one year, followed as they age. This page asks a simple question: did loans
        made in some years go bad far more often than others, and how bad did the 2006–07 loans get?
      </p>
      <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        Each line is the <Term k="cumulative default rate">cumulative default rate</Term> by <Term k="months on book">months on book</Term>, one
        line per origination year. Vintages are compared at month {COMPARE_MOB}, and only those fully observed that long; a dashed line means
        not every loan in that vintage has been on book that long yet.
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
          Every origination year on one chart. Pick a period to highlight it, hover or use the arrow keys to read any line, or pick a year in the ranking to light up its line.
        </p>
        <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="min-w-0 lg:col-span-8">
            <VintageCurveChart rows={rows} highlight={brush === null ? undefined : [brush]} />
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1 text-[13px]" style={{ color: "var(--ink-2)" }} aria-hidden>
              <span className="inline-flex items-center gap-2">
                <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="var(--crisis)" strokeWidth="2.5" /></svg> highlighted vintage
              </span>
              <span className="inline-flex items-center gap-2">
                <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="var(--ink-3)" strokeWidth="1.5" /></svg> other vintages
              </span>
              <span className="inline-flex items-center gap-2">
                <svg width="26" height="8"><line x1="0" y1="4" x2="26" y2="4" stroke="var(--ink-2)" strokeWidth="2" strokeDasharray="3 3" /></svg> not fully observed yet
              </span>
            </div>
          </div>
          <div className="lg:col-span-4">
            <h3 className="text-base font-medium">Ranked at month {COMPARE_MOB}</h3>
            <p className="text-[13px]" style={{ color: "var(--ink-2)" }}>
              {ranked.length} vintages observed that long, highest first. Tap or hover a row to light up its line.
            </p>
            <div className="relative mt-3" onMouseLeave={() => setBrush(null)}>
              <div className="grid grid-cols-[3.4rem_1fr_4rem] gap-2 font-mono text-[11px]" style={{ color: "var(--ink-3)" }} aria-hidden>
                <span />
                <span className="relative h-4">
                  {[0, 0.5, 1].map((f) => (
                    <span key={f} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: `${f * 100}%`, transform: f === 1 ? "translateX(-100%)" : f === 0 ? "none" : undefined }}>
                      {fmtPct(hi * f, 0)}
                    </span>
                  ))}
                </span>
                <span />
              </div>
              <ul>
                {ranked.map((r, idx) => {
                  const e = r.cum_default_rate;
                  const p = (v: number) => `${(v / hi) * 100}%`;
                  const crisis = r.vintage_year === 2006 || r.vintage_year === 2007;
                  const on = brush === r.vintage_year;
                  return (
                    <li key={r.vintage_year}>
                      <button
                        type="button"
                        aria-pressed={on}
                        onMouseEnter={() => setBrush(r.vintage_year)}
                        onFocus={() => setBrush(r.vintage_year)}
                        onBlur={() => setBrush(null)}
                        onClick={() => setBrush(on ? null : r.vintage_year)}
                        className="grid min-h-[36px] w-full grid-cols-[3.4rem_1fr_4rem] items-center gap-2 rounded px-0 text-left text-sm transition-colors"
                        style={{ background: on ? "color-mix(in srgb, var(--accent) 14%, transparent)" : idx % 2 ? "transparent" : "color-mix(in srgb, var(--ink-muted) 22%, transparent)" }}
                      >
                        <span className="font-mono pl-1" style={{ color: crisis ? "var(--crisis)" : "var(--ink)", fontWeight: crisis ? 600 : 400 }}>
                          {r.vintage_year}
                        </span>
                        <span className="relative h-5" aria-hidden>
                          <span className="absolute inset-y-0 left-0 w-px" style={{ background: "var(--ink-3)" }} />
                          {e.ci_low !== null && e.ci_high !== null && (
                            <span
                              className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full"
                              style={{ left: p(e.ci_low), width: `calc(${p(e.ci_high)} - ${p(e.ci_low)} + 2px)`, background: crisis ? "var(--crisis)" : "var(--ink-3)", opacity: 0.55 }}
                            />
                          )}
                          <span
                            className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full"
                            style={{ left: p(e.value ?? 0), background: crisis ? "var(--crisis)" : "var(--ink)", border: "2px solid var(--bg)" }}
                          />
                        </span>
                        <span className="tabular pr-1 text-right">{fmtPct(e.value ?? 0, 1)}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
            <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
              dot: rate · line: 95% <Term k="Wilson interval">Wilson interval</Term> · n = {nRange} loans per vintage
            </p>
          </div>
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Definition effect</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          A <Term k="default">default</Term> has to be defined before it can be counted. This compares defaults within 12 months under the primary definition against a naive one, per vintage. The gap is what the definition choice moves.
        </p>
        <div className="mt-6">
          <DefinitionDumbbell rows={portfolio.default_definition_effect as unknown as { vintage_year: number; defaults_12m_primary: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string }; defaults_12m_naive: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string } }[]} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Loss drivers</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Which loans go bad most often: the lifetime default rate by <Term k="LTV">loan-to-value</Term> band and by state, with 95% intervals. Long lists show the highest ten first.
        </p>
        <div className="mt-6">
          <LossDrivers rows={portfolio.loss_drivers as unknown as { dimension: string; segment: string; default_rate: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string }; loss_rate: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string } }[]} />
        </div>
      </section>
    </div>
  );
}
