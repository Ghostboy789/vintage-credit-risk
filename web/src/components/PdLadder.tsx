import { useId, useState } from "react";
import { m } from "framer-motion";
import { scaleLog } from "d3-scale";
import type { Grade, Estimate } from "../lib/types";
import { ResultBadge } from "./ResultBadge";
import { fmtPct, fmtInt } from "../lib/format";
import { useReducedMotion } from "../lib/theme";

interface Cal {
  grade: string;
  n: number;
  mean_pd: number;
  realised_rate: Estimate;
  result: string;
}

const scoreText = (g: Grade) =>
  g.score_min !== null && g.score_max !== null
    ? `${g.score_min}–${g.score_max}`
    : g.score_min !== null
      ? `≥ ${g.score_min}`
      : g.score_max !== null
        ? `≤ ${g.score_max}`
        : "—";

const TICKS = [1e-4, 1e-3, 1e-2, 1e-1, 1];
const tickLabel = (t: number) => (t >= 0.01 ? `${t * 100}%` : `${+(t * 100).toFixed(2)}%`);

// The master scale as a ladder: each grade's PD band on a log axis, with the predicted (diamond)
// and realised (dot + Jeffreys whisker) default rate. The calculator's grade is highlighted.
export function PdLadder({ grades, calibration, activeGrade }: { grades: Grade[]; calibration: Cal[]; activeGrade?: string }) {
  const reduced = useReducedMotion();
  const [table, setTable] = useState(false);
  const id = useId();
  const row = 44;
  const top = 24;
  const W = 720;
  const H = grades.length * row + top + 32;
  const x = scaleLog().domain([1e-4, 1]).range([48, W - 190]).clamp(true);
  const cal = new Map(calibration.map((c) => [c.grade, c]));
  const active = grades.findIndex((g) => g.grade === activeGrade || g.merged_into === activeGrade);
  const flagged = calibration.filter((c) => c.result === "FAIL").map((c) => c.grade);

  return (
    <div>
      <div className="mb-2 flex justify-end">
        <button
          type="button"
          onClick={() => setTable((t) => !t)}
          className="min-h-[32px] rounded border px-3 text-xs"
          style={{ borderColor: "var(--border)", color: "var(--ink-2)" }}
        >
          {table ? "Chart" : "Table"}
        </button>
      </div>
      {table ? (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: "var(--ink-3)" }} className="text-left">
                <th className="py-2 pr-3">Grade</th>
                <th className="pr-3">PD range</th>
                <th className="pr-3">Score range</th>
                <th className="pr-3">Mean PD</th>
                <th className="pr-3">Realised [95% CI]</th>
                <th className="pr-3">n</th>
                <th>Result</th>
              </tr>
            </thead>
            <tbody>
              {grades.map((g) => {
                const c = cal.get(g.grade);
                const r = c?.realised_rate;
                return (
                  <tr key={g.grade} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="font-mono py-2 pr-3">
                      {g.grade}
                      {g.merged_into ? ` → ${g.merged_into}` : ""}
                    </td>
                    <td className="tabular pr-3">
                      {fmtPct(g.pd_low)} – {fmtPct(g.pd_high)}
                    </td>
                    <td className="tabular pr-3">{scoreText(g)}</td>
                    <td className="tabular pr-3">{c ? fmtPct(c.mean_pd) : "—"}</td>
                    <td className="tabular pr-3">
                      {r && r.value !== null ? `${fmtPct(r.value)} [${fmtPct(r.ci_low ?? 0)}–${fmtPct(r.ci_high ?? 0)}]` : "—"}
                    </td>
                    <td className="tabular pr-3">{c ? fmtInt(c.n) : "—"}</td>
                    <td>{c ? <ResultBadge result={c.result} /> : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="chart-x"><svg viewBox={`0 0 ${W} ${H}`} role="img" aria-labelledby={`${id}-t ${id}-d`} className="h-auto w-full">
          <title id={`${id}-t`}>PD master scale by grade, with predicted and realised default rates</title>
          <desc id={`${id}-d`}>
            {grades.length} grades from {grades[0]?.grade} (lowest PD) to {grades.at(-1)?.grade} (highest). Calibration is shown for{" "}
            {calibration.length} grades on the test sample{flagged.length ? `; grades ${flagged.join(", ")} fail the calibration rule` : ""}.
            {activeGrade ? ` The calculator's loan is in grade ${activeGrade}.` : ""}
          </desc>
          {active >= 0 && (
            <m.rect
              x={4}
              width={W - 8}
              height={row - 6}
              rx={8}
              fill="color-mix(in srgb, var(--accent) 12%, transparent)"
              stroke="var(--accent)"
              initial={false}
              animate={{ y: top + active * row + 1 }}
              transition={reduced ? { duration: 0 } : { duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            />
          )}
          {grades.map((g, i) => {
            const y = top + i * row + row / 2 - 2;
            const c = cal.get(g.grade);
            const r = c?.realised_rate;
            const x0 = x(Math.max(1e-4, g.pd_low));
            const x1 = x(Math.min(1, g.pd_high));
            const isActive = i === active;
            return (
              <m.g
                key={g.grade}
                initial={reduced ? false : { opacity: 0 }}
                whileInView={{ opacity: 1 }}
                viewport={{ once: true, amount: 0.2 }}
                transition={{ duration: 0.3, delay: i * 0.06 }}
              >
                <text x={16} y={y + 6} className="font-display" fontSize={18} fill="var(--ink)">
                  {g.grade}
                </text>
                <rect
                  x={x0}
                  y={y - 7}
                  width={Math.max(2, x1 - x0)}
                  height={14}
                  rx={4}
                  fill={isActive ? "color-mix(in srgb, var(--accent) 30%, transparent)" : "var(--surface-2)"}
                  stroke={isActive ? "var(--accent)" : "var(--border)"}
                />
                {c && (
                  <path
                    d={`M${x(c.mean_pd)} ${y - 6} l6 6 l-6 6 l-6 -6 z`}
                    fill="var(--surface)"
                    stroke="var(--ink)"
                    strokeWidth={1.5}
                  />
                )}
                {r && r.value !== null && (
                  <g stroke="var(--ink)" strokeWidth={1.5}>
                    {r.ci_low !== null && r.ci_high !== null && (
                      <>
                        <line x1={x(Math.max(1e-4, r.ci_low))} x2={x(r.ci_high)} y1={y} y2={y} />
                        <line x1={x(Math.max(1e-4, r.ci_low))} x2={x(Math.max(1e-4, r.ci_low))} y1={y - 4} y2={y + 4} />
                        <line x1={x(r.ci_high)} x2={x(r.ci_high)} y1={y - 4} y2={y + 4} />
                      </>
                    )}
                    <circle cx={x(Math.max(1e-4, r.value))} cy={y} r={4} fill="var(--ink)" stroke="none" />
                  </g>
                )}
                <text x={W - 12} y={y - 2} textAnchor="end" className="font-mono" fontSize={11} fill={isActive ? "var(--accent)" : "var(--ink-3)"}>
                  {isActive ? "your loan · " : ""}score {scoreText(g)}
                </text>
                <text x={W - 12} y={y + 12} textAnchor="end" className="font-mono" fontSize={11} fill="var(--ink-3)">
                  {g.merged_into ? `merged into ${g.merged_into}` : c ? `n = ${fmtInt(c.n)}` : ""}
                </text>
              </m.g>
            );
          })}
          <line x1={x(1e-4)} x2={x(1)} y1={H - 26} y2={H - 26} stroke="var(--ink-muted)" />
          {TICKS.map((t) => (
            <text key={t} x={x(t)} y={H - 10} textAnchor="middle" className="font-mono" fontSize={11} fill="var(--ink-3)">
              {tickLabel(t)}
            </text>
          ))}
        </svg></div>
      )}
      <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
        Log scale. Diamond: mean predicted PD. Dot and whisker: realised rate with its 95% Jeffreys interval, development test sample. Grades with
        no marker have no test-sample calibration row.
      </p>
    </div>
  );
}
