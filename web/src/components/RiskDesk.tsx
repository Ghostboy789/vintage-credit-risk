import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Artefacts } from "../lib/artefacts";
import type { Estimate } from "../lib/types";
import { overviewFigures } from "../lib/overview-figures";
import { collectRules } from "../lib/rules";
import { fmtInt, fmtMoneyCompact, fmtPct } from "../lib/format";
import { COMPARE_MOB } from "../lib/vintage";
import { spotlightMove } from "./spotlight";
import { Term } from "./Term";
import { CountUp } from "./CountUp";
import { useReducedMotion } from "../lib/theme";

const CRISIS = new Set([2006, 2007]);
const STAGE_VAR = ["var(--stage-1)", "var(--stage-2)", "var(--stage-3)"];
const STAGE_NAME = ["performing", "risk has risen", "defaulted"];

const ci = (e: Estimate | undefined, f: (v: number) => string) =>
  e && e.ci_low !== null && e.ci_high !== null ? `95% CI ${f(e.ci_low)} – ${f(e.ci_high)}` : "";

function Cell({ to, label, span = 1, tall, children }: { to: string; label: ReactNode; span?: 1 | 2; tall?: boolean; children: ReactNode }) {
  return (
    <Link to={to} onPointerMove={spotlightMove} className={`desk-cell spot${span === 2 ? " desk-span2" : ""}${tall ? " desk-tall" : ""}`}>
      <span className="font-mono text-[11px] uppercase tracking-wide" style={{ color: "var(--ink-3)" }}>
        {label}
      </span>
      {children}
    </Link>
  );
}

const Big = ({ children, color = "var(--ink)" }: { children: ReactNode; color?: string }) => (
  <span className="tabular desk-big text-3xl font-semibold leading-none" style={{ color }}>
    {children}
  </span>
);
const Sub = ({ children }: { children: ReactNode }) => (
  <span className="font-mono text-xs leading-snug" style={{ color: "var(--ink-2)" }}>
    {children}
  </span>
);

function Pill({ tone, children }: { tone: string; children: ReactNode }) {
  return (
    <span className="font-mono rounded px-2 py-0.5 text-xs font-medium" style={{ color: tone, background: `color-mix(in srgb, ${tone} 15%, transparent)` }}>
      {children}
    </span>
  );
}

