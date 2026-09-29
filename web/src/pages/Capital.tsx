import { useState } from "react";
import type { Artefacts } from "../lib/artefacts";
import { selectCapital } from "../lib/capital";
import { KpiTile } from "../components/KpiTile";
import { Term } from "../components/Term";
import { Toggle } from "../components/EclCharts";
import { fmtMoney, fmtMoneyCompact, fmtInt, fmtPct } from "../lib/format";

const PARAM: Record<string, (v: number | string) => [string, string]> = {
  correlation: (v) => ["Asset correlation", String(v)],
  confidence: (v) => ["Confidence", `${+(Number(v) * 100).toFixed(2)}%`],
  pd_floor: (v) => ["PD floor", `${+(Number(v) * 100).toFixed(2)}%`],
  lgd_floor: (v) => ["LGD floor", `${+(Number(v) * 100).toFixed(2)}%`],
  lgd_basis: (v) => ["LGD basis", String(v) === "downturn_gross_of_mi" ? "downturn, before mortgage insurance" : String(v).replace(/_/g, " ")],
};

function param(k: string, v: number | string): [string, string] {
  return PARAM[k]?.(v) ?? [k.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase()), String(v)];
}

export function Capital({ data }: { data: Artefacts }) {
  const capital = selectCapital(data.capital);
  const [view, setView] = useState<"chart" | "table">("chart");

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
      <h1 className="font-display text-4xl">Capital</h1>
      <p className="mt-3 max-w-[68ch] text-lg" style={{ color: "var(--ink-2)" }}>
        <Term k="RWA">Risk-weighted assets</Term> scale each loan by how risky it is, and capital is the
        cushion a bank would hold against unexpected losses on them. Shown next to expected loss (ECL)
        so the two can be compared.
      </p>

      <aside className="mt-6 max-w-[68ch] rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--surface-2)" }}>
        <h2 className="text-base font-semibold" style={{ color: "var(--ink)" }}>Illustrative only, not a regulatory calculation</h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm" style={{ color: "var(--ink-2)" }}>
          {capital.limits.filter((l) => !/^illustrative only/i.test(l)).map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </aside>

      <div className="mt-4 flex flex-wrap gap-2">
        {Object.entries(capital.parameters).map(([k, v]) => {
          const [name, val] = param(k, v);
          return (
            <span key={k} className="rounded-full border px-3 py-1 text-sm" style={{ borderColor: "var(--border)", color: "var(--ink-2)" }}>
              {name}: <span className="tabular font-medium" style={{ color: "var(--ink)" }}>{val}</span>
            </span>
          );
        })}
      </div>

      {capital.totals && (
        <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
          <KpiTile label="Total EAD" estimate={capital.totals.ead} isPct={false} format={fmtMoneyCompact} />
          <KpiTile label="Total RWA" estimate={capital.totals.rwa} isPct={false} format={fmtMoneyCompact} />
          <KpiTile label="Total capital" estimate={capital.totals.capital} isPct={false} format={fmtMoneyCompact} />
          <KpiTile label="Total ECL" estimate={capital.totals.ecl} isPct={false} format={fmtMoneyCompact} />
        </div>
      )}

      <h2 className="font-display mt-10 text-2xl">Capital by grade</h2>
      <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        Grade A is the safest. Each bar is the capital held against that grade; the line beneath gives its risk-weighted assets.
      </p>
      <div className="mt-4">
        <Toggle view={view} onToggle={setView} />
        {view === "chart" && <GradeBars rows={capital.byGrade} />}
      </div>

      <div className={`mt-2 overflow-x-auto ${view === "chart" ? "hidden" : ""}`}>
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

function GradeBars({ rows }: { rows: ReturnType<typeof selectCapital>["byGrade"] }) {
  const max = Math.max(1, ...rows.map((g) => g.capital.value ?? 0));
  return (
    <ul className="m-0 list-none space-y-3 p-0">
      {rows.map((g) => {
        const v = g.capital.value;
        return (
          <li key={g.grade} className="grid grid-cols-[2rem_1fr] items-center gap-x-3">
            <span className="font-mono text-lg font-semibold" style={{ color: "var(--ink)" }}>{g.grade}</span>
            <div>
              <div className="flex items-center gap-3">
                <div className="h-6 rounded" style={{ width: `${v === null ? 0 : Math.max(0.5, (v / max) * 100) * 0.7}%`, background: "var(--accent)", minWidth: v === null ? 0 : 3 }} />
                <span className="tabular text-sm font-medium" style={{ color: "var(--ink)" }}>{v === null ? "—" : fmtMoneyCompact(v)}</span>
              </div>
              <div className="tabular mt-0.5 text-xs" style={{ color: "var(--ink-2)" }}>
                RWA {g.rwa.value === null ? "—" : fmtMoneyCompact(g.rwa.value)} · PD {g.pd.value === null ? "—" : fmtPct(g.pd.value)} · LGD {g.lgd.value === null ? "—" : fmtPct(g.lgd.value)}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
