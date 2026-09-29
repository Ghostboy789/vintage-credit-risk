import { useMemo, useState } from "react";
import type { Artefacts } from "../lib/artefacts";
import { RuleCard } from "../components/Scoreboard";
import { sortRules } from "../lib/rules";
import { ScrollProgress } from "../components/ScrollProgress";
import { Term } from "../components/Term";

interface Rule {
  rule_id?: string;
  id?: string;
  result: string;
  evidence?: string;
  artefact: string;
}

const NOT_ESTABLISHED = [
  "The PD is not calibrated out of time: S4b fails in 6 of the 7 grades tested against 2017-2019 and 2021-2024 originations (see the Scorecard page's out-of-time calibration).",
  "The ECL intervals cover parameter uncertainty only (from 1,000 parameter draws) and exclude LGD, scenario, staging and model uncertainty, so they are too narrow.",
  "The ECL backtest is biased: it over-predicts realised defaults in 48 of 49 grade-dates tested, and the PASS result comes from a wide Vasicek band rather than from the PD being calibrated.",
  "The IFRS 9 stage-2 rule is driven mainly by the gap between current and origination house-price growth, not by the borrower's own behaviour: this accounts for 89.7% of stage 2 at 2026-03 and 93% at 2023-03. Measured at 2026-03 (point estimates): putting the reference on the same forward-mean definition moves stage 2 only from 46,668 to 42,440 loans, while dropping the house-price term from both sides leaves 15,039, so most of stage 2 comes from the covariate itself, not from the definition gap.",
  "The historical ECL time series uses hindsight: the LGD model is fitted once on defaults through 2023-03 and then applied at every historical reporting date, and the adverse scenario at 2007 dates replays the house-price path that actually followed.",
  "Reject inference: the data has no rejected applicants, so acceptance-population bias cannot be measured.",
  "Selection: conforming loans only, bought by Freddie Mac — not the whole mortgage market.",
  "Geography: US mortgages, not Indian loans. Methods map to Ind AS 109 / RBI SMA; the numbers do not.",
];

export function Methods({ data }: { data: Artefacts }) {
  const allRules = useMemo<Rule[]>(() => {
    const collect = (artefact: string, list: unknown) =>
      ((list ?? []) as { rule_id?: string; id?: string; result: string; evidence?: string }[]).map((r) => ({ ...r, artefact }));
    return [
      ...collect("portfolio", data.portfolio.pass_rules),
      ...collect("pd_models", data.pd_models.pass_rules),
      ...collect("lgd_ead", (data.lgd_ead as { pass_rules?: unknown }).pass_rules),
      ...collect("ecl", (data.ecl as { pass_rules?: unknown }).pass_rules),
    ];
  }, [data]);

  const [filter, setFilter] = useState<string | null>(null);
  const filtered = filter ? allRules.filter((r) => r.result === filter) : allRules;
  const sorted = sortRules(filtered.map((r) => ({ ...r, rule_id: String(r.rule_id ?? r.id ?? "?") }))).map((r) => ({ ...r, id: r.rule_id }));
  const results = [...new Set(allRules.map((r) => r.result))];

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <ScrollProgress />
      <h1 className="font-display text-4xl">Methods & limits</h1>
      <p className="mt-3 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        Every test was written down before the results were seen (<Term k="pre-registered">pre-registered</Term>), and none was re-tuned to
        pass. Failures come first, and what the work cannot show is listed below the table.
      </p>

      <section className="mt-10">
        <h2 className="font-display text-2xl">Master rules table</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            aria-pressed={filter === null}
            onClick={() => setFilter(null)}
            className="min-h-[44px] rounded-full border px-4 text-xs lg:min-h-[32px]"
            style={{ borderColor: "var(--border)", background: filter === null ? "var(--accent)" : "transparent", color: filter === null ? "var(--bg)" : "var(--ink-2)" }}
          >
            All
          </button>
          {results.map((r) => (
            <button
              key={r}
              aria-pressed={filter === r}
              onClick={() => setFilter(r)}
              className="min-h-[44px] rounded-full border px-4 text-xs lg:min-h-[32px]"
              style={{ borderColor: "var(--border)", background: filter === r ? "var(--accent)" : "transparent", color: filter === r ? "var(--bg)" : "var(--ink-2)" }}
            >
              {r}
            </button>
          ))}
        </div>
        <ul className="mt-4 grid grid-cols-1 items-start gap-2 lg:grid-cols-2">
          {sorted.map((r) => {
            const id = String(r.rule_id ?? r.id ?? "?");
            return (
              <li id={id} key={`${r.artefact}-${id}`} className="scroll-mt-24">
                <RuleCard rule={{ rule_id: id, result: r.result, evidence: r.evidence, artefact: r.artefact }} showEvidence showArtefact />
              </li>
            );
          })}
        </ul>
      </section>

      <section
        className="mt-16 rounded-2xl border p-5 md:p-8"
        style={{ borderColor: "color-mix(in srgb, var(--amber) 55%, var(--border))", background: "color-mix(in srgb, var(--amber) 7%, var(--surface))" }}
      >
        <h2 className="font-display text-2xl md:text-3xl">What these results do not establish</h2>
        <p className="mt-2 max-w-[68ch] text-sm" style={{ color: "var(--ink-2)" }}>
          The honest limits of this work. Read these before relying on any number above.
        </p>
        <ol className="mt-6 grid grid-cols-1 gap-3">
          {NOT_ESTABLISHED.map((item, i) => (
            <li key={item} className="flex gap-4 rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
              <span
                aria-hidden
                className="font-mono flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs"
                style={{ background: "color-mix(in srgb, var(--amber) 18%, transparent)", color: "var(--amber)" }}
              >
                {i + 1}
              </span>
              <span className="max-w-[80ch] text-[15px] leading-relaxed" style={{ color: "var(--ink)" }}>
                {item}
              </span>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16">
        <a href="https://github.com/Ghostboy789/vintage-credit-risk/blob/main/VALIDATION_PLAN.md" style={{ color: "var(--accent)" }}>
          VALIDATION_PLAN.md
        </a>
        {" · "}
        <a href="https://github.com/Ghostboy789/vintage-credit-risk" style={{ color: "var(--accent)" }}>
          repo
        </a>
      </section>
    </div>
  );
}
