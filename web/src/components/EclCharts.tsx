import { useId, useState } from "react";
import { scaleBand, scaleLinear, scaleLog } from "d3-scale";
import { curveMonotoneX, line } from "d3-shape";
import { m } from "framer-motion";
import type { Estimate } from "../lib/types";
import { useReducedMotion } from "../lib/theme";
import { fmtInt, fmtMoney } from "../lib/format";
import { ResultBadge } from "./ResultBadge";

export interface StageMigRow {
  from_date: string;
  to_date: string;
  from_stage: string;
  to_stage: string;
  n: number;
  share: Estimate;
}

export interface Scenarios {
  used: boolean;
  source: string;
  weights: { scenario: string; weight: number }[];
}

export interface ScenarioTotalsRow {
  reporting_date: string;
  scenario: string;
  ecl: Estimate;
}

export interface PdTsRow {
  grade: string;
  year: number;
  marginal_pd: Estimate;
  cumulative_pd: Estimate;
}

export interface BacktestRow {
  reporting_date: string;
  grade: string;
  n: number;
  predicted_pd: number;
  realised_rate: Estimate;
  binomial_low: number;
  binomial_high: number;
  vasicek_low: number;
  vasicek_high: number;
  rag: string;
  covid_affected: boolean;
}

export interface Stage2DriverRow {
  reporting_date: string;
  reason: string;
  n_loans: number;
  share_of_stage2: Estimate;
}

export interface CuredRow {
  reporting_date: string;
  n_loans: number;
  ead: Estimate;
  ecl: Estimate;
}

function ChartCaption({ n, method, extra }: { n?: number; method?: string; extra?: string }) {
  const parts = [n !== undefined ? `n = ${fmtInt(n)}` : undefined, method, extra].filter(Boolean) as string[];
  return <p className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>{parts.join(" · ")}</p>;
}

function Toggle({ view, onToggle }: { view: "chart" | "table"; onToggle: (v: "chart" | "table") => void }) {
  return (
    <div className="mb-2 flex justify-end">
      <button
        type="button"
        onClick={() => onToggle(view === "chart" ? "table" : "chart")}
        className="rounded border px-3 py-1 text-xs"
        style={{ borderColor: "var(--border)", color: "var(--ink-2)", minHeight: 32 }}
      >
        {view === "chart" ? "Table" : "Chart"}
      </button>
    </div>
  );
}

const STAGE_LABEL: Record<string, string> = { "1": "Stage 1", "2": "Stage 2", "3": "Stage 3", exited: "Exited" };

