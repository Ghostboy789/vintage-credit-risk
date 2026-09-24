import { useEffect, useMemo, useState } from "react";
import { m } from "framer-motion";
import type { PdModelsArtefact } from "../lib/types";
import { calculate, featureList, type CalcInput, type CalcResult } from "../lib/calculator";
import { fmtPct } from "../lib/format";
import { useReducedMotion } from "../lib/theme";
import { ResultIsland } from "./ResultIsland";

const PRESETS: Record<string, CalcInput> = {
  "Typical 2003 loan": { fico: 700, ltv_pct: 80, dti_pct: 34 },
  "2007 high-LTV": { fico: 660, ltv_pct: 95, dti_pct: 42 },
  "Strong 2015 borrower": { fico: 770, ltv_pct: 60, dti_pct: 22 },
};

// Slider ranges for the numeric inputs (plausible values, not model bounds).
const RANGES: Record<string, [number, number]> = {
  fico: [300, 850],
  ltv_pct: [1, 105],
  cltv_pct: [1, 105],
  dti_pct: [1, 65],
};

const LABELS: Record<string, string> = {
  fico: "Credit score",
  ltv_pct: "Loan-to-value (%)",
  cltv_pct: "Combined LTV (%)",
  dti_pct: "Debt-to-income (%)",
  occupancy_status: "Occupancy",
};

const label = (f: string) => LABELS[f] ?? f.replace(/_/g, " ");

