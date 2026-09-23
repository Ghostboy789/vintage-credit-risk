import { useMemo, useState } from "react";
import type { Artefacts } from "../lib/artefacts";
import { ResultBadge } from "../components/ResultBadge";
import { fmtMoney, fmtInt, fmtPct } from "../lib/format";

interface EclRow {
  reporting_date: string;
  stage: string;
  grade: string;
  n_loans: number;
  ead: { value: number | null; n: number };
  ecl: { value: number | null; ci_low: number | null; ci_high: number | null; n: number; ci_method: string };
}

export function Ecl({ data }: { data: Artefacts }) {
  const ecl = data.ecl as unknown as { by_date: EclRow[]; pass_rules?: { rule_id?: string; result: string }[] };
  const dates = useMemo(() => [...new Set(ecl.by_date.map((r) => r.reporting_date))].sort(), [ecl]);
  const [date, setDate] = useState(dates[dates.length - 1]);
  const rows = ecl.by_date.filter((r) => r.reporting_date === date);
  const stageTotals = ["1", "2", "3"].map((s) => ({
    stage: s,
    n: rows.filter((r) => r.stage === s).reduce((sum, r) => sum + r.n_loans, 0),
    ecl: rows.filter((r) => r.stage === s).reduce((sum, r) => sum + (r.ecl.value ?? 0), 0),
  }));
  const totalN = stageTotals.reduce((s, t) => s + t.n, 0) || 1;

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">IFRS 9 ECL</h1>

      <div className="mt-6 flex flex-wrap gap-2">
        {dates.map((d) => (
          <button
            key={d}
            onClick={() => setDate(d)}
            className="rounded-full border px-3 py-1 text-xs"
            style={{ borderColor: "var(--border)", background: d === date ? "var(--accent)" : "transparent", color: d === date ? "var(--bg)" : "var(--ink-2)" }}
          >
            {d}
          </button>
        ))}
      </div>

      <section className="mt-8">
        <h2 className="font-display text-2xl">Stage mix</h2>
        <div className="mt-3 flex h-8 w-full overflow-hidden rounded" style={{ background: "var(--surface-2)" }}>
          {stageTotals.map((t, i) => (
            <div
              key={t.stage}
              style={{ width: `${(t.n / totalN) * 100}%`, background: ["#1B1530", "#9C3A63", "#F9BE4A"][i] }}
              title={`Stage ${t.stage}`}
            />
          ))}
        </div>
        <div className="mt-2 flex gap-6 text-sm">
          {stageTotals.map((t) => (
            <div key={t.stage}>
              Stage {t.stage}: {fmtInt(t.n)} loans, {fmtMoney(t.ecl)} ECL
            </div>
          ))}
        </div>
      </section>

      <section className="mt-10">
        <h2 className="font-display text-2xl">ECL by stage × grade</h2>
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr style={{ color: "var(--ink-3)" }}>
              <th className="text-left">Stage</th>
              <th className="text-left">Grade</th>
              <th className="text-right">n</th>
              <th className="text-right">EAD</th>
              <th className="text-right">ECL</th>
              <th className="text-right">Coverage</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={`${r.stage}-${r.grade}`} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="py-1">{r.stage}</td>
                <td className="font-mono py-1">{r.grade}</td>
                <td className="tabular text-right">{fmtInt(r.n_loans)}</td>
                <td className="tabular text-right">{r.ead.value !== null ? fmtMoney(r.ead.value) : "—"}</td>
                <td className="tabular text-right">{r.ecl.value !== null ? fmtMoney(r.ecl.value) : "—"}</td>
                <td className="tabular text-right">{r.ead.value ? fmtPct((r.ecl.value ?? 0) / r.ead.value) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {ecl.pass_rules && ecl.pass_rules.length > 0 && (
        <section className="mt-10 flex flex-wrap gap-3">
          {ecl.pass_rules.map((r) => (
            <div key={r.rule_id} className="flex items-center gap-2 rounded-md border px-3 py-2" style={{ borderColor: "var(--border)" }}>
              <span className="font-mono text-xs" style={{ color: "var(--ink-3)" }}>
                {r.rule_id}
              </span>
              <ResultBadge result={r.result} />
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
