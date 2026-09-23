import type { Artefacts } from "../lib/artefacts";
import { fmtMoney, fmtInt, fmtPct } from "../lib/format";

interface GradeRow {
  grade: string;
  n_loans: number;
  ead: { value: number };
  pd: { value: number };
  lgd: { value: number };
  rwa: { value: number };
  capital: { value: number };
}

export function Capital({ data }: { data: Artefacts }) {
  const capital = data.capital as unknown as {
    status?: string;
    parameters: Record<string, number | string>;
    by_grade?: GradeRow[];
    limits?: string[];
  };

  if (capital.status === "not_run" || !capital.by_grade) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-24 text-center">
        <h1 className="font-display text-4xl">Capital</h1>
        <p className="mt-6" style={{ color: "var(--ink-2)" }}>
          Not run. See Methods for why.
        </p>
      </div>
    );
  }

  const totalRwa = capital.by_grade.reduce((s, g) => s + g.rwa.value, 0);
  const totalCapital = capital.by_grade.reduce((s, g) => s + g.capital.value, 0);

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <div className="rounded-md p-3 text-sm" style={{ background: "color-mix(in srgb, var(--amber) 14%, transparent)", color: "var(--amber)" }}>
        Illustrative only — not a regulatory capital calculation.
        {(capital.limits ?? []).map((l) => (
          <div key={l}>{l}</div>
        ))}
      </div>
      <h1 className="font-display mt-6 text-4xl">Capital</h1>

      <div className="mt-4 flex flex-wrap gap-2">
        {Object.entries(capital.parameters).map(([k, v]) => (
          <span key={k} className="font-mono rounded border px-2 py-1 text-xs" style={{ borderColor: "var(--border)", color: "var(--ink-2)" }}>
            {k}: {String(v)}
          </span>
        ))}
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-2">
        <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)" }}>
          <div className="text-sm" style={{ color: "var(--ink-2)" }}>
            Total RWA
          </div>
          <div className="tabular text-3xl font-semibold">{fmtMoney(totalRwa)}</div>
        </div>
        <div className="rounded-lg border p-4" style={{ borderColor: "var(--border)" }}>
          <div className="text-sm" style={{ color: "var(--ink-2)" }}>
            Total capital
          </div>
          <div className="tabular text-3xl font-semibold">{fmtMoney(totalCapital)}</div>
        </div>
      </div>

      <table className="mt-8 w-full text-sm">
        <thead>
          <tr style={{ color: "var(--ink-3)" }}>
            <th className="text-left">Grade</th>
            <th className="text-right">n</th>
            <th className="text-right">EAD</th>
            <th className="text-right">PD</th>
            <th className="text-right">LGD</th>
            <th className="text-right">RWA</th>
            <th className="text-right">Capital</th>
          </tr>
        </thead>
        <tbody>
          {capital.by_grade.map((g) => (
            <tr key={g.grade} className="border-t" style={{ borderColor: "var(--border)" }}>
              <td className="font-mono py-1">{g.grade}</td>
              <td className="tabular text-right">{fmtInt(g.n_loans)}</td>
              <td className="tabular text-right">{fmtMoney(g.ead.value)}</td>
              <td className="tabular text-right">{fmtPct(g.pd.value)}</td>
              <td className="tabular text-right">{fmtPct(g.lgd.value)}</td>
              <td className="tabular text-right">{fmtMoney(g.rwa.value)}</td>
              <td className="tabular text-right">{fmtMoney(g.capital.value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