export function StageMigration({ rows }: { rows: StageMigRow[] }) {
  const reduced = useReducedMotion();
  if (!rows.length) return null;
  const froms = ["1", "2", "3"].filter((s) => rows.some((r) => r.from_stage === s));
  const tops = ["1", "2", "3", "exited"].filter((s) => rows.some((r) => r.to_stage === s));
  const byCell = new Map<string, StageMigRow>();
  for (const r of rows) byCell.set(`${r.from_stage}|${r.to_stage}`, r);

  return (
    <div className="overflow-x-auto">
      <p className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
        Migration from {rows[0].from_date} to {rows[0].to_date}
      </p>
      <table className="mt-2 border-collapse text-xs">
        <thead>
          <tr>
            <th className="p-1 text-left" style={{ color: "var(--ink-3)" }}>
              from \ to
            </th>
            {tops.map((t) => (
              <th key={t} className="font-mono p-1 text-center" style={{ color: "var(--ink-3)" }}>
                {STAGE_LABEL[t]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {froms.map((from, i) => {
            const nTotal = rows.filter((r) => r.from_stage === from).reduce((s, r) => s + r.n, 0);
            return (
              <m.tr
                key={from}
                initial={reduced ? false : { opacity: 0, y: 4 }}
                whileInView={reduced ? undefined : { opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.16, delay: i * 0.08 }}
              >
                <td className="p-1" style={{ color: "var(--ink-2)" }}>
                  {STAGE_LABEL[from]}{" "}
                  <span className="font-mono" style={{ color: "var(--ink-3)" }}>
                    n = {fmtInt(nTotal)}
                  </span>
                </td>
                {tops.map((to) => {
                  const share = byCell.get(`${from}|${to}`)?.share.value ?? null;
                  const pct = share === null ? 0 : Math.min(100, Math.round(share * 100));
                  return (
                    <td
                      key={to}
                      className="tabular text-center align-middle"
                      style={{
                        width: 56,
                        height: 56,
                        border: from === to ? "1px solid var(--ink-2)" : "1px solid var(--border)",
                        background:
                          share === null ? "transparent" : `color-mix(in srgb, var(--accent) ${pct}%, var(--surface))`,
                        color: "var(--ink)",
                      }}
                    >
                      {share === null ? "—" : share < 0.001 ? "<0.1%" : `${(share * 100).toFixed(1)}%`}
                    </td>
                  );
                })}
              </m.tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const SCEN_ORDER = ["base", "upside", "adverse", "final"];
const SCEN_LABEL: Record<string, string> = {
  base: "Base",
  upside: "Upside",
  adverse: "Adverse",
  final: "Probability-weighted",
};

export function ScenarioTotals({
  scenarios,
  rows,
  date,
}: {
  scenarios: Scenarios;
  rows: ScenarioTotalsRow[];
  date: string;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const id = useId();
  const byDate = rows.filter((r) => r.reporting_date === date);
  if (!byDate.length) return null;
  const ordered = SCEN_ORDER.filter((s) => byDate.some((r) => r.scenario === s)).concat(
    byDate.filter((r) => !SCEN_ORDER.includes(r.scenario)).map((r) => r.scenario)
  );
  const weightOf = Object.fromEntries((scenarios.weights ?? []).map((w) => [w.scenario, w.weight]));
  const eclOf = (s: string) => byDate.find((r) => r.scenario === s)?.ecl;

  const w = 640;
  const slot = 52;
  const margin = { top: 8, right: 104, bottom: 8, left: 178 };
  const h = margin.top + margin.bottom + ordered.length * slot;
  const x = scaleLinear()
    .domain([0, Math.max(1, ...byDate.map((r) => Math.max(r.ecl.value ?? 0, r.ecl.ci_high ?? 0)))])
    .nice()
    .range([margin.left, w - margin.right]);
  const refEst = byDate.find((r) => r.ecl.value !== null)?.ecl ?? byDate[0]?.ecl;

  return (
    <div>
      <Toggle view={view} onToggle={setView} />
      {view === "chart" ? (
        <div className="chart-x"><svg viewBox={`0 0 ${w} ${h}`} role="img" aria-labelledby={`${id}-t ${id}-d`} className="h-auto w-full">
          <title id={`${id}-t`}>Scenario-weighted ECL on {date}</title>
          <desc id={`${id}-d`}>
            Horizontal bars for base, upside, adverse and probability-weighted scenarios, each with its confidence
            interval whisker and the money value printed next to the bar.
          </desc>
          <line x1={margin.left} x2={margin.left} y1={margin.top} y2={h - margin.bottom} stroke="var(--border)" />
          {ordered.map((s, i) => {
            const est = eclOf(s);
            const v = est?.value ?? null;
            const cy = margin.top + i * slot + slot / 2;
            const isFinal = s === "final";
            const wt = weightOf[s];
            return (
              <g key={s}>
                <text
                  x={margin.left - 8}
                  y={cy + 4}
                  textAnchor="end"
                  className="font-mono"
                  fontSize={11}
                  fill="var(--ink)"
                >
                  {SCEN_LABEL[s] ?? s}
                  {wt !== undefined && ` · ${(wt * 100).toFixed(0)}%`}
                </text>
                {v === null ? (
                  <text x={margin.left} y={cy + 4} fontSize={11} fill="var(--ink-3)">
                    —
                  </text>
                ) : (
                  <>
                    <rect
                      x={margin.left}
                      y={cy - 12}
                      width={Math.max(2, x(v) - margin.left)}
                      height={24}
                      fill={isFinal ? "var(--accent)" : "var(--ink-2)"}
                    />
                    {est!.ci_low !== null && est!.ci_high !== null && est!.ci_low <= est!.ci_high && (
                      <g stroke="var(--ink)">
                        <line x1={x(est!.ci_low)} x2={x(est!.ci_high)} y1={cy} y2={cy} />
                        <line x1={x(est!.ci_low)} x2={x(est!.ci_low)} y1={cy - 5} y2={cy + 5} />
                        <line x1={x(est!.ci_high)} x2={x(est!.ci_high)} y1={cy - 5} y2={cy + 5} />
                      </g>
                    )}
                    <text x={x(Math.max(v, est!.ci_high ?? v)) + 8} y={cy + 4} className="font-mono tabular" fontSize={11} fill="var(--ink-2)">
                      {fmtMoney(v)}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </svg></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: "var(--ink-3)" }}>
                <th className="text-left">Scenario</th>
                <th className="text-right">Weight</th>
                <th className="text-right">ECL</th>
                <th className="text-right">95% CI</th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((s) => {
                const est = eclOf(s);
                const wt = weightOf[s];
                return (
                  <tr key={s} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="py-1">{SCEN_LABEL[s] ?? s}</td>
                    <td className="tabular text-right">{wt !== undefined ? `${(wt * 100).toFixed(0)}%` : "—"}</td>
                    <td className="tabular text-right">
                      {est && est.value !== null ? fmtMoney(est.value) : "—"}
                    </td>
                    <td className="tabular text-right">
                      {est && est.ci_low !== null && est.ci_high !== null
                        ? `${fmtMoney(est.ci_low)}–${fmtMoney(est.ci_high)}`
                        : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <ChartCaption n={refEst?.n} method={refEst?.ci_method} />
    </div>
  );
}

export function PdTermStructure({ rows }: { rows: PdTsRow[] }) {
  const reduced = useReducedMotion();
  const [view, setView] = useState<"chart" | "table">("chart");
  const id = useId();
  if (!rows.length) return null;
  const grades = [...new Set(rows.map((r) => r.grade))].sort();
  const valid = rows.filter((r) => r.cumulative_pd.value !== null);

  const w = 640;
  const h = 320;
  const margin = { top: 10, right: 30, bottom: 26, left: 46 };
  const y = scaleLinear()
    .domain([0, Math.max(0.01, ...valid.map((r) => r.cumulative_pd.value as number))])
    .nice()
    .range([h - margin.bottom, margin.top]);
  const x = scaleLinear().domain([1, 10]).range([margin.left, w - margin.right]);

  return (
    <div>
      <Toggle view={view} onToggle={setView} />
      {view === "chart" ? (
        <div className="chart-x"><svg viewBox={`0 0 ${w} ${h}`} role="img" aria-labelledby={`${id}-t ${id}-d`} className="h-auto w-full">
          <title id={`${id}-t`}>Cumulative lifetime PD by grade and year</title>
          <desc id={`${id}-d`}>
            One line per grade, cumulative PD over years 1 to 10. By year{" "}
            {Math.max(...valid.map((r) => r.year))}, grade {grades[grades.length - 1]} reaches{" "}
            {((valid.filter((r) => r.grade === grades[grades.length - 1]).sort((a, b) => b.year - a.year)[0]?.cumulative_pd.value ?? 0) * 100).toFixed(1)}%.
          </desc>
          {y.ticks(5).map((t) => (
            <g key={t}>
              <line x1={margin.left} x2={w - margin.right} y1={y(t)} y2={y(t)} stroke="var(--ink-muted)" opacity={0.5} />
              <text x={margin.left - 6} y={y(t) + 4} textAnchor="end" className="font-mono" fontSize={11} fill="var(--ink-3)">
                {(t * 100).toFixed(0)}%
              </text>
            </g>
          ))}
          {x.ticks(9).filter((t) => Number.isInteger(t)).map((t) => (
            <text
              key={t}
              x={x(t)}
              y={h - margin.bottom + 14}
              textAnchor="middle"
              className="font-mono"
              fontSize={11}
              fill="var(--ink-3)"
            >
              {t}
            </text>
          ))}
          {grades.map((g, idx) => {
            const pts = valid.filter((r) => r.grade === g).sort((a, b) => a.year - b.year);
            if (!pts.length) return null;
            const last = pts[pts.length - 1];
            const isG = g === grades[grades.length - 1];
            return (
              <g key={g}>
                <m.path
                  d={
                    line<PdTsRow>()
                      .x((r) => x(r.year))
                      .y((r) => y(r.cumulative_pd.value ?? 0))
                      .curve(curveMonotoneX)(pts) ?? undefined
                  }
                  fill="none"
                  stroke={isG ? "var(--accent)" : "var(--ink-2)"}
                  strokeWidth={isG ? 2 : 1.5}
                  initial={reduced ? false : { pathLength: 0 }}
                  whileInView={reduced ? undefined : { pathLength: 1 }}
                  viewport={{ once: true, amount: 0.3 }}
                  transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1], delay: idx * 0.035 }}
                />
                <text
                  x={x(last.year) + 5}
                  y={y(last.cumulative_pd.value as number) + 4}
                  className="font-mono"
                  fontSize={11}
                  fill={isG ? "var(--accent)" : "var(--ink-2)"}
                >
                  {g}
                </text>
              </g>
            );
          })}
        </svg></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: "var(--ink-3)" }}>
                <th className="text-left">Grade</th>
                <th className="text-right">Year</th>
                <th className="text-right">Marginal PD</th>
                <th className="text-right">Cumulative PD</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="font-mono py-1">{r.grade}</td>
                  <td className="tabular text-right">{r.year}</td>
                  <td className="tabular text-right">
                    {r.marginal_pd.value !== null ? `${(r.marginal_pd.value * 100).toFixed(2)}%` : "—"}
                  </td>
                  <td className="tabular text-right">
                    {r.cumulative_pd.value !== null ? `${(r.cumulative_pd.value * 100).toFixed(2)}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ChartCaption
        n={valid[0]?.cumulative_pd.n}
        method={valid[0]?.cumulative_pd.ci_method}
        extra={`grades A–G, years 1–10`}
      />
    </div>
  );
}

export function Backtest({ rows }: { rows: BacktestRow[] }) {
  const id = useId();
  const hatch = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const dates = [...new Set(rows.map((r) => r.reporting_date))].sort();
  const [date, setDate] = useState(dates[dates.length - 1] ?? "");
  const cur = rows.filter((r) => r.reporting_date === date);
  if (!cur.length) return null;
  const grades = [...new Set(cur.map((r) => r.grade))].sort();

  const w = 640;
  const h = 320;
  const margin = { top: 16, right: 16, bottom: 24, left: 58 };
  const lo = Math.max(1e-5, Math.min(...cur.map((r) => r.vasicek_low)));
  const hi = Math.max(1e-4, lo * 10, ...cur.map((r) => r.vasicek_high));
  const x = scaleBand<string>().domain(grades).range([margin.left, w - margin.right]).paddingInner(0.45);
  const y = scaleLog().domain([lo, hi]).range([h - margin.bottom, margin.top]);
  const yc = (v: number) => y(Math.min(hi, Math.max(lo, v)));
  const b = x.bandwidth();
  const fmtTick = (t: number) => {
    const p = t * 100;
    if (p >= 1) return `${p.toFixed(0)}%`;
    if (p >= 0.01) return `${p.toFixed(2)}%`;
    return t.toExponential(0);
  };

  return (
    <div>
      <div className="mb-3 flex flex-wrap gap-2">
        {dates.map((d) => (
          <button
            key={d}
            onClick={() => setDate(d)}
            className="rounded-full border px-3 py-1 text-xs"
            style={{
              borderColor: "var(--border)",
              background: d === date ? "var(--accent)" : "transparent",
              color: d === date ? "var(--bg)" : "var(--ink-2)",
            }}
          >
            {d}
          </button>
        ))}
      </div>
      <div className="chart-x"><svg viewBox={`0 0 ${w} ${h}`} role="img" aria-labelledby={`${id}-t ${id}-d`} className="h-auto w-full">
        <title id={`${id}-t`}>Backtest of predicted PD against realised default rates on {date}</title>
        <desc id={`${id}-d`}>
          One column per grade on a log scale. The wide band is the Vasicek interval, the inner band the binomial
          interval; the hollow diamond is the predicted PD and the filled dot the realised default rate with its
          interval. COVID-affected grades are hatched.
        </desc>
        {y.ticks().filter((t) => Math.abs(Math.log10(t) - Math.round(Math.log10(t))) < 1e-9).map((t) => (
          <g key={t}>
            <line x1={margin.left} x2={w - margin.right} y1={y(t)} y2={y(t)} stroke="var(--ink-muted)" opacity={0.5} />
            <text x={margin.left - 6} y={y(t) + 4} textAnchor="end" className="font-mono" fontSize={11} fill="var(--ink-3)">
              {fmtTick(t)}
            </text>
          </g>
        ))}
        <defs>
          <pattern id={hatch} width="5" height="5" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--ink-2)" strokeWidth={1} />
          </pattern>
        </defs>
        {grades.map((g) => {
          const r = cur.find((row) => row.grade === g)!;
          const cx = x(g)! + b / 2;
          const top = yc(r.vasicek_high);
          const bottom = yc(r.vasicek_low);
          const bandH = Math.max(1, bottom - top);
          return (
            <g key={g}>
              <text
                x={cx}
                y={h - margin.bottom + 14}
                textAnchor="middle"
                className="font-mono"
                fontSize={11}
                fill="var(--ink-3)"
              >
                {g}
              </text>
              <rect x={x(g)} y={top} width={b} height={bandH} fill="var(--ink-muted)" opacity={0.5} />
              <rect
                x={x(g)! + b * 0.2}
                y={yc(r.binomial_high)}
                width={b * 0.6}
                height={Math.max(1, yc(r.binomial_low) - yc(r.binomial_high))}
                fill="var(--ink-2)"
                opacity={0.35}
              />
              {r.covid_affected && <rect x={x(g)} y={top} width={b} height={bandH} fill={`url(#${hatch})`} />}
              <g transform={`translate(${cx}, ${yc(r.predicted_pd)})`}>
                <path d="M 0 -4 L 4 0 L 0 4 L -4 0 Z" fill="none" stroke="var(--ink)" />
              </g>
              {r.realised_rate.value !== null && (
                <g>
                  {r.realised_rate.ci_low !== null && r.realised_rate.ci_high !== null && (
                    <line
                      x1={cx}
                      x2={cx}
                      y1={yc(r.realised_rate.ci_low)}
                      y2={yc(r.realised_rate.ci_high)}
                      stroke="var(--ink)"
                    />
                  )}
                  <circle cx={cx} cy={yc(r.realised_rate.value)} r={3.5} fill="var(--ink)" />
                </g>
              )}
            </g>
          );
        })}
      </svg></div>
      <div className="mt-3 overflow-x-auto">
        <div className="grid gap-2" style={{ gridTemplateColumns: `repeat(${grades.length}, minmax(0, 1fr))` }}>
          {grades.map((g) => {
            const r = cur.find((row) => row.grade === g)!;
            return (
              <div
                key={g}
                className="flex flex-col items-center gap-1 rounded-md border p-2 text-center"
                style={{ borderColor: "var(--border)" }}
              >
                <span className="font-mono text-sm" style={{ color: "var(--ink)" }}>
                  {g}
                </span>
                <ResultBadge result={r.rag} />
                <span className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
                  n = {fmtInt(r.n)}
                </span>
                {r.covid_affected && (
                  <span className="font-mono text-[10px]" style={{ color: "var(--ink-3)" }}>
                    COVID-affected
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <ChartCaption n={cur.reduce((s, r) => s + r.n, 0)} method={cur[0]?.realised_rate.ci_method} extra="y axis is log scale" />
    </div>
  );
}

export function Stage2Drivers({ rows, date }: { rows: Stage2DriverRow[]; date: string }) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const id = useId();
  const dates = [...new Set(rows.map((r) => r.reporting_date))].sort();
  const shown = dates.includes(date) ? date : dates[dates.length - 1];
  const cur = rows.filter((r) => r.reporting_date === shown);
  if (!cur.length) return null;
  const ordered = [...cur].sort((a, b) => (b.share_of_stage2.value ?? 0) - (a.share_of_stage2.value ?? 0));

  const w = 640;
  const slot = 56;
  const margin = { top: 8, right: 150, bottom: 8, left: 170 };
  const h = margin.top + margin.bottom + ordered.length * slot;
  const x = scaleLinear()
    .domain([
      0,
      Math.max(0.01, ...cur.map((r) => r.share_of_stage2.value ?? 0), ...cur.map((r) => r.share_of_stage2.ci_high ?? 0)),
    ])
    .nice()
    .range([margin.left, w - margin.right]);

  return (
    <div>
      <p className="font-mono mb-2 text-xs" style={{ color: "var(--ink-3)" }}>
        Reporting date {shown}
        {shown !== date ? " (latest available)" : ""}
      </p>
      <Toggle view={view} onToggle={setView} />
      {view === "chart" ? (
        <div className="chart-x"><svg viewBox={`0 0 ${w} ${h}`} role="img" aria-labelledby={`${id}-t ${id}-d`} className="h-auto w-full">
          <title id={`${id}-t`}>Stage 2 entry drivers on {shown}</title>
          <desc id={`${id}-d`}>
            Horizontal bars ranked by share of the stage 2 population, each with its confidence interval whisker and
            the share range printed next to the bar.
          </desc>
          <line x1={margin.left} x2={margin.left} y1={margin.top} y2={h - margin.bottom} stroke="var(--border)" />
          {ordered.map((r, i) => {
            const v = r.share_of_stage2.value;
            const cy = margin.top + i * slot + slot / 2;
            const label = r.reason.replace(/_/g, " ");
            return (
              <g key={r.reason}>
                <text x={margin.left - 8} y={cy - 2} textAnchor="end" fontSize={11} fill="var(--ink)">
                  {label}
                </text>
                <text
                  x={margin.left - 8}
                  y={cy + 12}
                  textAnchor="end"
                  className="font-mono"
                  fontSize={10}
                  fill="var(--ink-3)"
                >
                  n = {fmtInt(r.n_loans)}
                </text>
                {v === null ? (
                  <text x={margin.left} y={cy + 4} fontSize={11} fill="var(--ink-3)">
                    —
                  </text>
                ) : (
                  <>
                    <rect
                      x={margin.left}
                      y={cy - 8}
                      width={Math.max(2, x(v) - margin.left)}
                      height={16}
                      fill="var(--ink-2)"
                    />
                    {r.share_of_stage2.ci_low !== null && r.share_of_stage2.ci_high !== null && (
                      <g stroke="var(--ink)">
                        <line x1={x(r.share_of_stage2.ci_low)} x2={x(r.share_of_stage2.ci_high)} y1={cy} y2={cy} />
                        <line x1={x(r.share_of_stage2.ci_low)} x2={x(r.share_of_stage2.ci_low)} y1={cy - 4} y2={cy + 4} />
                        <line x1={x(r.share_of_stage2.ci_high)} x2={x(r.share_of_stage2.ci_high)} y1={cy - 4} y2={cy + 4} />
                      </g>
                    )}
                    <text
                      x={x(Math.max(v, r.share_of_stage2.ci_high ?? v)) + 8}
                      y={cy + 4}
                      className="font-mono tabular"
                      fontSize={11}
                      fill="var(--ink-2)"
                    >
                      {`${(v * 100).toFixed(1)}%`}
                      {r.share_of_stage2.ci_low !== null && r.share_of_stage2.ci_high !== null
                        ? ` [${(r.share_of_stage2.ci_low * 100).toFixed(1)}–${(r.share_of_stage2.ci_high * 100).toFixed(1)}]`
                        : ""}
                    </text>
                  </>
                )}
              </g>
            );
          })}
        </svg></div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr style={{ color: "var(--ink-3)" }}>
                <th className="text-left">Reason</th>
                <th className="text-right">n loans</th>
                <th className="text-right">Share</th>
                <th className="text-right">95% CI</th>
              </tr>
            </thead>
            <tbody>
              {ordered.map((r) => (
                <tr key={r.reason} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="py-1">{r.reason.replace(/_/g, " ")}</td>
                  <td className="tabular text-right">{fmtInt(r.n_loans)}</td>
                  <td className="tabular text-right">
                    {r.share_of_stage2.value !== null ? `${(r.share_of_stage2.value * 100).toFixed(1)}%` : "—"}
                  </td>
                  <td className="tabular text-right">
                    {r.share_of_stage2.ci_low !== null && r.share_of_stage2.ci_high !== null
                      ? `${(r.share_of_stage2.ci_low * 100).toFixed(1)}–${(r.share_of_stage2.ci_high * 100).toFixed(1)}`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ChartCaption n={ordered[0]?.share_of_stage2.n} extra={ordered[0]?.share_of_stage2.ci_method} />
    </div>
  );
}