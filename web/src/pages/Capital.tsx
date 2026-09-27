import type { Artefacts } from "../lib/artefacts";
import { selectCapital } from "../lib/capital";
import { KpiTile } from "../components/KpiTile";
import { fmtMoney, fmtMoneyCompact, fmtInt, fmtPct } from "../lib/format";

export function Capital({ data }: { data: Artefacts }) {
  const capital = selectCapital(data.capital);

  if (capital.status === "not_run" || capital.byGrade.length === 0) {
    return (
      <div className="mx-auto max-w-[1200px] px-4 py-24 text-center">
        <h1 className="font-display text-4xl">Capital</h1>
        <p className="mt-6" style={{ color: "var(--ink-2)" }}>
          Not run. See Methods for why.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <div className="rounded-md p-3 text-sm" style={{ background: "color-mix(in srgb, var(--amber) 14%, transparent)", color: "var(--amber)" }}>
        Illustrative only — not a regulatory capital calculation.
        {capital.limits.map((l) => (
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

      {capital.totals && (
        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <KpiTile label="Total EAD" estimate={capital.totals.ead} isPct={false} format={fmtMoneyCompact} />
          <KpiTile label="Total RWA" estimate={capital.totals.rwa} isPct={false} format={fmtMoneyCompact} />
          <KpiTile label="Total capital" estimate={capital.totals.capital} isPct={false} format={fmtMoneyCompact} />
          <KpiTile label="Total ECL" estimate={capital.totals.ecl} isPct={false} format={fmtMoneyCompact} />
        </div>
      )}

      <div className="mt-8 overflow-x-auto">
        <table className="w-full text-sm">
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
            {capital.byGrade.map((g) => (
              <tr key={g.grade} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="font-mono py-1">{g.grade}</td>
                <td className="tabular text-right">{fmtInt(g.n_loans)}</td>
                <td className="tabular text-right">{g.ead.value !== null ? fmtMoney(g.ead.value) : "—"}</td>
                <td className="tabular text-right">{g.pd.value !== null ? fmtPct(g.pd.value) : "—"}</td>
                <td className="tabular text-right">{g.lgd.value !== null ? fmtPct(g.lgd.value) : "—"}</td>
                <td className="tabular text-right">{g.rwa.value !== null ? fmtMoney(g.rwa.value) : "—"}</td>
                <td className="tabular text-right">{g.capital.value !== null ? fmtMoney(g.capital.value) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
