import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Artefacts } from "../lib/artefacts";
import type { Estimate } from "../lib/types";
import { Ridge } from "../components/Ridge";
import { LoanField } from "../components/LoanField";
import { KpiTile } from "../components/KpiTile";
import { Prose } from "../components/Prose";
import { Term } from "../components/Term";
import { spotlightMove } from "../components/spotlight";
import { Scoreboard } from "../components/Scoreboard";
import { collectRules } from "../lib/rules";
import { ciMethodLabel, fmtInt, fmtMoney, fmtPct } from "../lib/format";
import { COMPARE_MOB, countWord, rowsAt } from "../lib/vintage";

interface Finding {
  to: string;
  page: string;
  text: string;
  est: Estimate;
  fmt: (v: number) => string;
  year?: number;
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

const ci = (f: Finding) =>
  f.est.ci_low !== null && f.est.ci_high !== null ? ` (95% CI ${f.fmt(f.est.ci_low)} – ${f.fmt(f.est.ci_high)})` : "";
const val = (f: Finding) => (f.est.value === null ? "—" : f.fmt(f.est.value));

function findings(data: Artefacts): Finding[] {
  const out: Finding[] = [];
  const { portfolio, pd_models } = data;
  const compared = rowsAt(portfolio.vintage_curves_annual);
  const top = [...compared].sort((a, b) => (b.cum_default_rate.value ?? 0) - (a.cum_default_rate.value ?? 0))[0];
  if (top)
    out.push({
      to: "/vintages",
      page: "Vintages",
      text: `At month ${COMPARE_MOB}, the ${top.vintage_year} vintage has the highest cumulative default rate of the ${compared.length} vintages observed that long`,
      year: top.vintage_year,
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
  const perVintage = new Set(portfolio.vintage_curves_annual.filter((r) => r.months_on_book === 1).map((r) => r.cum_default_rate.n));

  const fs = findings(data);
  const byPage = (page: string) => fs.find((f) => f.page === page);
  const worst = byPage("Vintages");
  const cure = byPage("Roll rates");
  const gini = byPage("Scorecard");
  const ecl = byPage("IFRS 9 ECL");
  const s4b = collectRules(data, ["pd_models"]).find((r) => r.rule_id === "S4b");
  const plain: { key: string; body: ReactNode }[] = [];
  if (worst)
    plain.push({
      key: "v",
      body: (
        <>
          Loans made in <b>{worst.year}</b> defaulted most of any vintage: <b>{val(worst)}</b>
          {ci(worst)} had defaulted by month {COMPARE_MOB}.
        </>
      ),
    });
  if (cure)
    plain.push({
      key: "c",
      body: (
        <>
          In the crisis, only <b>{val(cure)}</b>
          {ci(cure)} of loans 30 days late were back to current a month later.
        </>
      ),
    });
  if (gini)
    plain.push({
      key: "g",
      body: (
        <>
          The risk score ranks borrowers well on later loans (<Term k="Gini">Gini</Term> <b>{val(gini)}</b>
          {ci(gini)})
          {s4b?.result === "FAIL" ? ", but the default rates it predicts are not calibrated out of time." : "."}
        </>
      ),
    });
  if (ecl)
    plain.push({
      key: "e",
      body: (
        <>
          The <Term k="ECL">expected credit loss</Term> is <b>{val(ecl)}</b>
          {ci(ecl)}; that range covers parameter uncertainty only, so treat it as too narrow.
        </>
      ),
    });

  return (
    <>
      <section className="hero relative overflow-hidden">
        <div className="relative z-10 mx-auto max-w-[1200px] px-4 pt-12 md:px-8 md:pt-20">
          <h1
            className="font-display max-w-[17ch]"
            style={{ fontSize: "clamp(36px,6vw,88px)", lineHeight: 0.95, letterSpacing: "-0.02em" }}
          >
            {`${countWord(nVintages)} vintages of US mortgages. Watch 2006 and 2007.`.split(" ").map((w, i) => (
              <span key={i}>
                <span className="hero-word" style={{ animationDelay: `${i * 45}ms` }}>
                  {w}
                </span>{" "}
              </span>
            ))}
          </h1>
          <p className="mt-5 max-w-[52ch] text-base md:mt-6 md:text-lg" style={{ color: "var(--ink-2)" }}>
            {fmtInt(portfolio.summary.n_loans.value ?? 0)} loans and {fmtInt(portfolio.summary.n_loan_months.value ?? 0)}{" "}
            loan-months, originated {y0}–{y1}
            {perVintage.size === 1 ? ` (a sample of ${fmtInt([...perVintage][0])} per year)` : ""}. Each ridge is one <Term k="vintage">vintage</Term>'s{" "}
            <Term k="cumulative default rate">cumulative default rate</Term> over its first ten years on book.
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
        <section aria-labelledby="plain-h" className="rounded-xl border p-5 md:p-7" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
          <h2 id="plain-h" className="font-mono text-xs uppercase tracking-wide" style={{ color: "var(--accent)" }}>
            In plain English
          </h2>
          <ul className="mt-4 grid grid-cols-1 gap-x-8 gap-y-4 md:grid-cols-2">
            {plain.map((p) => (
              <li key={p.key} className="flex gap-3 text-base leading-snug" style={{ color: "var(--ink-2)" }}>
                <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: "var(--accent)" }} />
                <span className="[&_b]:font-semibold [&_b]:text-[var(--ink)]">{p.body}</span>
              </li>
            ))}
          </ul>
        </section>

        <section className="grid grid-cols-1 gap-4 pb-4 pt-8 sm:grid-cols-2 lg:grid-cols-4">
          <KpiTile label="Loans" estimate={portfolio.summary.n_loans} isPct={false} />
          <KpiTile label="Loan-months" estimate={portfolio.summary.n_loan_months} format={(v) => `${(v / 1e6).toFixed(1)}M`} />
          <KpiTile label="Primary defaults" estimate={portfolio.summary.n_defaults_primary} isPct={false} />
          <KpiTile label="Net loss" estimate={portfolio.summary.net_loss_total} format={(v) => `$${(v / 1e9).toFixed(2)}B`} />
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
            {fs.map((f) => (
              <Link
                key={f.to}
                to={f.to}
                className="finding-card spot group flex flex-col rounded-2xl border p-6 md:p-7 transition-colors"
                style={{ borderColor: "var(--border)", background: "var(--surface)", textDecoration: "none" }}
                onPointerMove={spotlightMove}
              >
                <span className="font-mono self-start rounded-full border px-2.5 text-[11px] uppercase leading-5" style={{ color: "var(--ink-2)", borderColor: "var(--border)" }}>
                  {f.page}
                </span>
                <span className="mt-4 text-base leading-snug" style={{ color: "var(--ink-2)" }}>
                  {f.text}
                </span>
                <span className="tabular mt-4 text-5xl font-semibold leading-none" style={{ color: "var(--ink)" }}>
                  {f.est.value === null ? "—" : f.fmt(f.est.value)}
                </span>
                <span className="mt-2 text-sm" style={{ color: "var(--ink-2)" }}>
                  {f.est.ci_low !== null && f.est.ci_high !== null
                    ? `95% CI ${f.fmt(f.est.ci_low)} – ${f.fmt(f.est.ci_high)}`
                    : f.est.ci_method.replace(/^none:\s*/, "")}
                </span>
                <IntervalBar est={f.est} />
                <span className="font-mono mt-2 text-xs" style={{ color: "var(--ink-3)" }}>
                  n = {fmtInt(f.est.n)} · {ciMethodLabel(f.est.ci_method)}
                </span>
                <span className="mt-auto pt-5 text-sm font-medium" style={{ color: "var(--accent)" }}>
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
