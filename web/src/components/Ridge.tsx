import { useEffect, useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { area, line, curveMonotoneX } from "d3-shape";
import { m } from "framer-motion";
import type { VintageCurveRow } from "../lib/types";
import { useReducedMotion } from "../lib/theme";
import { fmtInt, fmtPct } from "../lib/format";

// The Ridge: every annual vintage as a ridgeline of cumulative default rate by months on book,
// the oldest vintage at the back, the newest at the front. Each ridge is filled with the page
// colour so the ridges in front hide the ones behind. On load each ridge draws left to right
// (months on book passing), one vintage after another in origination order, using the pathLength
// draw technique from skiper-ui.com (skiper19); it is not scroll-scrubbed.
const CRISIS = new Set([2006, 2007]);
const MAX_MOB = 120;

type Pt = { mob: number; rate: number };

function useNarrow() {
  const q = "(max-width: 767px)";
  const [narrow, setNarrow] = useState(() => typeof window !== "undefined" && window.matchMedia(q).matches);
  useEffect(() => {
    const mq = window.matchMedia(q);
    const on = () => setNarrow(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return narrow;
}

export function Ridge({ rows }: { rows: VintageCurveRow[] }) {
  const reduced = useReducedMotion();
  const narrow = useNarrow();
  const W = narrow ? 600 : 1600;
  const H = narrow ? 720 : 640;
  const left = narrow ? 64 : 88;
  const right = narrow ? 24 : 150;
  const top = narrow ? 190 : 200;
  const bottom = narrow ? 24 : 28;
  const peak = narrow ? 170 : 190;
  const labelSize = narrow ? 17 : 13;

  const series = useMemo(() => {
    const byYear = new Map<number, VintageCurveRow[]>();
    for (const r of rows) {
      if (r.months_on_book > MAX_MOB) continue;
      if (!byYear.has(r.vintage_year)) byYear.set(r.vintage_year, []);
      byYear.get(r.vintage_year)!.push(r);
    }
    return [...byYear.entries()]
      .sort(([a], [b]) => a - b)
      .map(([year, yr]) => {
        const sorted = yr.sort((a, b) => a.months_on_book - b.months_on_book);
        const last = sorted[sorted.length - 1];
        // Every ridge starts on its own baseline at month 0 (nobody has defaulted at origination).
        const pts: Pt[] = [{ mob: 0, rate: 0 }, ...sorted.map((r) => ({ mob: r.months_on_book, rate: r.cum_default_rate.value ?? 0 }))];
        return { year, pts, last };
      });
  }, [rows]);

  const maxMob = Math.max(12, ...series.flatMap((s) => s.pts.map((p) => p.mob)));
  const maxRate = Math.max(0.001, ...series.flatMap((s) => s.pts.map((p) => p.rate)));
  const x = scaleLinear().domain([0, maxMob]).range([left, W - right]);
  const h = scaleLinear().domain([0, maxRate]).range([0, peak]);
  const gap = series.length > 1 ? (H - top - bottom) / (series.length - 1) : 0;
  const crisisLast = series.filter((s) => CRISIS.has(s.year)).at(-1);
  const annotate = crisisLast?.last;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby="ridge-title ridge-desc" className="block h-auto w-full">
      <title id="ridge-title">Cumulative default rate by months on book, one ridge per vintage year</title>
      <desc id="ridge-desc">
        A ridgeline of {series.length} annual vintages, oldest at the back. Height is the cumulative default rate
        under the primary definition. The 2006 and 2007 vintages are drawn in the crisis colour.
        {annotate &&
          ` ${annotate.vintage_year} reaches ${fmtPct(annotate.cum_default_rate.value ?? 0)} by month ${annotate.months_on_book}.`}
      </desc>
      <defs>
        <linearGradient id="ridge-crisis" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="var(--crisis)" stopOpacity="0.28" />
          <stop offset="1" stopColor="var(--crisis)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {series.map(({ year, pts }, i) => {
        const base = top + i * gap;
        const crisis = CRISIS.has(year);
        const lineD = line<Pt>().x((p) => x(p.mob)).y((p) => base - h(p.rate)).curve(curveMonotoneX)(pts) ?? "";
        const areaD = area<Pt>().x((p) => x(p.mob)).y0(base).y1((p) => base - h(p.rate)).curve(curveMonotoneX)(pts) ?? "";
        const delay = 0.15 + i * 0.035;
        const everyN = narrow ? 5 : 1;
        const showLabel = crisis || i % everyN === 0 || i === series.length - 1;
        return (
          <g key={year}>
            <path d={areaD} fill="var(--bg)" />
            {crisis && (
              <m.path
                d={areaD}
                fill="url(#ridge-crisis)"
                initial={reduced ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.6, delay: delay + 0.8 }}
              />
            )}
            <line x1={x(0)} x2={x(maxMob)} y1={base} y2={base} stroke="var(--ink-muted)" strokeOpacity={0.35} strokeWidth={1} />
            <m.path
              d={lineD}
              fill="none"
              stroke={crisis ? "var(--crisis)" : "var(--ink-3)"}
              strokeOpacity={crisis ? 1 : 0.55}
              strokeWidth={crisis ? 2.5 : 1.25}
              strokeLinejoin="round"
              initial={reduced ? false : { pathLength: 0 }}
              animate={{ pathLength: 1 }}
              transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1], delay }}
            />
            {showLabel && (
              <text
                x={left - 12}
                y={base + labelSize * 0.35}
                textAnchor="end"
                className="font-mono"
                fontSize={labelSize}
                fontWeight={crisis ? 600 : 400}
                fill={crisis ? "var(--crisis)" : "var(--ink-3)"}
              >
                {year}
              </text>
            )}
          </g>
        );
      })}
      {annotate && crisisLast && (
        <m.g
          initial={reduced ? false : { opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 1.6, ease: [0.16, 1, 0.3, 1] }}
        >
          {(() => {
            const i = series.indexOf(crisisLast);
            const px = x(annotate.months_on_book);
            const py = top + i * gap - h(annotate.cum_default_rate.value ?? 0);
            const e = annotate.cum_default_rate;
            const tx = narrow ? px - 8 : px + 14;
            const anchor = narrow ? "end" : "start";
            const ty = narrow ? py - 40 : py - 6;
            return (
              <>
                <circle cx={px} cy={py} r={narrow ? 5 : 4} fill="var(--crisis)" />
                <text x={tx} y={ty} textAnchor={anchor} className="font-mono" fontSize={narrow ? 18 : 14} fill="var(--crisis)" fontWeight={600}>
                  {annotate.vintage_year}: {fmtPct(e.value ?? 0, 1)}
                </text>
                <text x={tx} y={ty + (narrow ? 22 : 18)} textAnchor={anchor} className="font-mono" fontSize={narrow ? 15 : 12} fill="var(--ink-2)">
                  {e.ci_low !== null && e.ci_high !== null ? `95% CI ${fmtPct(e.ci_low, 1)}–${fmtPct(e.ci_high, 1)}` : e.ci_method}
                </text>
                <text x={tx} y={ty + (narrow ? 42 : 34)} textAnchor={anchor} className="font-mono" fontSize={narrow ? 15 : 12} fill="var(--ink-3)">
                  n = {fmtInt(e.n)} · month {annotate.months_on_book}
                </text>
              </>
            );
          })()}
        </m.g>
      )}
      <text x={x(maxMob)} y={H - 4} textAnchor="end" className="font-mono" fontSize={labelSize - 2} fill="var(--ink-3)">
        months on book →
      </text>
    </svg>
  );
}
