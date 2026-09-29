import { useState } from "react";
import type { EclRow, StageTotal } from "../lib/ecl";
import { fmtInt, fmtMoney, fmtMoneyCompact, fmtPct } from "../lib/format";
import { Toggle } from "./EclCharts";

const STAGE_NAME: Record<string, string> = { "1": "Performing", "2": "Risk has risen", "3": "Defaulted" };
const STAGE_VAR = ["var(--stage-1)", "var(--stage-2)", "var(--stage-3)"];

/** One bar for the loan mix by stage, with a legend chip per segment carrying loans and ECL. */
export function StageMixBar({ totals }: { totals: StageTotal[] }) {
  const total = totals.reduce((s, t) => s + t.n, 0) || 1;
  return (
    <div>
      <div
        className="flex h-14 w-full gap-[2px] overflow-hidden rounded-lg"
        role="img"
        aria-label={totals.map((t) => `Stage ${t.stage} ${fmtPct(t.n / total, 1)} of loans`).join(", ")}
      >
        {totals.map((t, i) => (
          <div
            key={t.stage}
            title={`Stage ${t.stage}: ${fmtPct(t.n / total, 1)} of loans`}
            style={{ width: `${(t.n / total) * 100}%`, minWidth: t.n > 0 ? 4 : 0, background: STAGE_VAR[i] }}
          />
        ))}
      </div>
      <ul className="mt-3 grid list-none gap-2 p-0 sm:grid-cols-3">
        {totals.map((t, i) => (
          <li key={t.stage} className="rounded-md border p-3 text-sm" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
            <div className="flex items-center gap-2 font-medium" style={{ color: "var(--ink)" }}>
              <span aria-hidden className="inline-block size-3 rounded-sm" style={{ background: STAGE_VAR[i], boxShadow: "0 0 0 1px var(--border)" }} />
              Stage {t.stage} · {STAGE_NAME[t.stage]}
            </div>
            <div className="tabular mt-1 text-lg font-semibold" style={{ color: "var(--ink)" }}>{fmtPct(t.n / total, 1)}</div>
            <div className="tabular text-xs" style={{ color: "var(--ink-2)" }}>
              {fmtInt(t.n)} loans · {fmtMoney(t.ecl)} ECL
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** ECL by grade (rows) and stage (columns) as a heatmap; shade is the cell's share of the largest ECL. */
export function StageGradeHeatmap({ rows }: { rows: EclRow[] }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const grades = [...new Set(rows.map((r) => r.grade))].sort();
  const stages = ["1", "2", "3"];
  const cell = (g: string, s: string) => rows.find((r) => r.grade === g && r.stage === s);
  const max = Math.max(1, ...rows.map((r) => r.ecl.value ?? 0));
  return (
    <div>
      <Toggle view={view} onToggle={setView} />
      {view === "chart" ? (
        <div className="overflow-x-auto">
          <table className="w-full border-separate text-sm" style={{ borderSpacing: 3 }}>
            <thead>
              <tr style={{ color: "var(--ink-3)" }}>
                <th className="text-left font-normal">Grade</th>
                {stages.map((s) => (
                  <th key={s} className="text-center font-normal">Stage {s}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grades.map((g) => (
                <tr key={g}>
                  <th scope="row" className="font-mono text-left font-normal" style={{ color: "var(--ink-2)" }}>{g}</th>
                  {stages.map((s) => {
                    const r = cell(g, s);
                    const v = r?.ecl.value ?? null;
                    return (
                      <td
                        key={s}
                        className="tabular rounded text-center align-middle"
                        style={{
                          height: 48,
                          minWidth: 68,
                          color: "var(--ink)",
                          background:
                            v === null
                              ? "var(--surface-2)"
                              : `color-mix(in srgb, var(--accent) ${Math.round(6 + (v / max) * 40)}%, var(--surface))`,
                        }}
                        title={r ? `${fmtInt(r.n_loans)} loans` : "No loans"}
                      >
                        {v === null ? "—" : (
                          <>
                            <span className="block font-medium">{fmtMoneyCompact(v)}</span>
                            <span className="block text-xs" style={{ color: "var(--ink-2)" }}>
                              {r!.ead.value ? fmtPct(v / r!.ead.value) : "—"} of EAD
                            </span>
                          </>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
            Darker cells hold more ECL. Each cell also shows ECL as a share of the balance owed.
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: "var(--ink-3)" }}>
                <th className="text-left">Stage</th>
                <th className="text-left">Grade</th>
                <th className="text-right">n</th>
                <th className="text-right">EAD</th>
                <th className="text-right">ECL</th>
                <th className="text-right">Coverage</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={`${r.stage}-${r.grade}`} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="py-1">{r.stage}</td>
                  <td className="font-mono py-1">{r.grade}</td>
                  <td className="tabular text-right">{fmtInt(r.n_loans)}</td>
                  <td className="tabular text-right">{r.ead.value !== null ? fmtMoney(r.ead.value) : "—"}</td>
                  <td className="tabular text-right">{r.ecl.value !== null ? fmtMoney(r.ecl.value) : "—"}</td>
                  <td className="tabular text-right">{r.ead.value ? fmtPct((r.ecl.value ?? 0) / r.ead.value) : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
