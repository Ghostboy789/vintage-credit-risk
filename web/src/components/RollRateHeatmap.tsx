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
      <div className="mb-3 flex flex-wrap gap-2">
        {periods.map((p) => (
          <button
            key={p}
            onClick={() => setPeriod(p)}
            className="rounded-full border px-3 py-1 text-xs capitalize"
            style={{
              borderColor: "var(--border)",
              background: p === period ? "var(--accent)" : "transparent",
              color: p === period ? "var(--bg)" : "var(--ink-2)",
            }}
          >
            {p.replace(/_/g, " ")}
          </button>
        ))}
      </div>
      <div className="relative overflow-x-auto">
        <table className="border-collapse text-xs">
          <thead>
            <tr>
              <th className="p-1 text-left" style={{ color: "var(--ink-3)" }}>
                from \ to
              </th>
              {toStates.map((t) => (
                <th key={t} className="font-mono p-1 text-center" style={{ color: "var(--ink-3)", minWidth: cell }}>
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {FROM_ORDER.map((from) => {
              const rowSum = toStates.reduce((s, t) => s + (cells.get(`${from}|${t}`)?.rate.value ?? 0), 0);
              return (
                <tr key={from}>
                  <td className="font-mono p-1" style={{ color: "var(--ink-2)" }}>
                    {from}
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
            label={`${hover.row.from_bucket} → ${hover.row.to_state}`}
            estimate={hover.row.rate}
            fmt={fmtPct}
            visible
          />
        )}
      </div>
      <p className="mt-2 text-sm font-mono" style={{ color: "var(--ink-3)" }}>
        Row-sum column checks 100%. n = {fmtInt(rows.filter((r) => r.period_group === period).reduce((s, r) => s + r.rate.n, 0))}
      </p>
    </div>
  );
}
