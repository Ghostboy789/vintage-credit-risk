import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { m } from "framer-motion";
import { useReducedMotion } from "../lib/theme";
import { fmtPct, fmtInt } from "../lib/format";
import type { Estimate } from "../lib/types";

interface Row {
  dimension: string;
  segment: string;
  default_rate: Estimate;
  loss_rate: Estimate;
}

export function LossDrivers({ rows }: { rows: Row[] }) {
  const reduced = useReducedMotion();
  const [showTable, setShowTable] = useState(false);

  const dimensions = useMemo(() => [...new Set(rows.map((r) => r.dimension))], [rows]);
  const totalN = useMemo(() => rows.reduce((s, r) => s + (r.default_rate.n ?? 0), 0), [rows]);
  const ciMethod = rows[0]?.default_rate.ci_method ?? "";


  if (showTable) {
    return (
      <div className="relative">
        <button
          onClick={() => setShowTable(false)}
          className="absolute right-0 top-0 rounded border px-3 py-1 text-xs"
          style={{
            borderColor: "var(--border)",
            color: "var(--ink)",
            background: "var(--surface)",
            minHeight: 32,
          }}
        >
          Chart
        </button>
        <table className="w-full border-collapse" role="table">
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
              const dimRows = rows.filter((r) => r.dimension === dim);
              return dimRows.map((r, i) => (
                <tr key={`${r.dimension}-${r.segment}`} style={{ borderBottom: "1px solid var(--border)" }}>
                  <td className="font-mono py-2 px-2">{i === 0 ? dim.replace(/_/g, " ") : ""}</td>
                  <td className="font-mono py-2 px-2">{r.segment.replace(/_/g, "–")}</td>
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
        className="absolute right-0 top-0 rounded border px-3 py-1 text-xs"
        style={{
          borderColor: "var(--border)",
          color: "var(--ink)",
          background: "var(--surface)",
          minHeight: 32,
        }}
      >
        Table
      </button>
      <div
        className="grid gap-8"
        style={{ gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 320px), 1fr))" }}
      >
        {dimensions.map((dim) => {
          const dimRows = rows.filter((r) => r.dimension === dim);
          const maxCiHigh = Math.max(
            0.01,
            ...dimRows.map((r) => r.default_rate.ci_high ?? r.default_rate.value ?? 0)
          );
          const panelWidth = 400;
          const rowHeight = 28;
          const panelHeight = Math.max(180, dimRows.length * rowHeight + 60);
          const margin = { top: 36, right: 150, bottom: 20, left: 64 };
          const innerWidth = panelWidth - margin.left - margin.right;

          const x = scaleLinear().domain([0, maxCiHigh]).range([0, innerWidth]);

          return (
            <div key={dim}>
              <svg
                viewBox={`0 0 ${panelWidth} ${panelHeight}`}
                className="h-auto w-full max-w-[560px]"
                role="img"
                aria-label={`Lifetime default rate by ${dim.replace(/_/g, " ")}, with 95% intervals: ${dimRows
                  .map((r) => `${r.segment.replace(/_/g, "–")} ${r.default_rate.value === null ? "suppressed" : fmtPct(r.default_rate.value, 1)}`)
                  .join(", ")}.`}
              >
                <text
                  x={margin.left}
                  y={margin.top - 10}
                  className="font-mono"
                  fontSize={10}
                  fill="var(--ink-3)"
                  style={{ textTransform: "uppercase" }}
                >
                  {dim.replace(/_/g, " ")}
                </text>
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
                      <text x={4} y={y + 4} className="font-mono" fontSize={11} fill="var(--ink-3)">
                        {r.segment.replace(/_/g, "–")}
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