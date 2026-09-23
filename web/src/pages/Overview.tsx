import type { Artefacts } from "../lib/artefacts";
import { Ridge } from "../components/Ridge";
import { LoanField } from "../components/LoanField";
import { KpiTile } from "../components/KpiTile";
import { ResultBadge } from "../components/ResultBadge";
import { fmtInt } from "../lib/format";

export function Overview({ data }: { data: Artefacts }) {
  const { portfolio } = data;
  const rules = [
    ...(portfolio.pass_rules ?? []),
    ...(data.pd_models.pass_rules ?? []),
  ] as { rule_id?: string; id?: string; result: string; evidence?: string }[];
  const counts = rules.reduce<Record<string, number>>((acc, r) => {
    acc[r.result] = (acc[r.result] ?? 0) + 1;
    return acc;
  }, {});
  const flagged = rules.filter((r) => r.result === "FAIL" || r.result === "AMBER");

  return (
    <div className="mx-auto max-w-[1200px] px-4 md:px-8">
      <section className="py-12 md:py-20">
        <h1
          className="font-display max-w-4xl"
          style={{ fontSize: "clamp(44px,7vw,104px)", lineHeight: 0.95, letterSpacing: "-0.02em" }}
        >
          Twenty-seven vintages of US mortgages. Watch 2006 and 2007.
        </h1>
        <p className="mt-6 max-w-[68ch] text-lg" style={{ color: "var(--ink-2)" }}>
          {fmtInt(portfolio.summary.n_loans.value ?? 0)} loans, {fmtInt(portfolio.summary.n_loan_months.value ?? 0)}{" "}
          loan-months, origination years 1999–2025.
        </p>
        <div className="mt-10">
          <Ridge rows={portfolio.vintage_curves_annual} />
        </div>
      </section>

      <section className="grid grid-cols-2 gap-4 py-8 md:grid-cols-4">
        <KpiTile label="Loans" estimate={portfolio.summary.n_loans} isPct={false} />
        <KpiTile label="Loan-months" estimate={portfolio.summary.n_loan_months} isPct={false} />
        <KpiTile label="Primary defaults" estimate={portfolio.summary.n_defaults_primary} isPct={false} />
        <KpiTile
          label="Net loss ($)"
          estimate={{ ...portfolio.summary.net_loss_total, value: portfolio.summary.net_loss_total.value }}
          isPct={false}
        />
      </section>

      <section className="py-16">
        <h2 className="font-display text-2xl">The Loan Field</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Scale, and where the defaults concentrate: about 1,350 dots, one per 1,000 loans.
        </p>
        <div className="mt-6">
          <LoanField rows={portfolio.vintage_curves_annual} />
        </div>
      </section>

      <section className="py-16">
        <h2 className="font-display text-2xl">Validation scoreboard</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {Object.entries(counts).map(([result, n]) => (
            <div key={result} className="flex items-center gap-2 rounded-md border px-3 py-2" style={{ borderColor: "var(--border)" }}>
              <ResultBadge result={result} /> <span className="font-mono text-sm">{n}</span>
            </div>
          ))}
        </div>
        {flagged.length > 0 && (
          <div className="mt-6 space-y-2">
            {flagged.map((r) => (
              <div key={(r.rule_id ?? r.id) as string} className="flex items-start gap-3 rounded-md border p-3" style={{ borderColor: "var(--border)" }}>
                <ResultBadge result={r.result} />
                <div>
                  <div className="font-mono text-sm">{r.rule_id ?? r.id}</div>
                  <div className="text-sm" style={{ color: "var(--ink-2)" }}>
                    {r.evidence}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
        <a href="/methods" className="mt-4 inline-block text-sm" style={{ color: "var(--accent)" }}>
          See every rule on Methods & limits →
        </a>
      </section>
    </div>
  );
}
