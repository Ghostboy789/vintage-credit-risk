import { useMemo, useState } from "react";
import type { PdModelsArtefact } from "../lib/types";
import { calculate, featureList, type CalcInput } from "../lib/calculator";
import { fmtPct } from "../lib/format";

const PRESETS: Record<string, CalcInput> = {
  "Typical 2003 loan": { fico: 700, ltv_pct: 80, dti_pct: 34 },
  "2007 high-LTV": { fico: 660, ltv_pct: 95, dti_pct: 42 },
  "Strong 2015 borrower": { fico: 770, ltv_pct: 60, dti_pct: 22 },
};

function bins(model: PdModelsArtefact, feature: string) {
  return model.points_table.filter((b) => b.feature === feature);
}

export function Calculator({ model }: { model: PdModelsArtefact }) {
  const features = useMemo(() => featureList(model), [model]);
  const [input, setInput] = useState<CalcInput>(() => {
    const initial: CalcInput = {};
    for (const f of features) initial[f] = "unknown";
    return initial;
  });

  const result = useMemo(() => calculate(model, input), [model, input]);

  return (
    <div id="calculator" className="grid grid-cols-1 gap-8 lg:grid-cols-12">
      <div className="lg:col-span-5">
        <div className="mb-4 flex flex-wrap gap-2">
          {Object.entries(PRESETS).map(([name, preset]) => (
            <button
              key={name}
              onClick={() => setInput((prev) => ({ ...prev, ...preset }))}
              className="rounded-full border px-3 py-1 text-xs"
              style={{ borderColor: "var(--border)", color: "var(--ink-2)" }}
            >
              {name}
            </button>
          ))}
        </div>
        {features.map((feature) => {
          const featureBins = bins(model, feature);
          const numeric = featureBins.some((b) => !b.is_missing_bin && b.categories.length === 0);
          const current = input[feature];
          return (
            <div key={feature} className="mb-4">
              <label className="mb-1 flex items-center justify-between text-sm">
                <span className="font-mono">{feature}</span>
                <span style={{ color: "var(--ink-3)" }}>{current === "unknown" ? "Unknown" : String(current)}</span>
              </label>
              {numeric ? (
                <input
                  type="number"
                  value={current === "unknown" ? "" : (current as number)}
                  onChange={(e) =>
                    setInput((prev) => ({ ...prev, [feature]: e.target.value === "" ? "unknown" : Number(e.target.value) }))
                  }
                  placeholder="Unknown"
                  className="w-full rounded-md border px-2 py-1"
                  style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink)" }}
                />
              ) : (
                <select
                  value={current === "unknown" ? "unknown" : String(current)}
                  onChange={(e) => setInput((prev) => ({ ...prev, [feature]: e.target.value }))}
                  className="w-full rounded-md border px-2 py-1"
                  style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink)" }}
                >
                  <option value="unknown">Unknown</option>
                  {[...new Set(featureBins.flatMap((b) => b.categories))].map((c) => (
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
        <div className="rounded-lg border p-6" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
          <div className="flex items-baseline gap-4">
            <div className="tabular font-semibold" style={{ fontSize: 64 }}>
              {result.score}
            </div>
            <div className="font-mono rounded px-2 py-1" style={{ background: "var(--surface-2)" }}>
              Grade {result.grade}
            </div>
            <div className="tabular text-xl">PD {fmtPct(result.pd12m)}</div>
          </div>
          <p className="mt-1 text-sm" style={{ color: "var(--ink-3)" }}>
            {result.pdLabel}
          </p>

          <h3 className="mt-6 text-sm" style={{ color: "var(--ink-2)" }}>
            Contribution by feature
          </h3>
          <div className="mt-2 space-y-1">
            {[...result.contributions].sort((a, b) => b.points - a.points).map((c) => (
              <div key={c.feature} className="flex items-center gap-2 text-sm">
                <span className="font-mono w-28 shrink-0">{c.feature}</span>
                <div className="h-2 flex-1 rounded" style={{ background: "var(--ink-muted)" }}>
                  <div
                    className="h-2 rounded"
                    style={{ width: `${Math.max(2, (c.points / c.maxPoints) * 100)}%`, background: "var(--accent)" }}
                  />
                </div>
                <span className="tabular w-10 text-right">{c.points}</span>
              </div>
            ))}
          </div>

          <h3 className="mt-6 text-sm" style={{ color: "var(--ink-2)" }}>
            Reason codes
          </h3>
          <ul className="mt-2 space-y-1 text-sm">
            {result.reasonCodes.length === 0 && <li style={{ color: "var(--ink-3)" }}>No shortfall — every feature is in its best bin.</li>}
            {result.reasonCodes.map((r) => (
              <li key={r.feature}>
                {r.feature} {r.bin.bin}: −{r.shortfall} points vs best bin
              </li>
            ))}
          </ul>

          <p className="mt-6 text-xs" style={{ color: "var(--ink-3)" }}>
            Illustrative. Development-average 12-month PD, not a lending decision.
          </p>
        </div>
      </div>
    </div>
  );
}
