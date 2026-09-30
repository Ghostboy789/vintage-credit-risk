import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { scaleLinear } from "d3-scale";
import { area, curveMonotoneX, line } from "d3-shape";
import { Delaunay } from "d3-delaunay";
import { m } from "framer-motion";
import type { Estimate, VintageCurveRow } from "../lib/types";
import { COMPARE_MOB, byYear } from "../lib/vintage";
import { useReducedMotion } from "../lib/theme";
import { fmtInt, fmtPct } from "../lib/format";
import { ChartTooltip } from "./ChartTooltip";

// Wide and phone geometries: a narrower viewBox on phones keeps text and lines legible.
const WIDE = { W: 900, H: 480 };
const NARROW = { W: 520, H: 420 };
const M = { top: 20, right: 64, bottom: 36, left: 52 };
const NO_EST: Estimate = { value: null, ci_low: null, ci_high: null, n: 0, ci_method: "" };

const span = (a: number, b: number) => Array.from({ length: b - a + 1 }, (_, i) => a + i);
const PRESETS: { name: string; years: number[] }[] = [
  { name: "Crisis 2006–07", years: [2006, 2007] },
  { name: "Pre-crisis 1999–2005", years: span(1999, 2005) },
  { name: "Post-crisis 2010–19", years: span(2010, 2019) },
  { name: "COVID 2020–21", years: [2020, 2021] },
  { name: "All", years: [] },
];
const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(v, Math.max(lo, hi)));

type Pt = { x: number; y: number; mob: number; row: VintageCurveRow };
type Series = { year: number; rows: VintageCurveRow[]; pts: Pt[]; solid: string | null; dash: string | null };
type Props = { rows: VintageCurveRow[]; highlight?: number[]; showPresets?: boolean; maxMob?: number; annotate?: number; caption?: boolean; tableToggle?: boolean };

