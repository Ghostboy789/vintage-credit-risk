import { useEffect, useRef, useState } from "react";
import type { VintageCurveRow } from "../lib/types";
import { useReducedMotion } from "../lib/theme";

interface Dot {
  x0: number;
  y0: number;
  x1: number;
  y1: number;
  defaulted: boolean;
  column: number;
}

// Rebuild of ThreeUI's Structure Flow "Data Field" (MIT, Community tier) in Canvas2D per the
// brief — no three.js/WebGL anywhere on this site. ~1 dot per 1,000 loans, sorted into 27 vintage
// columns on view, defaulted share stacked at the top of each column in the crisis colour.
export function LoanField({ rows }: { rows: VintageCurveRow[] }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [showTable, setShowTable] = useState(false);
  const reduced = useReducedMotion();

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
    const obs = new IntersectionObserver(([entry]) => setVisible(entry.isIntersecting), { threshold: 0.4 });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !years.length) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 3);
    const cssHeight = window.innerWidth < 768 ? 360 : 480;
    const cssWidth = canvas.parentElement?.clientWidth ?? 1200;
    canvas.width = cssWidth * dpr;
    canvas.height = cssHeight * dpr;
    canvas.style.width = `${cssWidth}px`;
    canvas.style.height = `${cssHeight}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const grid = 6;
    const colWidth = cssWidth / years.length;
    const dots: Dot[] = [];
    let seed = 42;
    const rand = () => {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      return seed / 0x7fffffff;
    };

    years.forEach((year, colIdx) => {
      const row = byYear.get(year)!;
      const nDots = Math.max(1, Math.round(nLoansOf(year) / 1000));
      const nDefaulted = Math.round(nDots * (row.cum_default_rate.value ?? 0));
      for (let i = 0; i < nDots; i++) {
        const x0 = rand() * cssWidth;
        const y0 = rand() * cssHeight;
        const perCol = Math.floor((cssHeight - 20) / grid);
        const localIdx = i % perCol;
        const x1 = colIdx * colWidth + grid + (Math.floor(i / perCol) * grid);
        const y1 = i < nDefaulted ? 10 + localIdx * grid : cssHeight - 10 - localIdx * grid;
        dots.push({ x0, y0, x1, y1, defaulted: i < nDefaulted, column: colIdx });
      }
    });

    let raf = 0;
    const start = performance.now();
    const duration = reduced ? 0 : 1400;

    const draw = (t: number) => {
      ctx.clearRect(0, 0, cssWidth, cssHeight);
      const globalT = visible ? Math.min(1, (t - start) / duration) : 0;
      for (const d of dots) {
        const colDelay = reduced ? 1 : Math.min(1, Math.max(0, (globalT - d.column * 0.015) / 0.6));
        const eased = 1 - Math.pow(1 - colDelay, 3);
        const x = d.x0 + (d.x1 - d.x0) * eased;
        const y = d.y0 + (d.y1 - d.y0) * eased;
        ctx.fillStyle = d.defaulted ? "#ff7849" : "#7d8591";
        ctx.fillRect(x, y, 3, 3);
      }
      if (globalT < 1 && visible && !reduced) raf = requestAnimationFrame(draw);
    };
    if (reduced) draw(start + duration);
    else raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [visible, years.length, reduced]);

  return (
    <div ref={containerRef}>
      <canvas ref={canvasRef} className="w-full" />
      <p className="mt-2 text-sm" style={{ color: "var(--ink-3)" }}>
        1 dot ≈ 1,000 loans (rounded, from the earliest observed cohort size). Highlighted: defaulted
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
                  <td className="tabular text-right">{nLoansOf(y)}</td>
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
