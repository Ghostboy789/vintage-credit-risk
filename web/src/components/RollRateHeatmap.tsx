import { useMemo, useState } from "react";
import type { Estimate } from "../lib/types";
import { ChartTooltip } from "./ChartTooltip";
import { fmtPct, fmtInt } from "../lib/format";

interface RollRow {
  period_group: string;
  from_bucket: string;
  to_state: string;
  rate: Estimate;
}

// Plain names for the delinquency buckets, exit states and economic periods (no numbers involved).
const STATE_LABEL: Record<string, string> = {
  current: "Current",
  dpd_30: "30 days late",
  dpd_60: "60 days late",
  dpd_90p: "90+ days late",
  reo: "Repossessed (REO)",
  prepaid: "Paid off early",
  matured: "Reached full term",
  credit_event: "Credit loss event",
  other_exit: "Other exit",
  missing: "Unknown",
};
const PERIOD_LABEL: Record<string, string> = {
  all: "All periods",
  pre_crisis: "Pre-crisis",
  crisis: "Crisis",
  recovery: "Recovery",
  recent: "Recent",
  covid: "COVID",
};
export const stateLabel = (c: string) => STATE_LABEL[c] ?? c.replace(/_/g, " ");
export const periodLabel = (c: string) => PERIOD_LABEL[c] ?? c.replace(/_/g, " ");

const FROM_ORDER = ["current", "dpd_30", "dpd_60", "dpd_90p", "reo"];
const TO_ORDER = ["current", "dpd_30", "dpd_60", "dpd_90p", "reo", "prepaid", "matured", "credit_event", "other_exit", "missing"];

export function RollRateHeatmap({ rows }: { rows: RollRow[] }) {
  const periods = useMemo(() => [...new Set(rows.map((r) => r.period_group))], [rows]);
  const [period, setPeriod] = useState(periods[0] ?? "");
  const [hover, setHover] = useState<{ x: number; y: number; row: RollRow } | null>(null);

  const cells = useMemo(() => {
    const map = new Map<string, RollRow>();
    for (const r of rows.filter((r) => r.period_group === period)) map.set(`${r.from_bucket}|${r.to_state}`, r);
    return map;
  }, [rows, period]);

  const toStates = TO_ORDER.filter((t) => FROM_ORDER.some((f) => cells.has(`${f}|${t}`)));
  const cell = 56;

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2" role="group" aria-label="Economic period">
        {periods.map((p) => (
          <button
            key={p}
            aria-pressed={p === period}
            onClick={() => setPeriod(p)}
            className="min-h-[44px] rounded-full border px-4 text-sm"
            style={{
              borderColor: "var(--border)",
              background: p === period ? "var(--accent)" : "transparent",
              color: p === period ? "var(--bg)" : "var(--ink-2)",
            }}
          >
            {periodLabel(p)}
          </button>
        ))}
      </div>
      <div className="relative overflow-x-auto">
        <table className="border-collapse text-xs">
          <thead>
            <tr>
              <th className="sticky left-0 p-1 text-left align-bottom font-normal" style={{ color: "var(--ink-3)", background: "var(--bg)" }}>
                From ↓ · to →
              </th>
              {toStates.map((t) => (
                <th key={t} className="p-1 text-center align-bottom font-normal leading-tight" style={{ color: "var(--ink-2)", minWidth: cell }}>
                  {stateLabel(t)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FROM_ORDER.map((from) => {
              const rowSum = toStates.reduce((s, t) => s + (cells.get(`${from}|${t}`)?.rate.value ?? 0), 0);
              return (
                <tr key={from}>
                  <td className="sticky left-0 whitespace-nowrap p-1 pr-2" style={{ color: "var(--ink)", background: "var(--bg)" }}>
                    {stateLabel(from)}
                  </td>
                  {toStates.map((to) => {
                    const c = cells.get(`${from}|${to}`);
                    const v = c?.rate.value ?? null;
                    const alpha = v === null ? 0 : Math.min(0.9, 0.08 + v * 0.9);
                    return (
                      <td
                        key={to}
                        className="tabular text-center transition-colors duration-300"
                        style={{
                          border: from === to ? "1px solid var(--ink-2)" : "1px solid var(--border)",
                          background: v === null ? "transparent" : `color-mix(in srgb, var(--accent) ${alpha * 100}%, var(--surface))`,
                          height: cell,
                          cursor: c ? "pointer" : "default",
                        }}
                        onMouseMove={(e) => {
                          if (!c) return;
                          const rect = (e.target as HTMLElement).getBoundingClientRect();
                          setHover({ x: rect.left + rect.width / 2, y: rect.top, row: c });
                        }}
                        onMouseLeave={() => setHover(null)}
                      >
                        {v === null ? "—" : v < 0.001 ? "<0.1%" : `${(v * 100).toFixed(1)}%`}
                      </td>
                    );
                  })}
                  <td className="tabular p-1 text-center" style={{ color: "var(--ink-3)" }}>
                    {(rowSum * 100).toFixed(0)}%
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {hover && (
          <ChartTooltip
            x={hover.x}
            y={hover.y - 300}
            label={`${stateLabel(hover.row.from_bucket)} → ${stateLabel(hover.row.to_state)}`}
            estimate={hover.row.rate}
            fmt={fmtPct}
            visible
          />
        )}
      </div>
      <p className="mt-2 text-sm font-mono" style={{ color: "var(--ink-3)" }}>
        The last column adds each row up to check it totals 100%. n ={" "}
        {fmtInt(
          // each from-bucket's denominator once, not once per destination cell
          [...new Map(rows.filter((r) => r.period_group === period).map((r) => [r.from_bucket, r.rate.n])).values()].reduce((s, n) => s + n, 0)
        )}{" "}
        loan-months · 95% Wilson intervals
      </p>
    </div>
  );
}
