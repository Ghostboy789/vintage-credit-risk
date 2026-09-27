import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, m } from "framer-motion";
import { featureLabel, binText, categoryLabel } from "../lib/labels";
import type { PdModelsArtefact } from "../lib/types";
import { calculate, featureList, type CalcInput, type CalcResult } from "../lib/calculator";
import { fmtPct } from "../lib/format";
import { useReducedMotion } from "../lib/theme";
import { ResultIsland } from "./ResultIsland";

// Illustrative profiles, not real loans. Every selected feature is set so a preset is complete.
const PRESETS: Record<string, CalcInput> = {
  "Typical 2003 loan": { fico: 725, ltv_pct: 75, dti_pct: 33, rate_spread_pct: 0, term_band: "gt_240", property_type: "SF", channel: "R" },
  "2007 high-LTV": { fico: 665, ltv_pct: 95, dti_pct: 46, rate_spread_pct: 0.5, term_band: "gt_240", property_type: "CO", channel: "B" },
  "Strong 2015 borrower": { fico: 790, ltv_pct: 60, dti_pct: 22, rate_spread_pct: -0.25, term_band: "le_180", property_type: "PU", channel: "R" },
};

// Slider ranges for the numeric inputs (plausible values, not model bounds): [min, max, step].
const RANGES: Record<string, [number, number, number]> = {
  fico: [300, 850, 1],
  ltv_pct: [1, 105, 1],
  cltv_pct: [1, 105, 1],
  dti_pct: [1, 65, 1],
  rate_spread_pct: [-1.5, 2, 0.05],
};

const label = featureLabel;

