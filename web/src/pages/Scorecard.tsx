import type { Artefacts } from "../lib/artefacts";
import { Calculator } from "../components/Calculator";
import { ResultBadge } from "../components/ResultBadge";

export function Scorecard({ data }: { data: Artefacts }) {
  const { pd_models } = data;
  const rules = (pd_models.pass_rules ?? []) as { rule_id?: string; id?: string; result: string; evidence?: string }[];
  const challengerStatus = pd_models.challenger?.status ?? "not_run";

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">Scorecard</h1>
      <p className="mt-2" style={{ color: "var(--ink-2)" }}>
        {pd_models.scaling.pd_label}
      </p>

      <section className="mt-8 flex flex-wrap gap-3">
        {rules.map((r) => (
          <div key={(r.rule_id ?? r.id) as string} className="flex items-center gap-2 rounded-md border px-3 py-2" style={{ borderColor: "var(--border)" }}>
            <span className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
              {r.rule_id ?? r.id}
            </span>
            <ResultBadge result={r.result} />
          </div>
        ))}
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl">Grades</h2>
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr style={{ color: "var(--ink-3)" }}>
              <th className="text-left">Grade</th>
              <th className="text-left">PD range</th>
              <th className="text-left">Score range</th>
              <th className="text-left">Merged into</th>
            </tr>
          </thead>
          <tbody>
            {pd_models.grades.map((g) => (
              <tr id={`grade-${g.grade}`} key={g.grade} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="font-mono py-1">{g.grade}</td>
                <td className="tabular py-1">
                  [{(g.pd_low * 100).toFixed(2)}% – {(g.pd_high * 100).toFixed(2)}%)
                </td>
                <td className="tabular py-1">
                  {g.score_min ?? "–∞"} – {g.score_max ?? "+∞"}
                </td>
                <td className="py-1">{g.merged_into ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl">Challenger</h2>
        <p className="mt-2 text-sm" style={{ color: "var(--ink-2)" }}>
          Status: <span className="font-mono">{challengerStatus}</span>. Not promoted unless it beats the
          champion under the pre-registered rule, on the held-out interval.
        </p>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Calculator</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Enter loan attributes and see the points, grade, 12-month PD and reason codes, computed
          client-side from the published points table.
        </p>
        <div className="mt-8">
          <Calculator model={pd_models} />
        </div>
      </section>
    </div>
  );
}
