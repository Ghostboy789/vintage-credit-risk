import { useMemo, useState } from "react";
import type { Artefacts } from "../lib/artefacts";
import { ResultBadge } from "../components/ResultBadge";
import { ScrollProgress } from "../components/ScrollProgress";
import { Prose } from "../components/Prose";

interface Rule {
  rule_id?: string;
  id?: string;
  result: string;
  evidence?: string;
  artefact: string;
}

const NOT_ESTABLISHED = [
  "Reject inference: the data has no rejected applicants, so acceptance-population bias cannot be measured.",
  "Selection: conforming loans only, bought by Freddie Mac — not the whole mortgage market.",
  "Geography: US mortgages, not Indian loans. Methods map to Ind AS 109 / RBI SMA; the numbers do not.",
  "This is a synthetic-fixture build. No number on this site is a real result until the real-data release replaces these fixtures.",
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
  const sorted = [...filtered].sort((a, b) => (a.result === "FAIL" ? -1 : b.result === "FAIL" ? 1 : 0));
  const results = [...new Set(allRules.map((r) => r.result))];

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <ScrollProgress />
      <h1 className="font-display text-4xl">Methods & limits</h1>

      <section className="mt-10">
        <h2 className="font-display text-2xl">Master rules table</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => setFilter(null)}
            className="rounded-full border px-3 py-1 text-xs"
            style={{ borderColor: "var(--border)", background: filter === null ? "var(--accent)" : "transparent", color: filter === null ? "var(--bg)" : "var(--ink-2)" }}
          >
            All
          </button>
          {results.map((r) => (
            <button
              key={r}
              onClick={() => setFilter(r)}
              className="rounded-full border px-3 py-1 text-xs"
              style={{ borderColor: "var(--border)", background: filter === r ? "var(--accent)" : "transparent", color: filter === r ? "var(--bg)" : "var(--ink-2)" }}
            >
              {r}
            </button>
          ))}
        </div>
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr style={{ color: "var(--ink-3)" }}>
              <th className="text-left">Rule</th>
              <th className="text-left">Artefact</th>
              <th className="text-left">Result</th>
              <th className="text-left">Evidence</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((r) => (
              <tr id={(r.rule_id ?? r.id) as string} key={`${r.artefact}-${r.rule_id ?? r.id}`} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="font-mono py-1">{r.rule_id ?? r.id}</td>
                <td className="py-1">{r.artefact}</td>
                <td className="py-1">
                  <ResultBadge result={r.result} />
                </td>
                <td className="py-1" style={{ color: "var(--ink-2)" }}>
                  {r.evidence}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <Prose>
        <section className="mt-16">
          <h2 className="font-display text-2xl">What these results do not establish</h2>
          <ol className="mt-4 list-decimal space-y-2 pl-5">
            {NOT_ESTABLISHED.map((item) => (
              <li key={item} style={{ color: "var(--ink-2)" }}>
                {item}
              </li>
            ))}
          </ol>
        </section>
      </Prose>

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
