import { useId, useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { m } from "framer-motion";
import { useReducedMotion } from "../lib/theme";
import { fmtInt } from "../lib/format";
import type { Estimate } from "../lib/types";

const CRISIS = new Set([2006, 2007]);

interface Row {
  vintage_year: number;
  defaults_12m_primary: Estimate;
  defaults_12m_naive: Estimate;
}

export function DefinitionDumbbell({ rows }: { rows: Row[] }) {
  const reduced = useReducedMotion();
  const [showTable, setShowTable] = useState(false);
  const titleId = useId();
  const descId = useId();

  const sorted = useMemo(() => [...rows].sort((a, b) => a.vintage_year - b.vintage_year), [rows]);

  const maxVal = useMemo(() =>
    Math.max(
      1,
      ...sorted.flatMap((r) => [
        r.defaults_12m_primary.value ?? 0,
        r.defaults_12m_naive.value ?? 0,
      ])
    ),
    [sorted]
  );

  const totalN = useMemo(() =>
    sorted.reduce((s, r) => s + (r.defaults_12m_primary.n ?? 0), 0),
    [sorted]
  );

  const width = 700;
  const height = Math.max(200, sorted.length * 18 + 60);
  const margin = { top: 40, right: 120, bottom: 20, left: 80 };
  const innerWidth = width - margin.left - margin.right;

  const x = scaleLinear().domain([0, maxVal]).range([0, innerWidth]);

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
              <th className="text-left font-mono py-2 px-2">Vintage</th>
              <th className="text-right font-mono tabular py-2 px-2">Primary</th>
              <th className="text-right font-mono tabular py-2 px-2">Naive</th>
              <th className="text-right font-mono tabular py-2 px-2">Difference</th>
              <th className="text-right font-mono tabular py-2 px-2">n</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr key={r.vintage_year} style={{ borderBottom: "1px solid var(--border)" }}>
                <td className="font-mono py-2 px-2">{r.vintage_year}</td>
                <td className="tabular py-2 px-2 text-right">
                  {r.defaults_12m_primary.value === null ? "—" : fmtInt(r.defaults_12m_primary.value)}
                </td>
                <td className="tabular py-2 px-2 text-right">
                  {r.defaults_12m_naive.value === null ? "—" : fmtInt(r.defaults_12m_naive.value)}
                </td>
                <td className="tabular py-2 px-2 text-right" style={{ color: "var(--ink-3)" }}>
                  {r.defaults_12m_primary.value !== null && r.defaults_12m_naive.value !== null
                    ? `${r.defaults_12m_naive.value - r.defaults_12m_primary.value > 0 ? "+" : ""}${
                        r.defaults_12m_naive.value - r.defaults_12m_primary.value
                      }`
                    : "—"}
                </td>
                <td className="tabular py-2 px-2 text-right">{fmtInt(r.defaults_12m_primary.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
          n = {fmtInt(totalN)} loans · counts, no interval (population counts)
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
      <div className="chart-x"><svg
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby={titleId}
        aria-describedby={descId}
        className="w-full h-auto"
      >
        <title id={titleId}>Defaults within 12 months: primary vs naive definition per vintage</title>
        <desc id={descId}>
          Defaults within 12 months per vintage under the primary and the naive definition. The naive count is
          higher in {sorted.filter((r) => (r.defaults_12m_naive.value ?? 0) > (r.defaults_12m_primary.value ?? 0)).length} of{" "}
          {sorted.length} vintages.
        </desc>
        <text x={margin.left} y={margin.top - 8} className="font-mono" fontSize={11} fill="var(--ink-3)">
          ● primary   ○ naive
        </text>
        {sorted.map((r, i) => {
          const y = margin.top + i * 18;
          const primaryX = x(r.defaults_12m_primary.value ?? 0);
          const naiveX = x(r.defaults_12m_naive.value ?? 0);
          const isCrisis = CRISIS.has(r.vintage_year);
          const lineColor = isCrisis ? "var(--crisis)" : "var(--ink-muted)";
          const dotColor = isCrisis ? "var(--crisis)" : "var(--ink)";
          const diff = r.defaults_12m_primary.value !== null && r.defaults_12m_naive.value !== null
            ? r.defaults_12m_naive.value - r.defaults_12m_primary.value
            : null;

          return (
            <g key={r.vintage_year}>
              <text x={4} y={y + 4} className="font-mono" fontSize={11} fill="var(--ink-3)">
                {r.vintage_year}
              </text>
              <m.line
                x1={margin.left + primaryX}
                x2={margin.left + naiveX}
                y1={y}
                y2={y}
                stroke={lineColor}
                strokeWidth={2}
                initial={reduced ? false : { x2: margin.left + primaryX }}
                whileInView={{ x2: margin.left + naiveX }}
                viewport={{ once: true, amount: 0.2 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1], delay: i * 0.02 }}
              />
              <circle
                cx={margin.left + primaryX}
                cy={y}
                r={4}
                fill={dotColor}
              />
              <circle
                cx={margin.left + naiveX}
                cy={y}
                r={4}
                fill="none"
                stroke="var(--ink-2)"
                strokeWidth={2}
              />
              {diff !== null && (
                <text
                  x={width - margin.right + 16}
                  y={y + 4}
                  className="font-mono tabular"
                  fontSize={11}
                  fill="var(--ink-3)"
                  textAnchor="start"
                >
                  {diff > 0 ? "+" : ""}{diff}
                </text>
              )}
            </g>
          );
        })}
      </svg></div>
      <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
        n = {fmtInt(totalN)} loans · counts, no interval (population counts)
      </p>
    </div>
  );
}