/** Default rate at month 72 for each fully observed vintage; the crisis years carry the accent. */
function CrisisBars({ rows }: { rows: { year: number; rate: number }[] }) {
  const W = 300, H = 150, top = 26, base = 128;
  const max = Math.max(...rows.map((r) => r.rate));
  const slot = W / rows.length;
  const peak = rows.reduce((a, b) => (b.rate > a.rate ? b : a));
  // Bars grow left to right; the crisis vintages come last, the peak label after them.
  const calm = rows.filter((r) => !CRISIS.has(r.year)).map((r) => r.year);
  const delay = (y: number) => (CRISIS.has(y) ? calm.length * 40 + 200 + (y - 2006) * 140 : calm.indexOf(y) * 40);
  const peakDelay = calm.length * 40 + 200 + 2 * 140 + 100;
  const label = rows.map((r) => `${r.year} ${fmtPct(r.rate, 1)}`).join(", ");
  const mono = "var(--font-mono, ui-monospace, monospace)";
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Default rate by month ${COMPARE_MOB} for each vintage: ${label}`} className="chart-x">
      <line x1="0" x2={W} y1={base} y2={base} stroke="var(--border)" />
      {rows.map((r, i) => {
        const h = (r.rate / max) * (base - top);
        const hot = CRISIS.has(r.year);
        return (
          <rect key={r.year} className="desk-bar" style={{ "--d": `${delay(r.year)}ms` } as CSSProperties} x={i * slot + slot * 0.15} y={base - h} width={slot * 0.7} height={h} rx="1.5" fill={hot ? "var(--crisis)" : "var(--ink-3)"} fillOpacity={hot ? 1 : 0.5}>
            <title>{`${r.year}: ${fmtPct(r.rate, 1)}`}</title>
          </rect>
        );
      })}
      <text className="desk-peak" style={{ "--d": `${peakDelay}ms` } as CSSProperties} x={Math.min(Math.max(rows.indexOf(peak) * slot + slot / 2, 42), W - 42)} y={top - 9} textAnchor="middle" fontSize="11" fill="var(--crisis)" fontFamily={mono}>
        {`${peak.year} · ${fmtPct(peak.rate, 1)}`}
      </text>
      <text x="0" y={H - 4} fontSize="10" fill="var(--ink-3)" fontFamily={mono}>{rows[0].year}</text>
      <text x={W} y={H - 4} textAnchor="end" fontSize="10" fill="var(--ink-3)" fontFamily={mono}>{rows[rows.length - 1].year}</text>
    </svg>
  );
}

/** Concept C: the book on one screen, every tile a door into its page. */
export function RiskDesk({ data }: { data: Artefacts }) {
  const { portfolio } = data;
  const f = overviewFigures(data);
  const rows = f.at72
    .map((r) => ({ year: r.vintage_year, rate: r.cum_default_rate.value as number }))
    .sort((a, b) => a.year - b.year);
  const rules = collectRules(data);
  const count = (r: string) => rules.filter((x) => x.result === r).length;
  const n = portfolio.summary;
  const stageTotal = f.stages.reduce((s, t) => s + t.n, 0) || 1;
  const stageText = f.stages.map((t, i) => `${fmtPct(t.n / stageTotal, 1)} ${STAGE_NAME[i]}`).join(" · ");
  const peak = rows.length ? rows.reduce((a, b) => (b.rate > a.rate ? b : a)) : undefined;
  const y2003 = rows.find((r) => r.year === 2003);
  const reduced = useReducedMotion();
  const gridRef = useRef<HTMLDivElement>(null);
  const [seen, setSeen] = useState(false);
  useEffect(() => {
    const el = gridRef.current;
    if (!el || typeof IntersectionObserver === "undefined") return setSeen(true);
    const io = new IntersectionObserver(([e]) => e.isIntersecting && (setSeen(true), io.disconnect()), { threshold: 0.25 });
    io.observe(el);
    return () => io.disconnect();
  }, []);
  const num = (e: Estimate, fmt: (v: number) => string) => <CountUp estimate={e} fmt={fmt} run={seen} reduced={reduced} />;

  return (
    <section aria-labelledby="desk-h" className="py-12 md:py-16">
      <div className="font-mono text-xs uppercase tracking-wide" style={{ color: "var(--accent)" }}>
        Book at {f.eclDate ?? portfolio.data_cutoff}
      </div>
      <h2 id="desk-h" className="font-display mt-2 text-3xl md:text-4xl">
        The risk desk
      </h2>
      <p className="mt-3 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        The whole book on one screen: portfolio, crisis, model, provision, capital and validation. Each tile opens its evidence.
      </p>

      <div ref={gridRef} className={`desk-grid mt-8${seen ? " desk-live" : ""}`}>
        {rows.length > 0 && peak && (
          <Cell to="/vintages" label={`Crisis · default rate by month ${COMPARE_MOB}`} span={2} tall>
            <CrisisBars rows={rows} />
            <Sub>
              {peak.year} peaked at {fmtPct(peak.rate, 1)}
              {y2003 && peak.year !== 2003 ? `, about ${Math.round(peak.rate / y2003.rate)}× the 2003 vintage` : ""}. Vintages fully observed to month {COMPARE_MOB} only.
            </Sub>
          </Cell>
        )}
        <Cell to="/vintages" label="Loans">
          <Big>{num(n.n_loans, (v) => `${(v / 1e6).toFixed(1)}M`)}</Big>
          <Sub>{((n.n_loan_months.value ?? 0) / 1e6).toFixed(1)}M loan-months</Sub>
        </Cell>
        <Cell to="/vintages" label="Net loss">
          <Big>{num(n.net_loss_total, (v) => `$${(v / 1e9).toFixed(2)}B`)}</Big>
          <Sub>{fmtInt(n.n_defaults_primary.value ?? 0)} defaulted loans</Sub>
        </Cell>
        {f.gini?.value != null && (
          <Cell to="/scorecard" label={<><Term k="Gini">Gini</Term> · out of time</>}>
            <Big>{num(f.gini, (v) => v.toFixed(2))}</Big>
            <Sub>{ci(f.gini, (v) => v.toFixed(2))}</Sub>
          </Cell>
        )}
        <Cell to="/methods" label="Validation">
          <span className="flex flex-wrap gap-2">
            <Pill tone="var(--fail)">{count("FAIL")} FAIL</Pill>
            <Pill tone="var(--amber)">{count("AMBER")} AMBER</Pill>
            <Pill tone="var(--pass)">{count("PASS")} PASS</Pill>
          </span>
          <Sub>Pre-registered; none re-tuned to pass.</Sub>
        </Cell>
        {f.ecl?.value != null && (
          <Cell to="/ecl" label={<>IFRS 9 <Term k="ECL">ECL</Term> · probability-weighted</>} span={2}>
            <Big color="var(--accent)">{num(f.ecl, fmtMoneyCompact)}</Big>
            <Sub>{ci(f.ecl, fmtMoneyCompact)} · parameter uncertainty only, too narrow</Sub>
            {f.stages.length > 0 && (
              <>
                <span className="desk-stages flex h-3 gap-[2px] overflow-hidden rounded" role="img" aria-label={stageText}>
                  {f.stages.map((t, i) => (
                    <i key={t.stage} style={{ width: `${(t.n / stageTotal) * 100}%`, minWidth: t.n > 0 ? 3 : 0, background: STAGE_VAR[i] }} />
                  ))}
                </span>
                <Sub>{stageText}</Sub>
              </>
            )}
          </Cell>
        )}
        {f.cure30?.value != null && (
          <Cell to="/roll-rates" label="Crisis · 30 days late, cured">
            <Big>{num(f.cure30, (v) => fmtPct(v, 1))}</Big>
            <Sub>{ci(f.cure30, (v) => fmtPct(v, 1))}</Sub>
          </Cell>
        )}
        {f.capital?.value != null && (
          <Cell to="/capital" label="Capital · illustrative IRB">
            <Big>{num(f.capital, fmtMoneyCompact)}</Big>
            {f.rwa?.value != null && <Sub>on {fmtMoneyCompact(f.rwa.value)} RWA</Sub>}
          </Cell>
        )}
      </div>
    </section>
  );
}
