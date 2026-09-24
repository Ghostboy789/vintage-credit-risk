import { Link } from "react-router-dom";
import type { Artefacts } from "../lib/artefacts";
import type { Estimate } from "../lib/types";
import { Ridge } from "../components/Ridge";
import { LoanField } from "../components/LoanField";
import { KpiTile } from "../components/KpiTile";
import { Prose } from "../components/Prose";
import { Scoreboard } from "../components/Scoreboard";
import { collectRules } from "../lib/rules";
import { fmtInt, fmtMoney, fmtPct } from "../lib/format";

interface Finding {
  to: string;
  page: string;
  text: string;
  est: Estimate;
  fmt: (v: number) => string;
}

// A 120 px interval bar: the finding's estimate inside its 95% interval.
function IntervalBar({ est }: { est: Estimate }) {
  const { value, ci_low, ci_high } = est;
  if (value === null || ci_low === null || ci_high === null || ci_high <= ci_low) return null;
  const lo = ci_low - (ci_high - ci_low) * 0.5;
  const hi = ci_high + (ci_high - ci_low) * 0.5;
  const p = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  return (
    <div className="relative mt-4 h-1.5 w-[120px] rounded-full" style={{ background: "var(--ink-muted)" }} aria-hidden>
      <div className="absolute inset-y-0 rounded-full" style={{ left: p(ci_low), right: `calc(100% - ${p(ci_high)})`, background: "var(--ink-2)" }} />
      <div className="absolute top-1/2 h-3 w-0.5 -translate-y-1/2" style={{ left: p(value), background: "var(--ink)" }} />
    </div>
  );
}

function findings(data: Artefacts): Finding[] {
  const out: Finding[] = [];
  const { portfolio, pd_models } = data;
  const N = portfolio.comparable_months_on_book;
  const top = portfolio.vintage_curves_annual
    .filter((r) => r.months_on_book === N && r.cum_default_rate.value !== null)
    .sort((a, b) => (b.cum_default_rate.value ?? 0) - (a.cum_default_rate.value ?? 0))[0];
  if (top)
    out.push({
      to: "/vintages",
      page: "Vintages",
      text: `At month ${N}, the ${top.vintage_year} vintage has the highest cumulative default rate`,
      est: top.cum_default_rate,
      fmt: (v) => fmtPct(v, 1),
    });

  const rolls = (portfolio.roll_rates ?? []) as { period_group: string; from_bucket: string; to_state: string; rate: Estimate }[];
  const cure = rolls.find((r) => r.period_group === "crisis" && r.from_bucket === "dpd_30" && r.to_state === "current");
  if (cure)
    out.push({
      to: "/roll-rates",
      page: "Roll rates",
      text: "In the crisis period, loans 30 days late that were current again a month later",
      est: cure.rate,
      fmt: (v) => fmtPct(v, 1),
    });

  const disc = (pd_models.discrimination ?? []) as { sample: string; definition: string; model: string; gini: Estimate }[];
  const oot = disc.find((d) => d.sample === "oot" && d.definition === "primary" && d.model === "champion");
  if (oot)
    out.push({
      to: "/scorecard",
      page: "Scorecard",
      text: "Scorecard Gini on the out-of-time sample",
      est: oot.gini,
      fmt: (v) => v.toFixed(2),
    });

  const totals = ((data.ecl as { scenario_totals?: unknown }).scenario_totals ?? []) as { reporting_date: string; scenario: string; ecl: Estimate }[];
  const final = totals.filter((t) => t.scenario === "final").sort((a, b) => b.reporting_date.localeCompare(a.reporting_date))[0];
  if (final)
    out.push({
      to: "/ecl",
      page: "IFRS 9 ECL",
      text: `Probability-weighted ECL at ${final.reporting_date}`,
      est: final.ecl,
      fmt: (v) => fmtMoney(v),
    });
  return out;
}

