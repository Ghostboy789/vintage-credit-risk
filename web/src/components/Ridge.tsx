import { useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { line, curveMonotoneX } from "d3-shape";
import { motion } from "framer-motion";
import type { VintageCurveRow } from "../lib/types";
import { useReducedMotion } from "../lib/theme";
import { fmtPct } from "../lib/format";

// The Ridge (design brief signature moment): all annual vintages as a ridgeline of cumulative
// default rate by months on book, 1999 at the back / most recent at front. Skiper19's pathLength
// draw technique (not scroll-scrubbed) reveals each ridge left to right on first view.
// Uses portfolio.json's vintage_curves_annual (one series per origination year).
export function Ridge({ rows }: { rows: VintageCurveRow[] }) {
  const reduced = useReducedMotion();
  const width = 1200;
  const height = 640;

  const { years, xScale, yScale, crisisYears } = useMemo(() => {
    const byYear = new Map<number, VintageCurveRow[]>();
    for (const r of rows) {
      if (!byYear.has(r.vintage_year)) byYear.set(r.vintage_year, []);
      byYear.get(r.vintage_year)!.push(r);
    }
    const years = [...byYear.keys()].sort((a, b) => a - b);
    const maxMonths = Math.max(1, ...rows.map((r) => r.months_on_book));
    const maxRate = Math.max(0.01, ...rows.map((r) => r.cum_default_rate.value ?? 0));
    return {
      years: years.map((y) => ({ year: y, rows: byYear.get(y)!.sort((a, b) => a.months_on_book - b.months_on_book) })),
      xScale: scaleLinear().domain([0, Math.max(120, maxMonths)]).range([80, width - 20]),
      yScale: scaleLinear().domain([0, maxRate]).range([0, 180]),
      crisisYears: new Set([2006, 2007]),
    };
  }, [rows]);

  const baseGap = years.length ? (height - 60) / years.length : 20;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-labelledby="ridge-title ridge-desc"
      className="w-full"
      style={{ background: "var(--bg)" }}
    >
      <title id="ridge-title">Cumulative default rate by vintage year, 1999–2025</title>
      <desc id="ridge-desc">
        A ridgeline of 27 annual vintages by months on book. The 2006 and 2007 vintages rise well above
        every other year in the crisis colour, showing the crisis as it appears in the default data.
      </desc>
      {years.map(({ year, rows: yearRows }, i) => {
        const baseline = 40 + i * baseGap;
        const isCrisis = crisisYears.has(year);
        const gen = line<VintageCurveRow>()
          .x((r: VintageCurveRow) => xScale(r.months_on_book))
          .y((r: VintageCurveRow) => baseline - yScale(r.cum_default_rate.value ?? 0))
          .curve(curveMonotoneX);
        const areaPath = `${gen(yearRows)} L ${xScale(yearRows[yearRows.length - 1]?.months_on_book ?? 0)} ${baseline} L ${xScale(0)} ${baseline} Z`;
        return (
          <g key={year}>
            <path d={areaPath ?? undefined} fill="var(--bg)" />
            {isCrisis && (
              <path
                d={areaPath ?? undefined}
                fill="var(--crisis)"
                opacity={0.12}
              />
            )}
            <motion.path
              d={gen(yearRows) ?? undefined}
              fill="none"
              stroke={isCrisis ? "var(--crisis)" : "var(--ink-muted)"}
              strokeWidth={isCrisis ? 2 : 1.25}
              initial={reduced ? false : { pathLength: 0 }}
              whileInView={reduced ? undefined : { pathLength: 1 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1], delay: i * 0.035 }}
            />
            <text x={20} y={baseline + 4} className="font-mono" fontSize={10} fill="var(--ink-3)">
              {year}
            </text>
            {isCrisis && (
              <text
                x={xScale(yearRows[yearRows.length - 1]?.months_on_book ?? 0) + 6}
                y={baseline - yScale(yearRows[yearRows.length - 1]?.cum_default_rate.value ?? 0) + 4}
                className="font-mono"
                fontSize={11}
                fill="var(--crisis)"
              >
                {fmtPct(yearRows[yearRows.length - 1]?.cum_default_rate.value ?? 0)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
