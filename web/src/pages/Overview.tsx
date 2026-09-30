import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Artefacts } from "../lib/artefacts";
import type { Estimate } from "../lib/types";
import { Ridge } from "../components/Ridge";
import { LoanField } from "../components/LoanField";
import { AudiencePicker } from "../components/AudiencePicker";
import { LoanJourney } from "../components/LoanJourney";
import { RiskDesk } from "../components/RiskDesk";
import { useAudience } from "../lib/audience";
import { Prose } from "../components/Prose";
import { Term } from "../components/Term";
import { Scoreboard } from "../components/Scoreboard";
import { collectRules } from "../lib/rules";
import { fmtInt, fmtMoney, fmtPct } from "../lib/format";
import { COMPARE_MOB, countWord, rowsAt } from "../lib/vintage";

interface Finding {
  to: string;
  page: string;
  text: string;
  est: Estimate;
  fmt: (v: number) => string;
  year?: number;
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
          {ci(gini).replace(" (", ", ").replace(/\)$/, "")})
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

  const [audience] = useAudience();

  const sections: Record<string, ReactNode> = {
    plain: (
      <div key="plain" className="pt-2">
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

      </div>
    ),
    journey: <LoanJourney key="journey" data={data} />,
    desk: <RiskDesk key="desk" data={data} />,
    pro: (
      <section key="pro" aria-labelledby="pro-h" className="rounded-xl border p-5 md:p-7" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
        <h2 id="pro-h" className="font-mono text-xs uppercase tracking-wide" style={{ color: "var(--accent)" }}>
          For risk and model people
        </h2>
        <Link to="/vintages#crisis-story" className="font-display mt-3 block text-2xl underline-offset-4 hover:underline md:text-3xl" style={{ color: "var(--ink)" }}>
          Start with the crisis story →
        </Link>
        <p className="mt-2 max-w-[62ch]" style={{ color: "var(--ink-2)" }}>
          How the 2006 and 2007 vintages diverged, with intervals. The rules, limits and every failed check are on{" "}
          <Link to="/methods" style={{ color: "var(--accent)" }}>Methods and limits</Link>.
        </p>
      </section>
    ),
    field: (
        <section key="field" className="py-16 md:py-24">
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

    ),
    score: (
        <section key="score" className="py-16 md:py-24">
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
    ),
  };
  const order =
    audience === "hiring"
      ? ["desk", "plain", "journey", "field", "score"]
      : audience === "pro"
        ? ["pro", "desk", "plain", "journey", "field", "score"]
        : ["plain", "journey", "desk", "field", "score"];

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
          <AudiencePicker />
        </div>
        <div className="relative z-0 mx-auto mt-6 max-w-[1600px] px-2 md:px-4 lg:-mt-24">
          <Ridge rows={portfolio.vintage_curves_annual} />
        </div>
        <p className="font-mono mx-auto max-w-[1200px] px-4 pb-4 text-xs md:px-8" style={{ color: "var(--ink-3)" }}>
          n = {fmtInt(portfolio.summary.n_loans.value ?? 0)} loans · {nVintages} vintages · primary default definition · data to{" "}
          {portfolio.data_cutoff}
        </p>
      </section>

      <div id="overview-content" tabIndex={-1} className="mx-auto max-w-[1200px] scroll-mt-20 px-4 outline-none md:px-8">
        {order.map((k) => sections[k])}
      </div>
    </>
  );
}
