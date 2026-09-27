import { useEffect, useRef, useState, type PointerEvent } from "react";
import type { VintageCurveRow } from "../lib/types";
import { useReducedMotion, useTheme } from "../lib/theme";
import { fmtInt, fmtPct } from "../lib/format";

const AXIS = 18; // px under the field for the year labels

interface Dot {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  defaulted: boolean;
  column: number;
}

// Rebuild of ThreeUI's Structure Flow "Data Field" (MIT, Community tier) in Canvas2D per the
// brief — no three.js/WebGL anywhere on this site. one dot per 250 loans (1,000 on phones), sorted into one column
// per vintage on view, defaulted share stacked at the top of each column in the crisis colour.
export function LoanField({ rows }: { rows: VintageCurveRow[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const played = useRef(false);
  const [showTable, setShowTable] = useState(false);
  // Column under the pointer, once the field has sorted: that vintage is brightened and read out.
  const [hoverCol, setHoverCol] = useState<number | null>(null);
  const [perDot, setPerDot] = useState(250);
  const reduced = useReducedMotion();
  const { choice } = useTheme();

  // Per vintage year: n_loans approximated from the earliest observed row's at-risk count
  // (almost the whole cohort at month 6), defaulted share from the latest observed row.
  const earliest = new Map<number, VintageCurveRow>();
  const latest = new Map<number, VintageCurveRow>();
  for (const r of rows) {
    const e = earliest.get(r.vintage_year);
    if (!e || r.months_on_book < e.months_on_book) earliest.set(r.vintage_year, r);
    const l = latest.get(r.vintage_year);
    if (!l || r.months_on_book > l.months_on_book) latest.set(r.vintage_year, r);
  }
  const years = [...latest.keys()].sort((a, b) => a - b);
  const nLoansOf = (year: number) => earliest.get(year)?.cum_default_rate.n ?? 0;
  const byYear = latest;

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    // Plays once: after the first sort the field stays sorted.
    const obs = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setVisible(true);
        obs.disconnect();
      }
    }, { threshold: 0.4 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !years.length) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const cssHeight = (window.innerWidth < 768 ? 360 : 480) + AXIS;
    const cssWidth = canvas.parentElement?.clientWidth ?? 1200;
    canvas.width = cssWidth * dpr;
    canvas.height = cssHeight * dpr;
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const grid = 6;
    setPerDot(cssWidth < 700 ? 1000 : 250);
    const perDot = cssWidth < 700 ? 1000 : 250;
    const colWidth = cssWidth / years.length;
    const dots: Dot[] = [];
    let seed = 42;
    const rand = () => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };

    const perCol = Math.floor((cssHeight - AXIS - 20) / grid);
    years.forEach((year, colIdx) => {
      const row = byYear.get(year)!;
      const nDots = Math.max(1, Math.round(nLoansOf(year) / perDot));
      const nDefaulted = Math.round(nDots * (row.cum_default_rate.value ?? 0));
      // Dots fill rows of `sub` across each column: defaulted from the top, the rest from the bottom.
      const sub = Math.max(Math.ceil(nDots / perCol), Math.floor((colWidth - grid) / grid), 1);
      const baseX = colIdx * colWidth + (colWidth - (sub - 1) * grid - 3) / 2;
      const floorY = cssHeight - AXIS - 10;
      for (let i = 0; i < nDots; i++) {
        const x0 = rand() * cssWidth;
        const y0 = rand() * (cssHeight - AXIS);
        const j = i < nDefaulted ? i : i - nDefaulted;
        const x1 = baseX + (j % sub) * grid;
        const y1 = i < nDefaulted ? 10 + Math.floor(j / sub) * grid : floorY - Math.floor(j / sub) * grid;
        dots.push({ x0, y0, x1, y1, defaulted: i < nDefaulted, column: colIdx });
      }
    });

    let raf = 0;
    const start = performance.now();
    const instant = reduced || played.current;
    const duration = 1400;

    const draw = (t: number) => {
      // Read the theme colours at draw time (the theme attribute is set after this effect runs).
      const css = getComputedStyle(document.documentElement);
      const crisis = css.getPropertyValue("--crisis").trim();
      const muted = css.getPropertyValue("--ink-3").trim();
      ctx.clearRect(0, 0, cssWidth, cssHeight);
      const globalT = instant ? 1 : visible ? Math.min(1, (t - start) / duration) : 0;
      if (globalT >= 1) played.current = true;
      for (const d of dots) {
        const colDelay = instant ? 1 : Math.min(1, Math.max(0, (globalT - d.column * 0.015) / 0.6));
        const eased = 1 - Math.pow(1 - colDelay, 3);
        const x = d.x0 + (d.x1 - d.x0) * eased;
        const y = d.y0 + (d.y1 - d.y0) * eased;
        ctx.globalAlpha = hoverCol === null || hoverCol === d.column ? 1 : 0.3;
        ctx.fillStyle = d.defaulted ? crisis : muted;
        ctx.fillRect(x, y, 3, 3);
      }
      ctx.globalAlpha = 1;
      if (globalT >= 1) {
        // Year labels under the columns: every fifth year, the crisis years and the hovered one.
        ctx.font = "11px 'IBM Plex Mono', monospace";
        ctx.textAlign = "center";
        years.forEach((year, i) => {
          const show = hoverCol === null ? year % 5 === 0 || year === 2006 || year === 2007 : i === hoverCol;
          if (!show || (hoverCol !== null && i !== hoverCol)) return;
          ctx.fillStyle = year === 2006 || year === 2007 ? crisis : css.getPropertyValue("--ink-3").trim();
          ctx.fillText(String(year), i * colWidth + colWidth / 2, cssHeight - 4);
        });
      }
      if (globalT < 1 && visible) raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [visible, years.length, reduced, choice, hoverCol]);

  const hovered = hoverCol === null ? null : years[hoverCol];
  const hoveredRow = hovered === null ? null : byYear.get(hovered)!;
  const onMove = (e: PointerEvent<HTMLCanvasElement>) => {
    if (!played.current || e.pointerType === "touch") return;
    const rect = e.currentTarget.getBoundingClientRect();
    const col = Math.floor(((e.clientX - rect.left) / rect.width) * years.length);
    setHoverCol(col >= 0 && col < years.length ? col : null);
  };

  return (
    <div ref={containerRef} className="relative">
      <canvas ref={canvasRef} className="w-full" onPointerMove={onMove} onPointerLeave={() => setHoverCol(null)} aria-hidden />
      <p className="font-mono mt-1 h-5 text-xs" style={{ color: "var(--ink-2)" }} aria-live="polite">
        {hoveredRow
          ? `${hovered} · ${fmtInt(nLoansOf(hovered!))} loans · ${fmtPct(hoveredRow.cum_default_rate.value ?? 0, 1)} defaulted by month ${hoveredRow.months_on_book}`
          : ""}
      </p>
      <p className="mt-2 text-sm" style={{ color: "var(--ink-3)" }}>
        1 dot ≈ {fmtInt(perDot)} loans (rounded, from the earliest observed cohort size). Highlighted: defaulted
        under the primary definition, as observed by the latest months on book reached.
      </p>
      <button
        type="button"
        onClick={() => setShowTable((v) => !v)}
        className="mt-2 rounded border px-2 py-1 text-xs"
        style={{ borderColor: "var(--border)", color: "var(--ink-2)" }}
      >
        {showTable ? "Hide table" : "Show as table"}
      </button>
      {showTable && (
        <table className="mt-2 w-full text-sm">
          <thead>
            <tr style={{ color: "var(--ink-3)" }}>
              <th className="text-left">Vintage</th>
              <th className="text-right">n_loans</th>
              <th className="text-right">Cum. default rate</th>
            </tr>
          </thead>
          <tbody>
            {years.map((y) => {
              const row = byYear.get(y)!;
              return (
                <tr key={y} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td>{y}</td>
                  <td className="tabular text-right">{fmtInt(nLoansOf(y))}</td>
                  <td className="tabular text-right">{((row.cum_default_rate.value ?? 0) * 100).toFixed(2)}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}
