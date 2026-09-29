import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { m } from "framer-motion";
import { useReducedMotion } from "../lib/theme";
import { fmtPct, fmtInt } from "../lib/format";
import type { Estimate } from "../lib/types";
import { codeLabel } from "../lib/labels";

// A reader's name for a segment code; states keep their two-letter code.
const segLabel = (dim: string, seg: string) => (seg === "missing" ? "Unknown" : dim === "property_state" ? seg : codeLabel(seg));
const dimLabel = (dim: string) => (dim === "ltv_band" ? "Loan-to-value band" : dim === "property_state" ? "State" : codeLabel(dim));
const TOP = 10;

interface Row {
  dimension: string;
  segment: string;
  default_rate: Estimate;
  loss_rate: Estimate;
}

export function LossDrivers({ rows }: { rows: Row[] }) {
  const reduced = useReducedMotion();
  const [showTable, setShowTable] = useState(false);
  const [allOf, setAllOf] = useState<Record<string, boolean>>({});

  const dimensions = useMemo(() => [...new Set(rows.map((r) => r.dimension))], [rows]);
  // Every dimension splits the same loans, so n is one dimension's total, not the sum over all of them.
  const totalN = useMemo(() => rows.filter((r) => r.dimension === rows[0]?.dimension).reduce((s, r) => s + (r.default_rate.n ?? 0), 0), [rows]);
  const ciMethod = rows[0]?.default_rate.ci_method ?? "";


  if (showTable) {
    return (
      <div className="relative">
        <button
          onClick={() => setShowTable(false)}
          className="absolute right-0 top-0 rounded border px-4 py-1 text-sm"
          style={{
            borderColor: "var(--border)",
            color: "var(--ink)",
            background: "var(--surface)",
            minHeight: 44,
          }}
        >
          Chart
        </button>
        <div className="overflow-x-auto pt-10">
        <table className="w-full min-w-[520px] border-collapse" role="table">
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border)" }}>
              <th className="text-left font-mono py-2 px-2">Dimension</th>
              <th className="text-left font-mono py-2 px-2">Segment</th>
              <th className="text-right font-mono tabular py-2 px-2">Default rate</th>
              <th className="text-left font-mono tabular py-2 px-2">95% CI</th>
              <th className="text-right font-mono tabular py-2 px-2">Loss rate</th>
              <th className="text-right font-mono tabular py-2 px-2">n</th>
            </tr>
          </thead>
          <tbody>
            {dimensions.map((dim) => {
              // Ordered bands keep their order; unordered segments (states) are ranked by default rate.
          const dimRows = rows.filter((r) => r.dimension === dim);
          if (!/band/.test(dim)) dimRows.sort((a, b) => (b.default_rate.value ?? -1) - (a.default_rate.value ?? -1));
              return dimRows.map((r, i) => (
                <tr key={`${r.dimension}-${r.segment}`} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td className="font-mono py-2 px-2">{i === 0 ? dimLabel(dim) : ""}</td>
                  <td className="font-mono py-2 px-2">{segLabel(r.dimension, r.segment)}</td>
                  <td className="tabular py-2 px-2 text-right">
                    {r.default_rate.value === null ? "—" : fmtPct(r.default_rate.value)}
                  </td>
                  <td className="tabular py-2 px-2 text-left" style={{ color: "var(--ink-3)" }}>
                    {r.default_rate.ci_low !== null && r.default_rate.ci_high !== null
                      ? `[${fmtPct(r.default_rate.ci_low)}–${fmtPct(r.default_rate.ci_high)}]`
                      : "—"}
                  </td>
                  <td className="tabular py-2 px-2 text-right">
                    {r.loss_rate.value === null ? "—" : fmtPct(r.loss_rate.value)}
                  </td>
                  <td className="tabular py-2 px-2 text-right">{fmtInt(r.default_rate.n)}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
        </div>
        <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
          n = {fmtInt(totalN)} loans · {ciMethod} intervals
        </p>
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setShowTable(true)}
        className="absolute right-0 top-0 rounded border px-4 py-1 text-sm"
        style={{
          borderColor: "var(--border)",
          color: "var(--ink)",
          background: "var(--surface)",
          minHeight: 44,
        }}
      >
        Table
      </button>
      <div
        className="grid gap-8 pt-14"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))" }}
      >
        {dimensions.map((dim) => {
          // Ordered bands keep their order; unordered segments (states) are ranked by default rate.
          const allRows = rows.filter((r) => r.dimension === dim);
          if (!/band/.test(dim)) allRows.sort((a, b) => (b.default_rate.value ?? -1) - (a.default_rate.value ?? -1));
          // Long lists (50+ states) show the highest ten until asked; the scale still covers every row.
          const long = allRows.length > TOP + 2;
          const dimRows = long && !allOf[dim] ? allRows.slice(0, TOP) : allRows;
          const maxCiHigh = Math.max(
            0.01,
            ...allRows.map((r) => r.default_rate.ci_high ?? r.default_rate.value ?? 0)
          );
          const panelWidth = 480;
          const rowHeight = 28;
          const panelHeight = dimRows.length * rowHeight + 44;
          const margin = { top: 12, right: 190, bottom: 20, left: 92 };
          const innerWidth = panelWidth - margin.left - margin.right;

          const x = scaleLinear().domain([0, maxCiHigh]).range([0, innerWidth]);

          return (
            <div key={dim} className="overflow-x-auto">
              <h4 className="text-sm font-medium">
                {dimLabel(dim)}
                {long && (
                  <span className="font-normal" style={{ color: "var(--ink-3)" }}>
                    {" "}
                    · {allOf[dim] ? `all ${allRows.length}` : `highest ${TOP} of ${allRows.length}`}, ranked by default rate
                  </span>
                )}
              </h4>
              <svg
                viewBox={`0 0 ${panelWidth} ${panelHeight}`}
                className="h-auto w-full min-w-[480px] max-w-[580px]"
                role="img"
                aria-label={`Lifetime default rate by ${dimLabel(dim).toLowerCase()}, with 95% intervals: ${dimRows
                  .map((r) => `${segLabel(dim, r.segment)} ${r.default_rate.value === null ? "suppressed" : fmtPct(r.default_rate.value, 1)}`)
                  .join(", ")}.`}
              >
                {x.ticks(4).map((t) => (
                  <g key={t}>
                    <text
                      x={margin.left + x(t)}
                      y={panelHeight - margin.bottom + 15}
                      className="font-mono"
                      fontSize={11}
                      fill="var(--ink-3)"
                      textAnchor="middle"
                    >
                      {fmtPct(t, 1)}
                    </text>
                  </g>
                ))}
                {dimRows.map((r, i) => {
                  const y = margin.top + i * rowHeight;
                  const barWidth = x(r.default_rate.value ?? 0);
                  const ciLowX = x(r.default_rate.ci_low ?? 0);
                  const ciHighX = x(r.default_rate.ci_high ?? 0);

                  return (
                    <g key={r.segment}>
                      <text x={4} y={y + 4} fontSize={12} fill="var(--ink)">
                        {segLabel(dim, r.segment)}
                      </text>
                        <m.rect
                          x={margin.left}
                          y={y - 8}
                          width={barWidth}
                          height={16}
                          fill="var(--ink-2)"
                          fillOpacity={0.5}
                          initial={reduced ? false : { width: 0 }}
                          whileInView={{ width: barWidth }}
                          viewport={{ once: true, amount: 0.3 }}
                          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1], delay: i * 0.04 }}
                        />
                      {r.default_rate.ci_low !== null && r.default_rate.ci_high !== null && (
                        <>
                          <line
                            x1={margin.left + ciLowX}
                            x2={margin.left + ciHighX}
                            y1={y}
                            y2={y}
                            stroke="var(--ink)"
                            strokeWidth={1.5}
                          />
                          <line
                            x1={margin.left + ciLowX}
                            x2={margin.left + ciLowX}
                            y1={y - 3}
                            y2={y + 3}
                            stroke="var(--ink)"
                            strokeWidth={1.5}
                          />
                          <line
                            x1={margin.left + ciHighX}
                            x2={margin.left + ciHighX}
                            y1={y - 3}
                            y2={y + 3}
                            stroke="var(--ink)"
                            strokeWidth={1.5}
                          />
                        </>
                      )}
                      <text
                        x={margin.left + innerWidth + 8}
                        y={y - 2}
                        className="font-mono tabular"
                        fontSize={11}
                        fill="var(--ink-3)"
                        textAnchor="start"
                      >
                        {r.default_rate.value === null
                          ? "—"
                          : `${fmtPct(r.default_rate.value, 1)} ${
                              r.default_rate.ci_low !== null && r.default_rate.ci_high !== null
                                ? `[${fmtPct(r.default_rate.ci_low, 1)}–${fmtPct(r.default_rate.ci_high, 1)}]`
                                : ""
                            }`}
                      </text>
                      <text
                        x={margin.left + innerWidth + 8}
                        y={y + 12}
                        className="font-mono tabular"
                        fontSize={10}
                        fill="var(--ink-3)"
                        textAnchor="start"
                      >
                        n = {fmtInt(r.default_rate.n)}
                        {r.loss_rate.value !== null ? ` · loss ${fmtPct(r.loss_rate.value)}` : ""}
                      </text>
                    </g>
                  );
                })}
              </svg>
              {long && (
                <button
                  type="button"
                  aria-expanded={!!allOf[dim]}
                  onClick={() => setAllOf((o) => ({ ...o, [dim]: !o[dim] }))}
                  className="mt-1 min-h-[44px] rounded-full border px-4 text-sm"
                  style={{ borderColor: "var(--border)", color: "var(--ink)" }}
                >
                  {allOf[dim] ? `Show top ${TOP} only` : `Show all ${allRows.length}`}
                </button>
              )}
            </div>
          );
        })}
      </div>
      <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
        n = {fmtInt(totalN)} loans · {ciMethod} intervals
      </p>
    </div>
  );
}