export function Calculator({ model, onResult }: { model: PdModelsArtefact; onResult?: (r: CalcResult) => void }) {
  const reduced = useReducedMotion();
  const features = useMemo(() => featureList(model), [model]);
  const [input, setInput] = useState<CalcInput>(() => Object.fromEntries(features.map((f) => [f, "unknown"])));
  const [preset, setPreset] = useState<string | null>(null);
  const result = useMemo(() => calculate(model, input), [model, input]);
  useEffect(() => onResult?.(result), [result, onResult]);

  const set = (feature: string, value: string | number) => {
    setPreset(null);
    setInput((prev) => ({ ...prev, [feature]: value }));
  };
  const gradeNames = [...new Set(model.grades.map((g) => g.merged_into ?? g.grade))];
  const gradeIdx = Math.max(0, gradeNames.indexOf(result.grade));
  const spring = reduced ? { duration: 0 } : { type: "spring" as const, stiffness: 420, damping: 32 };

  return (
    <div id="calculator" className="grid grid-cols-1 gap-8 lg:grid-cols-12">
      <div className="lg:col-span-5">
        <div className="mb-6 flex flex-wrap gap-2" role="group" aria-label="Presets">
          {Object.entries(PRESETS).map(([name, p]) => (
            <button
              key={name}
              type="button"
              aria-pressed={preset === name}
              onClick={() => {
                setPreset(name);
                setInput((prev) => ({ ...prev, ...p }));
              }}
              className="min-h-[36px] rounded-full border px-3 text-xs transition-colors"
              style={{
                borderColor: preset === name ? "var(--accent)" : "var(--border)",
                background: preset === name ? "color-mix(in srgb, var(--accent) 14%, transparent)" : "transparent",
                color: preset === name ? "var(--ink)" : "var(--ink-2)",
              }}
            >
              {name}
            </button>
          ))}
        </div>
        {features.map((feature) => {
          const bins = model.points_table.filter((b) => b.feature === feature);
          const numeric = bins.some((b) => !b.is_missing_bin && b.categories.length === 0);
          const current = input[feature];
          const picked = result.contributions.find((c) => c.feature === feature)?.bin;
          const id = `calc-${feature}`;
          const [lo, hi] = RANGES[feature] ?? [0, 100];
          const categories = [...new Set(bins.flatMap((b) => b.categories))];
          return (
            <div key={feature} className="mb-5">
              <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                <label htmlFor={id}>{label(feature)}</label>
                <span className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
                  {picked ? (picked.is_missing_bin ? "Unknown" : picked.bin) : ""} · {picked?.points ?? 0} pts
                </span>
              </div>
              {numeric ? (
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    aria-label={`${label(feature)} slider`}
                    min={lo}
                    max={hi}
                    value={current === "unknown" ? Math.round((lo + hi) / 2) : Number(current)}
                    onChange={(e) => set(feature, Number(e.target.value))}
                    className="h-11 min-w-0 flex-1"
                    style={{ accentColor: "var(--accent)", opacity: current === "unknown" ? 0.5 : 1 }}
                  />
                  <input
                    id={id}
                    type="number"
                    inputMode="numeric"
                    value={current === "unknown" ? "" : (current as number)}
                    onChange={(e) => set(feature, e.target.value === "" ? "unknown" : Number(e.target.value))}
                    placeholder="Unknown"
                    className="tabular h-11 w-24 rounded-md border px-2"
                    style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink)" }}
                  />
                </div>
              ) : (
                <select
                  id={id}
                  value={current === "unknown" ? "unknown" : String(current)}
                  onChange={(e) => set(feature, e.target.value)}
                  className="h-11 w-full rounded-md border px-2"
                  style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink)" }}
                >
                  <option value="unknown">Unknown</option>
                  {categories.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              )}
            </div>
          );
        })}
      </div>

      <div className="lg:sticky lg:top-[88px] lg:col-span-7 lg:self-start">
        <div className="rounded-xl border p-6 md:p-8" style={{ borderColor: "var(--border)", background: "var(--surface)" }} aria-live="polite">
          <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
            <div>
              <div className="text-[13px]" style={{ color: "var(--ink-2)" }}>
                Score
              </div>
              <div className="tabular font-semibold leading-none" style={{ fontSize: "clamp(48px,6vw,64px)" }}>
                {result.score}
              </div>
            </div>
            <div>
              <div className="text-[13px]" style={{ color: "var(--ink-2)" }}>
                Grade
              </div>
              <div className="font-display text-4xl leading-none">{result.grade}</div>
            </div>
            <div>
              <div className="text-[13px]" style={{ color: "var(--ink-2)" }}>
                12-month PD
              </div>
              <div className="tabular text-3xl font-semibold leading-none">{fmtPct(result.pd12m)}</div>
            </div>
          </div>
          <p className="mt-3 text-sm" style={{ color: "var(--ink-3)" }}>
            {result.pdLabel}
          </p>

          <div className="relative mt-6 flex gap-1" aria-hidden>
            {gradeNames.map((g, i) => (
              <div
                key={g}
                className="font-mono relative z-10 flex h-8 flex-1 items-center justify-center rounded text-xs"
                style={{ background: "var(--surface-2)", color: i === gradeIdx ? "var(--ink)" : "var(--ink-3)" }}
              >
                {g}
              </div>
            ))}
            <m.div
              className="pointer-events-none absolute inset-y-0 z-20 rounded"
              style={{ width: `calc(${100 / gradeNames.length}% - 4px)`, border: "2px solid var(--accent)" }}
              initial={false}
              animate={{ left: `${(gradeIdx * 100) / gradeNames.length}%` }}
              transition={spring}
            />
          </div>
          <div className="font-mono mt-1 flex justify-between text-[11px]" style={{ color: "var(--ink-3)" }}>
            <span>lower risk</span>
            <span>higher risk</span>
          </div>

          <h3 className="mt-6 text-sm font-medium" style={{ color: "var(--ink-2)" }}>
            Points by feature
          </h3>
          <div className="mt-2 space-y-2">
            {[...result.contributions]
              .sort((a, b) => b.points - a.points)
              .map((c) => (
                <div key={c.feature} className="flex items-center gap-3 text-sm">
                  <span className="w-32 shrink-0 truncate">{label(c.feature)}</span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full" style={{ background: "var(--ink-muted)" }}>
                    <m.div
                      className="h-2 rounded-full"
                      style={{ background: "var(--accent)" }}
                      initial={false}
                      animate={{ width: `${c.maxPoints > 0 ? Math.max(2, (c.points / c.maxPoints) * 100) : 2}%` }}
                      transition={reduced ? { duration: 0 } : { duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
                    />
                  </div>
                  <span className="tabular w-16 text-right">
                    {c.points}
                    <span style={{ color: "var(--ink-3)" }}>/{c.maxPoints}</span>
                  </span>
                </div>
              ))}
          </div>

          <h3 className="mt-6 text-sm font-medium" style={{ color: "var(--ink-2)" }}>
            Reason codes
          </h3>
          <ol className="mt-2 space-y-1 text-sm">
            {result.reasonCodes.length === 0 && <li style={{ color: "var(--ink-3)" }}>No shortfall: every feature is in its best bin.</li>}
            {result.reasonCodes.map((r, i) => (
              <li key={r.feature} className="flex gap-2">
                <span className="font-mono" style={{ color: "var(--ink-3)" }}>
                  {i + 1}.
                </span>
                <span>
                  {label(r.feature)} <span className="font-mono text-xs">{r.bin.is_missing_bin ? "Unknown" : r.bin.bin}</span>: −{r.shortfall}{" "}
                  points vs best bin
                </span>
              </li>
            ))}
          </ol>

          <p className="mt-6 text-xs" style={{ color: "var(--ink-3)" }}>
            Illustrative. Development-average 12-month PD, not a lending decision.
          </p>
        </div>
      </div>
      <ResultIsland result={result} />
    </div>
  );
}