export function Overview({ data }: { data: Artefacts }) {
  const { portfolio } = data;
  const years = portfolio.vintage_curves_annual.map((r) => r.vintage_year);
  const y0 = Math.min(...years);
  const y1 = Math.max(...years);
  const nVintages = new Set(years).size;

  return (
    <>
      <section className="hero relative overflow-hidden">
        <div className="relative z-10 mx-auto max-w-[1200px] px-4 pt-12 md:px-8 md:pt-20">
          <h1
            className="font-display max-w-[15ch]"
            style={{ fontSize: "clamp(44px,7vw,104px)", lineHeight: 0.95, letterSpacing: "-0.02em" }}
          >
            Twenty-seven vintages of US mortgages. Watch 2006 and 2007.
          </h1>
          <p className="mt-6 max-w-[52ch] text-lg" style={{ color: "var(--ink-2)" }}>
            {fmtInt(portfolio.summary.n_loans.value ?? 0)} loans and {fmtInt(portfolio.summary.n_loan_months.value ?? 0)}{" "}
            loan-months, originated {y0}–{y1}. Each ridge is one vintage's cumulative default rate as it ages.
          </p>
        </div>
        <div className="relative z-0 mx-auto mt-6 max-w-[1600px] px-2 md:px-4 lg:-mt-24">
          <Ridge rows={portfolio.vintage_curves_annual} />
        </div>
        <p className="font-mono mx-auto max-w-[1200px] px-4 pb-4 text-xs md:px-8" style={{ color: "var(--ink-3)" }}>
          n = {fmtInt(portfolio.summary.n_loans.value ?? 0)} loans · {nVintages} vintages · primary default definition · data to{" "}
          {portfolio.data_cutoff}
        </p>
      </section>

      <div className="mx-auto max-w-[1200px] px-4 md:px-8">
        <section className="grid grid-cols-1 gap-4 py-12 sm:grid-cols-2 lg:grid-cols-4">
          <KpiTile label="Loans" estimate={portfolio.summary.n_loans} isPct={false} />
          <KpiTile label="Loan-months" estimate={portfolio.summary.n_loan_months} isPct={false} />
          <KpiTile label="Primary defaults" estimate={portfolio.summary.n_defaults_primary} isPct={false} />
          <KpiTile label="Net loss ($)" estimate={portfolio.summary.net_loss_total} isPct={false} />
        </section>

        <section className="py-16 md:py-24">
          <Prose>
            <h2 className="font-display text-3xl md:text-4xl">The Loan Field</h2>
            <p className="mt-3 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
              Scale, and where the defaults concentrate. The dots sort into one column per vintage; the defaulted
              share of each column rises to the top.
            </p>
          </Prose>
          <div className="mt-8">
            <LoanField rows={portfolio.vintage_curves_annual} />
          </div>
        </section>

        <section className="py-16 md:py-24">
          <Prose>
            <h2 className="font-display text-3xl md:text-4xl">Findings</h2>
            <p className="mt-3 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
              One number from each part of the work, with its interval. Each links to the evidence.
            </p>
          </Prose>
          <div className="mt-8 grid grid-cols-1 gap-4 md:grid-cols-2">
            {findings(data).map((f) => (
              <Link
                key={f.to}
                to={f.to}
                className="group flex flex-col rounded-xl border p-6 transition-colors"
                style={{ borderColor: "var(--border)", background: "var(--surface)", textDecoration: "none" }}
              >
                <span className="font-mono text-xs uppercase" style={{ color: "var(--ink-3)" }}>
                  {f.page}
                </span>
                <span className="mt-3 text-base" style={{ color: "var(--ink-2)" }}>
                  {f.text}
                </span>
                <span className="tabular mt-2 text-4xl font-semibold" style={{ color: "var(--ink)" }}>
                  {f.est.value === null ? "—" : f.fmt(f.est.value)}
                </span>
                <span className="mt-1 text-sm" style={{ color: "var(--ink-2)" }}>
                  {f.est.ci_low !== null && f.est.ci_high !== null
                    ? `95% CI ${f.fmt(f.est.ci_low)} – ${f.fmt(f.est.ci_high)}`
                    : f.est.ci_method.replace(/^none:\s*/, "")}
                </span>
                <IntervalBar est={f.est} />
                <span className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
                  n = {fmtInt(f.est.n)} · {f.est.ci_method}
                </span>
                <span className="mt-5 text-sm" style={{ color: "var(--accent)" }}>
                  See the evidence <span className="inline-block transition-transform group-hover:translate-x-1">→</span>
                </span>
              </Link>
            ))}
          </div>
        </section>

        <section className="py-16 md:py-24">
          <Prose>
            <h2 className="font-display text-3xl md:text-4xl">Validation scoreboard</h2>
            <p className="mt-3 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
              Every pre-registered rule, failures first. None was re-tuned to pass.
            </p>
          </Prose>
          <div className="mt-8">
            <Scoreboard rules={collectRules(data)} showEvidence />
          </div>
          <Link to="/methods" className="mt-6 inline-block text-sm" style={{ color: "var(--accent)" }}>
            See every rule with its evidence on Methods & limits →
          </Link>
        </section>
      </div>
    </>
  );
}