export function VintageCurveChart({ rows, highlight, showPresets, maxMob: maxMobProp, annotate, caption, tableToggle }: Props) {
  const reduced = useReducedMotion();
  const uid = useId();
  const [preset, setPreset] = useState<number[]>([2006, 2007]);
  const [hover, setHover] = useState<{ year: number; row: VintageCurveRow } | null>(null);
  const [table, setTable] = useState(false);
  const [box, setBox] = useState({ w: WIDE.W, h: WIDE.H });
  const { W, H } = box.w < 640 ? NARROW : WIDE;
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => {
      const r = el.getBoundingClientRect();
      setBox({ w: r.width, h: r.height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [table]);

  // Keep chart text near 11 px on screen however wide the chart renders.
  const fs = Math.round(clamp((11 * W) / Math.max(1, box.w), 11, 20));
  const MB = fs * 2 + 14; // room for the tick row and the axis title
  const maxMob = Math.max(1, maxMobProp ?? Math.max(0, ...rows.map((r) => r.months_on_book)));

  const { series, x, y } = useMemo(() => {
    const xs = scaleLinear().domain([0, maxMob]).range([M.left, W - M.right]);
    const inRange = rows.filter((r) => r.months_on_book <= maxMob);
    const ys = scaleLinear()
      .domain([0, Math.max(0.001, ...inRange.map((r) => r.cum_default_rate.value ?? 0))])
      .range([H - MB, M.top])
      .nice();
    const gen = line<VintageCurveRow>()
      .defined((r) => r.cum_default_rate.value !== null)
      .x((r) => xs(r.months_on_book))
      .y((r) => ys(r.cum_default_rate.value ?? 0))
      .curve(curveMonotoneX);
    return {
      x: xs,
      y: ys,
      series: [...byYear(inRange)].map(([year, yr]): Series => {
        const split = yr.findIndex((r) => !r.fully_observed);
        return {
          year,
          rows: yr,
          pts: yr
            .filter((r) => r.cum_default_rate.value !== null)
            .map((r) => ({ x: xs(r.months_on_book), y: ys(r.cum_default_rate.value ?? 0), mob: r.months_on_book, row: r })),
          solid: gen(split < 0 ? yr : yr.slice(0, split + 1)),
          dash: split < 0 ? null : gen(yr.slice(split)),
        };
      }),
    };
  }, [rows, maxMob, MB, W, H]);

  const band = useMemo(
    () =>
      area<VintageCurveRow>()
        .defined((r) => r.cum_default_rate.ci_low !== null && r.cum_default_rate.ci_high !== null)
        .x((r) => x(r.months_on_book))
        .y0((r) => y(r.cum_default_rate.ci_low ?? 0))
        .y1((r) => y(r.cum_default_rate.ci_high ?? 0))
        .curve(curveMonotoneX),
    [x, y]
  );

  const flat = useMemo(() => series.flatMap((s) => s.pts.map((p) => ({ x: p.x, y: p.y, year: s.year, row: p.row }))), [series]);
  const delaunay = useMemo(() => Delaunay.from(flat, (p) => p.x, (p) => p.y), [flat]);

  const focus = highlight ?? preset;
  const focusSet = useMemo(() => new Set(focus), [focus]);
  const bands = useMemo(() => {
    const set = new Set(focus.filter((yr) => series.some((s) => s.year === yr)));
    if (hover && !set.has(hover.year)) set.add(hover.year);
    return [...set]
      .map((yr) => ({ colour: hover?.year === yr ? "var(--accent)" : "var(--crisis)", d: band(series.find((s) => s.year === yr)?.rows ?? []) }))
      .filter((b) => b.d);
  }, [focus, hover, series, band]);

  // End labels of the focus vintages, pushed apart so two of them never print on top of each other.
  const labels = useMemo(() => {
    const out: { year: number; x: number; ly: number }[] = [];
    let prev = -Infinity;
    const ends = series.filter((s) => focusSet.has(s.year) && s.pts.length).sort((a, b) => a.pts.at(-1)!.y - b.pts.at(-1)!.y);
    for (const s of ends) {
      const p = s.pts[s.pts.length - 1];
      const ly = Math.max(p.y, prev + fs + 1);
      prev = ly;
      out.push({ year: s.year, x: p.x, ly });
    }
    // Keep the stack above the "compared at" note on the x-axis: push it back up from the bottom.
    let floor = H - MB - fs * 2;
    for (let i = out.length - 1; i >= 0; i--) {
      out[i].ly = Math.min(out[i].ly, floor);
      floor = out[i].ly - fs - 1;
    }
    return out;
  }, [series, focusSet, fs, H, MB]);

  const ns = series.map((s) => s.rows[0]?.cum_default_rate.n ?? 0);
  const nText = ns.length === 0 ? "—" : Math.min(...ns) === Math.max(...ns) ? fmtInt(ns[0]) : `${fmtInt(Math.min(...ns))}–${fmtInt(Math.max(...ns))}`;
  // Only a fully observed row is compared across vintages.
  const at = (s: Series, mob: number) => s.rows.find((r) => r.months_on_book === mob && r.fully_observed);
  const top = series
    .map((s) => ({ year: s.year, row: at(s, COMPARE_MOB) }))
    .filter((a): a is { year: number; row: VintageCurveRow } => !!a.row && a.row.cum_default_rate.value !== null)
    .sort((a, b) => (b.row.cum_default_rate.value ?? 0) - (a.row.cum_default_rate.value ?? 0))[0];
  const annRow = annotate === undefined ? undefined : series.find((s) => s.year === annotate && at(s, COMPARE_MOB))?.rows.find((r) => r.months_on_book === COMPARE_MOB);
  const hx = hover ? x(hover.row.months_on_book) : 0;
  const hy = hover ? y(hover.row.cum_default_rate.value ?? 0) : 0;
  const xticks: number[] = [];
  for (let mob = 0; mob <= maxMob; mob += maxMob > 200 ? 60 : 24) xticks.push(mob);

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const ctm = svgRef.current?.getScreenCTM();
    if (!ctm || !flat.length) return setHover(null);
    const p = new DOMPoint(e.clientX, e.clientY).matrixTransform(ctm.inverse());
    const i = delaunay.find(p.x, p.y);
    if (i < 0) return setHover(null);
    const hit = flat[i];
    setHover((h) => (h && h.row === hit.row ? h : { year: hit.year, row: hit.row }));
  };

  const firstFocus = (): { year: number; row: VintageCurveRow } | null => {
    const s = series[focus.findIndex((yr) => series.some((q) => q.year === yr))] ?? series[0];
    if (!s) return null;
    const row = s.pts.find((p) => p.mob === COMPARE_MOB)?.row ?? s.pts.at(-1)?.row;
    return row ? { year: s.year, row } : null;
  };

  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === "Escape") return setHover(null);
    if (!series.length) return;
    const i = hover ? series.findIndex((s) => s.year === hover.year) : focus.findIndex((yr) => series.some((s) => s.year === yr));
    const s0 = series[i] ?? series[0];
    if (!hover) return setHover(firstFocus());
    if (!e.key.startsWith("Arrow")) return;
    e.preventDefault();
    if (e.key === "ArrowUp" || e.key === "ArrowDown") {
      const s = series[clamp(i + (e.key === "ArrowDown" ? 1 : -1), 0, series.length - 1)];
      if (!s.pts.length) return;
      const mob = hover.row.months_on_book;
      const p = s.pts.reduce((b, q) => (Math.abs(q.mob - mob) < Math.abs(b.mob - mob) ? q : b));
      return setHover({ year: s.year, row: p.row });
    }
    const p = s0.pts[clamp(s0.pts.findIndex((q) => q.row === hover.row) + (e.key === "ArrowRight" ? 1 : -1), 0, s0.pts.length - 1)];
    if (p) setHover({ year: s0.year, row: p.row });
  };

  const chip = (on: boolean) => ({
    borderColor: on ? "var(--accent)" : "var(--border)",
    background: on ? "color-mix(in srgb, var(--accent) 14%, transparent)" : "transparent",
    color: on ? "var(--ink)" : "var(--ink-2)",
  });

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        {showPresets !== false && (
          <div className="flex flex-wrap gap-2" role="group" aria-label="Highlight vintages">
            {PRESETS.map((p) => {
              const on = p.years.length === focus.length && p.years.every((yr) => focusSet.has(yr));
              return (
                <button key={p.name} type="button" aria-pressed={on} onClick={() => setPreset(p.years)} className="min-h-[44px] rounded-full border px-3 text-sm transition-colors" style={chip(on)}>
                  {p.name}
                </button>
              );
            })}
          </div>
        )}
        {tableToggle !== false && <button type="button" aria-pressed={table} onClick={() => setTable((v) => !v)} className="ml-auto min-h-[44px] rounded-full border px-4 text-sm" style={{ borderColor: table ? "var(--accent)" : "var(--border)", color: table ? "var(--ink)" : "var(--ink-2)" }}>
          {table ? "Chart" : "Table"}
        </button>}
      </div>

      <div className="relative">
        {table ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <caption className="sr-only">Cumulative default rate per vintage year at month {COMPARE_MOB} and at the last month observed</caption>
              <thead>
                <tr className="text-left" style={{ background: "var(--surface-2)", color: "var(--ink-3)" }}>
                  {["Vintage", `Rate at m${COMPARE_MOB}`, "95% CI", "n", "Last mob", "Rate at last mob"].map((h) => (
                    <th key={h} scope="col" className="px-2 py-2">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {series.map((s) => {
                  const cmp = at(s, COMPARE_MOB);
                  const e = cmp && cmp.fully_observed && cmp.cum_default_rate.value !== null ? cmp.cum_default_rate : null;
                  const last = s.rows[s.rows.length - 1];
                  const ci = e && e.ci_low !== null && e.ci_high !== null ? `${fmtPct(e.ci_low)} – ${fmtPct(e.ci_high)}` : "—";
                  return (
                    <tr key={s.year} className="tabular font-mono border-t" style={{ borderColor: "var(--border)" }}>
                      <th scope="row" className="px-2 py-1.5 text-left font-normal">{s.year}</th>
                      <td className="px-2 py-1.5">{e ? fmtPct(e.value ?? 0) : "—"}</td>
                      <td className="px-2 py-1.5">{ci}</td>
                      <td className="px-2 py-1.5">{e ? fmtInt(e.n) : "—"}</td>
                      <td className="px-2 py-1.5">{last ? last.months_on_book : "—"}</td>
                      <td className="px-2 py-1.5">{last?.cum_default_rate.value != null ? fmtPct(last.cum_default_rate.value) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <svg
            ref={svgRef}
            viewBox={`0 0 ${W} ${H}`}
            role="img"
            tabIndex={0}
            aria-labelledby={`${uid}t ${uid}d`}
            className="block h-auto w-full"
            onKeyDown={onKey}
            onFocus={() => !hover && setHover(firstFocus())}
            onBlur={() => setHover(null)}
          >
            <title id={`${uid}t`}>Cumulative default rate by months on book, one line per origination vintage</title>
            <desc id={`${uid}d`}>
              {series.length} vintage curves out to month {maxMob}.{" "}
              {top ? `The highest at month ${COMPARE_MOB} is ${top.year} at ${fmtPct(top.row.cum_default_rate.value ?? 0)}.` : `No vintage is fully observed to month ${COMPARE_MOB}, so nothing is compared there.`} Use the arrow keys: up and
              down change vintage, left and right move along months on book.
            </desc>

            {y.ticks(5).map((t) => (
              <g key={t}>
                <line x1={M.left} x2={W - M.right} y1={y(t)} y2={y(t)} stroke="var(--ink-muted)" strokeOpacity={0.5} />
                <text x={M.left - 8} y={y(t) + 4} textAnchor="end" className="font-mono tabular" fontSize={fs} fill="var(--ink-3)">{fmtPct(t, y.domain()[1] < 0.05 ? 1 : 0)}</text>
              </g>
            ))}
            {xticks.map((t) => (
              <text key={t} x={x(t)} y={H - MB + 6 + fs} textAnchor="middle" className="font-mono tabular" fontSize={fs} fill="var(--ink-3)">{t}</text>
            ))}
            <text x={W - M.right} y={H - 4} textAnchor="end" className="font-mono" fontSize={fs} fill="var(--ink-3)">months on book</text>
            <line x1={x(COMPARE_MOB)} x2={x(COMPARE_MOB)} y1={M.top} y2={H - MB} stroke="var(--ink-3)" strokeDasharray="4 4" />
            <text x={x(COMPARE_MOB) + 4} y={H - MB - 6} textAnchor="start" className="font-mono" fontSize={fs} fill="var(--ink-3)" stroke="var(--bg)" strokeWidth={4} paintOrder="stroke">compared at month {COMPARE_MOB}</text>

            {bands.map((b, i) => (
              <path key={i} d={b.d!} fill={b.colour} fillOpacity={0.14} pointerEvents="none" />
            ))}

            {series.map((s, i) => {
              const isH = hover?.year === s.year;
              const isF = focusSet.has(s.year);
              const op = hover ? (isH ? 1 : 0.2) : isF ? 1 : focusSet.size ? 0.35 : 0.6;
              const common = { fill: "none", stroke: isH ? "var(--accent)" : isF ? "var(--crisis)" : "var(--ink-3)", strokeWidth: isH ? 2.5 : isF ? 2.25 : 1, strokeOpacity: op, strokeLinejoin: "round" as const, pointerEvents: "none" as const };
              return (
                <g key={s.year}>
                  {s.solid && <m.path d={s.solid} {...common} style={reduced ? undefined : { transition: "stroke-opacity 400ms, stroke 300ms, stroke-width 300ms" }} initial={reduced ? false : { pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1], delay: 0.03 * i }} />}
                  {s.dash && <m.path d={s.dash} {...common} strokeDasharray="3 3" initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.5, delay: 1.0 }} />}
                </g>
              );
            })}

            {labels.map((l) => (
              <text key={l.year} x={l.x + 6} y={l.ly + 4} className="font-mono tabular" fontSize={fs} fill="var(--crisis)">{l.year}</text>
            ))}

            {annRow && (() => {
              const e = annRow.cum_default_rate;
              const px = x(COMPARE_MOB);
              const py = y(e.value ?? 0);
              const halo = { stroke: "var(--bg)", strokeWidth: 4, paintOrder: "stroke" as const };
              return (
                <m.g key={annotate} pointerEvents="none" initial={reduced ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, delay: 0.15 }}>
                  <circle cx={px} cy={py} r={3.5} fill="var(--crisis)" />
                  <text x={px - 8} y={py - 8 - fs} textAnchor="end" className="font-mono tabular" fontSize={fs} fill="var(--crisis)" {...halo}>{fmtPct(e.value ?? 0, 1)}</text>
                  <text x={px - 8} y={py - 6} textAnchor="end" className="font-mono tabular" fontSize={fs} fill="var(--crisis)" {...halo}>
                    {e.ci_low !== null && e.ci_high !== null ? `95% CI ${fmtPct(e.ci_low, 1)}–${fmtPct(e.ci_high, 1)}` : "95% CI —"}
                  </text>
                </m.g>
              );
            })()}

            {hover && (
              <g pointerEvents="none">
                <line x1={hx} x2={hx} y1={M.top} y2={H - MB} stroke="var(--ink-3)" strokeOpacity={0.4} />
                <circle cx={hx} cy={hy} r={4} fill="var(--accent)" stroke="var(--bg)" strokeWidth={2} />
              </g>
            )}
            <rect x={M.left} y={M.top} width={W - M.left - M.right} height={H - M.top - MB} fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)} />
          </svg>
        )}
        <ChartTooltip
          x={clamp((hx * box.w) / W, 120, box.w - 120)}
          y={(hy * box.h) / H}
          label={hover ? `${hover.year} · month ${hover.row.months_on_book}` : ""}
          estimate={hover?.row.cum_default_rate ?? NO_EST}
          fmt={(v) => fmtPct(v, 2)}
          visible={!!hover && !table}
        />
      </div>

      {caption !== false && (
        <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
          n = {nText} loans per vintage · 95% Wilson intervals · dashed: not every loan observed that long
        </p>
      )}
    </div>
  );
}