// Tween a number from its previous value to the new one, so a change reads as a change.
function useTween(target: number, reduced: boolean, ms = 450) {
  const [shown, setShown] = useState(target);
  const from = useRef(target);
  useEffect(() => {
    if (reduced) {
      from.current = target;
      setShown(target);
      return;
    }
    const start = performance.now();
    const a = from.current;
    let raf = 0;
    const step = (t: number) => {
      const k = Math.min(1, (t - start) / ms);
      const v = a + (target - a) * (1 - Math.pow(1 - k, 3));
      from.current = v;
      setShown(v);
      if (k < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [target, reduced, ms]);
  return shown;
}

// "1 in 270": the PD as a natural frequency.
const oneIn = (pd: number) => {
  const n = 1 / pd;
  const r = n >= 1000 ? Math.round(n / 100) * 100 : n >= 100 ? Math.round(n / 10) * 10 : Math.round(n);
  return new Intl.NumberFormat("en-US").format(r);
};

export function Calculator({ model, onResult }: { model: PdModelsArtefact; onResult?: (r: CalcResult) => void }) {
  const reduced = useReducedMotion();
  const features = useMemo(() => featureList(model), [model]);
  const first = Object.keys(PRESETS)[0];
  const [input, setInput] = useState<CalcInput>(() => ({ ...Object.fromEntries(features.map((f) => [f, "unknown"])), ...PRESETS[first] }));
  const [preset, setPreset] = useState<string | null>(first);
  const result = useMemo(() => calculate(model, input), [model, input]);
  const score = useTween(result.score, reduced);
  const pdShown = useTween(result.pd12m, reduced);
  // The last change in points, shown briefly beside the score.
  const prevScore = useRef(result.score);
  const [delta, setDelta] = useState<{ d: number; key: number } | null>(null);
  useEffect(() => {
    const d = result.score - prevScore.current;
    prevScore.current = result.score;
    if (d === 0) return;
    setDelta({ d, key: performance.now() });
    const t = setTimeout(() => setDelta(null), 1600);
    return () => clearTimeout(t);
  }, [result.score]);
  const prevGrade = useRef(result.grade);
  useEffect(() => onResult?.(result), [result, onResult]);

  const set = (feature: string, value: string | number) => {
    setPreset(null);
    setInput((prev) => ({ ...prev, [feature]: value }));
  };
  const gradeNames = [...new Set(model.grades.map((g) => g.merged_into ?? g.grade))];
  const gradeIdx = Math.max(0, gradeNames.indexOf(result.grade));
  // New grade slides in from below when risk rises, from above when it falls.
  const gradeDir = gradeIdx >= gradeNames.indexOf(prevGrade.current) ? 1 : -1;
  useEffect(() => {
    prevGrade.current = result.grade;
  }, [result.grade]);
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
          const [lo, hi, stepSize] = RANGES[feature] ?? [0, 100, 1];
          const categories = [...new Set(bins.flatMap((b) => b.categories))];
          return (
            <div key={feature} className="mb-5">
              <div className="mb-1.5 flex items-center justify-between gap-2 text-sm">
                <label htmlFor={id}>{label(feature)}</label>
                <span className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
                  {picked ? binText(feature, picked) : ""} · {picked?.points ?? 0} pts
                </span>
              </div>
              {numeric ? (
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    aria-label={`${label(feature)} slider`}
                    min={lo}
                    max={hi}
                    step={stepSize}
                    value={current === "unknown" ? (lo + hi) / 2 : Number(current)}
                    onChange={(e) => set(feature, Number(e.target.value))}
                    className="h-11 min-w-0 flex-1"
                    style={{ accentColor: "var(--accent)", opacity: current === "unknown" ? 0.5 : 1 }}
                  />
                  <input
                    id={id}
                    type="number"
                    inputMode="decimal"
                    step={stepSize}
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
                      {categoryLabel(feature, c)}
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
              <div className="flex h-5 items-center gap-2 text-[13px]" style={{ color: "var(--ink-2)" }}>
                Score
                <AnimatePresence>
                  {delta && (
                    <m.span
                      key={delta.key}
                      aria-hidden
                      className="tabular font-mono whitespace-nowrap rounded px-1.5 py-0.5 text-xs font-medium"
                      style={{
                        color: delta.d > 0 ? "var(--pass)" : "var(--fail)",
                        background: `color-mix(in srgb, ${delta.d > 0 ? "var(--pass)" : "var(--fail)"} 14%, transparent)`,
                      }}
                      initial={reduced ? false : { opacity: 0, y: delta.d > 0 ? 6 : -6 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: reduced ? 0 : 0.2 }}
                    >
                      {delta.d > 0 ? "+" : "−"}
                      {Math.abs(delta.d)} pts
                    </m.span>
                  )}
                </AnimatePresence>
              </div>
              <span className="tabular block font-semibold leading-none" style={{ fontSize: "clamp(48px,6vw,64px)" }}>
                {Math.round(score)}
              </span>
            </div>
            <div>
              <div className="text-[13px]" style={{ color: "var(--ink-2)" }}>
                Grade
              </div>
              <div className="font-display relative h-9 w-8 overflow-hidden text-4xl leading-none">
                <AnimatePresence initial={false}>
                  <m.span
                    key={result.grade}
                    className="absolute inset-0"
                    initial={reduced ? false : { y: `${gradeDir * 100}%`, opacity: 0 }}
                    animate={{ y: "0%", opacity: 1 }}
                    exit={reduced ? { opacity: 0, transition: { duration: 0 } } : { y: `${-gradeDir * 100}%`, opacity: 0 }}
                    transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                  >
                    {result.grade}
                  </m.span>
                </AnimatePresence>
              </div>
            </div>
            <div>
              <div className="text-[13px]" style={{ color: "var(--ink-2)" }}>
                12-month PD
              </div>
              <div className="tabular text-3xl font-semibold leading-none">{fmtPct(pdShown)}</div>
            </div>
          </div>
          <p className="mt-3 text-sm" style={{ color: "var(--ink-2)" }}>
            At this PD, about 1 in {oneIn(result.pd12m)} loans would default within 12 months.
          </p>
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
                  {label(r.feature)} <span className="font-mono text-xs">{binText(r.feature, r.bin)}</span>: −{r.shortfall}{" "}
                  points vs best bin
                </span>
              </li>
            ))}
          </ol>

          <p className="mt-6 text-xs" style={{ color: "var(--ink-3)" }}>
            Illustrative. Development-average 12-month PD, not a lending decision. The presets are made-up profiles, not real loans.
          </p>
        </div>
      </div>
      <ResultIsland result={result} />
    </div>
  );
}
