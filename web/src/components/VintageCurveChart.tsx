import { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line, curveMonotoneX } from "d3-shape";
import { m } from "framer-motion";
import type { VintageCurveRow } from "../lib/types";
import { useReducedMotion } from "../lib/theme";
import { ChartTooltip } from "./ChartTooltip";
import { fmtPct, fmtInt } from "../lib/format";

const CRISIS = new Set([2006, 2007]);

export function VintageCurveChart({ rows, comparableMonths }: { rows: VintageCurveRow[]; comparableMonths: number }) {
  const reduced = useReducedMotion();
  const [hover, setHover] = useState<{ x: number; y: number; row: VintageCurveRow } | null>(null);
  const width = 900;
  const height = 420;
  const margin = { top: 16, right: 16, bottom: 28, left: 48 };

  const byYear = useMemo(() => {
    const map = new Map<number, VintageCurveRow[]>();
    for (const r of rows) {
      if (!map.has(r.vintage_year)) map.set(r.vintage_year, []);
      map.get(r.vintage_year)!.push(r);
    }
    for (const arr of map.values()) arr.sort((a, b) => a.months_on_book - b.months_on_book);
    return map;
  }, [rows]);

  const { x, y } = useMemo(() => {
    const maxMonths = Math.max(1, ...rows.map((r) => r.months_on_book));
    const maxRate = Math.max(0.01, ...rows.map((r) => r.cum_default_rate.value ?? 0));
    return {
      x: scaleLinear().domain([0, maxMonths]).range([margin.left, width - margin.right]),
      y: scaleLinear().domain([0, maxRate]).range([height - margin.bottom, margin.top]),
    };
  }, [rows]);

  const gen = line<VintageCurveRow>()
    .x((r: VintageCurveRow) => x(r.months_on_book))
    .y((r: VintageCurveRow) => y(r.cum_default_rate.value ?? 0))
    .curve(curveMonotoneX);

  return (
    <div className="relative">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="curve-title" className="w-full">
        <title id="curve-title">Cumulative default rate by months on book, per origination vintage</title>
        {y.ticks(5).map((t: number) => (
          <g key={t}>
            <line x1={margin.left} x2={width - margin.right} y1={y(t)} y2={y(t)} stroke="var(--ink-muted)" strokeOpacity={0.5} />
            <text x={4} y={y(t) + 4} className="font-mono" fontSize={11} fill="var(--ink-3)">
              {(t * 100).toFixed(0)}%
            </text>
          </g>
        ))}
        <line
          x1={x(comparableMonths)}
          x2={x(comparableMonths)}
          y1={margin.top}
          y2={height - margin.bottom}
          stroke="var(--ink-2)"
          strokeDasharray="4 4"
        />
        <text x={x(comparableMonths) + 4} y={margin.top + 10} fontSize={10} fill="var(--ink-3)">
          All vintages observed to month {comparableMonths}
        </text>
        {[...byYear.entries()].map(([year, yearRows]) => {
          const isCrisis = CRISIS.has(year);
          return (
            <m.path
              key={year}
              d={gen(yearRows) ?? undefined}
              fill="none"
              stroke={isCrisis ? "var(--crisis)" : "var(--ink-muted)"}
              strokeWidth={isCrisis ? 2 : 1}
              strokeDasharray={yearRows.some((r) => !r.fully_observed) ? "3 3" : undefined}
              initial={reduced ? false : { pathLength: 0 }}
              animate={reduced ? undefined : { pathLength: 1 }}
              transition={{ duration: 1, ease: [0.16, 1, 0.3, 1] }}
              style={{ cursor: "pointer" }}
              onMouseMove={(e) => {
                const rect = (e.target as SVGPathElement).ownerSVGElement!.getBoundingClientRect();
                const px = e.clientX - rect.left;
                const nearest = yearRows.reduce((best, r) =>
                  Math.abs(x(r.months_on_book) - px) < Math.abs(x(best.months_on_book) - px) ? r : best
                );
                setHover({ x: x(nearest.months_on_book), y: y(nearest.cum_default_rate.value ?? 0), row: nearest });
              }}
              onMouseLeave={() => setHover(null)}
            />
          );
        })}
      </svg>
      {hover && (
        <ChartTooltip
          x={(hover.x / width) * 100 + "%" === undefined ? 0 : (hover.x / width) * 900}
          y={hover.y}
          label={`${hover.row.vintage_year} · month ${hover.row.months_on_book}`}
          estimate={hover.row.cum_default_rate}
          fmt={fmtPct}
          visible
        />
      )}
      <p className="mt-2 text-sm font-mono" style={{ color: "var(--ink-3)" }}>
        n = {fmtInt(rows.reduce((s, r) => s + (r.cum_default_rate.n ?? 0), 0))} · 95% intervals · one series per vintage year
      </p>
    </div>
  );
}
