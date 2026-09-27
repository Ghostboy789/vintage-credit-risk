import { useMemo, useState } from "react";
import type { Artefacts } from "../lib/artefacts";
import { ResultBadge } from "../components/ResultBadge";
import { KpiTile } from "../components/KpiTile";
import { eclDates, stageTotals as computeStageTotals, type EclRow } from "../lib/ecl";
import { selectLgdEad } from "../lib/lgd";
import {
  Backtest,
  PdTermStructure,
  ScenarioTotals,
  Stage2Drivers,
  StageMigration,
} from "../components/EclCharts";
import type {
  BacktestRow,
  CuredRow,
  PdTsRow,
  Scenarios,
  ScenarioTotalsRow,
  Stage2DriverRow,
  StageMigRow,
} from "../components/EclCharts";
import { fmtMoney, fmtInt, fmtPct, fmtDate } from "../lib/format";

export function Ecl({ data }: { data: Artefacts }) {
  const ecl = data.ecl as unknown as {
    by_date: EclRow[];
    pass_rules?: { rule_id?: string; result: string }[];
    stage_migration?: StageMigRow[];
    scenarios?: Scenarios;
    scenario_totals?: ScenarioTotalsRow[];
    pd_term_structure?: PdTsRow[];
    backtest?: BacktestRow[];
    stage2_drivers?: Stage2DriverRow[];
    cured_population?: CuredRow[];
  };
  const lgdEad = useMemo(() => selectLgdEad(data.lgd_ead), [data.lgd_ead]);
  const dates = useMemo(() => eclDates(ecl.by_date), [ecl]);
  const [date, setDate] = useState(dates[dates.length - 1]);
  const rows = ecl.by_date.filter((r) => r.reporting_date === date);
  const stageTotals = computeStageTotals(ecl.by_date, date);
  const totalN = stageTotals.reduce((s, t) => s + t.n, 0) || 1;

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 md:px-8">
      <h1 className="font-display text-4xl">IFRS 9 ECL</h1>

      <label className="mt-6 flex max-w-xs flex-col gap-1 text-sm" style={{ color: "var(--ink-2)" }}>
        Reporting date ({dates.length} available)
        <input
          type="range"
          min={0}
          max={dates.length - 1}
          value={dates.indexOf(date)}
          onChange={(e) => setDate(dates[Number(e.target.value)])}
          aria-label="Reporting date scrubber"
        />
        <select
          value={date}
          onChange={(e) => setDate(e.target.value)}
          className="font-mono rounded border px-3 py-2 text-sm"
          style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink)" }}
        >
          {dates.map((d) => (
            <option key={d} value={d}>
              {fmtDate(d)}
            </option>
          ))}
        </select>
      </label>

      <section className="mt-8">
        <h2 className="font-display text-2xl">Stage mix</h2>
        <div className="mt-3 flex h-8 w-full overflow-hidden rounded" style={{ background: "var(--surface-2)" }}>
          {stageTotals.map((t, i) => (
            <div
              key={t.stage}
              style={{ width: `${(t.n / totalN) * 100}%`, background: ["var(--stage-1)", "var(--stage-2)", "var(--stage-3)"][i] }}
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

      <LgdEadSection lgdEad={lgdEad} />

      <section className="mt-10">
        <h2 className="font-display text-2xl">ECL by stage × grade</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
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
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Stage migration</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          How accounts moved between stages over the migration window.
        </p>
        <div className="mt-6">
          <StageMigration rows={ecl.stage_migration ?? []} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Scenarios</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          ECL under each macro scenario and the probability-weighted view.
        </p>
        <div className="mt-6">
          {ecl.scenarios?.used ? (
            <ScenarioTotals scenarios={ecl.scenarios} rows={ecl.scenario_totals ?? []} date={date} />
          ) : (
            <p style={{ color: "var(--ink-2)" }}>Scenarios not used in this run.</p>
          )}
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">PD term structure</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Cumulative lifetime PD by grade and year.
        </p>
        <div className="mt-6">
          <PdTermStructure rows={ecl.pd_term_structure ?? []} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Backtest</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Realised default rate against the predicted PD, inside the binomial and Vasicek bands.
        </p>
        <p className="mt-2 max-w-[68ch] text-sm" style={{ color: "var(--ink-2)" }}>
          The pass comes from a wide band: the model over-predicts realised defaults in 48 of the 49 grade-dates
          tested. A pass here is not evidence the PD is calibrated.
        </p>
        <div className="mt-6">
          <Backtest rows={ecl.backtest ?? []} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Stage 2 drivers</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          What moved accounts into stage 2 at the current date, ranked by share.
        </p>
        <div className="mt-6">
          <Stage2Drivers rows={ecl.stage2_drivers ?? []} date={date} />
        </div>
      </section>

      <section className="mt-16">
        <h2 className="font-display text-2xl">Cured population</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          Loans that cured and are still in their probation period.
        </p>
        <div className="mt-6">
          <p style={{ color: "var(--ink-2)" }}>
            {(() => {
              const c = (ecl.cured_population ?? []).find((r) => r.reporting_date === date);
              return c && c.ecl.value !== null
                ? `${fmtInt(c.n_loans)} cured loans carry ${fmtMoney(c.ecl.value)} of ECL at this date, held in their probation stage.`
                : "No cured loans at this date.";
            })()}
          </p>
        </div>
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

function LgdEadSection({ lgdEad }: { lgdEad: ReturnType<typeof selectLgdEad> }) {
  const [dim, setDim] = useState(lgdEad.dimensions[0] ?? "ltv_band");
  const rows = lgdEad.segments.filter((s) => s.dimension === dim);

  return (
    <section className="mt-16">
      <h2 className="font-display text-2xl">LGD &amp; EAD</h2>
      <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
        Realised loss given default and exposure at default, the inputs to the ECL above.
        {lgdEad.modelUsed ? " An LGD model is used, having beaten the segment means out of sample." : ""}
      </p>

      <div className="mt-6 grid grid-cols-2 gap-4 md:grid-cols-4">
        <KpiTile label="Mean EAD" estimate={lgdEad.meanEad} isPct={false} format={fmtMoney} />
        {lgdEad.overall && <KpiTile label="Overall LGD (economic)" estimate={lgdEad.overall.lgd_economic} />}
      </div>

      {lgdEad.dimensions.length > 0 && (
        <div className="mt-8">
          <label className="flex max-w-xs flex-col gap-1 text-sm" style={{ color: "var(--ink-2)" }}>
            Segment by
            <select
              value={dim}
              onChange={(e) => setDim(e.target.value)}
              className="font-mono rounded border px-3 py-2 text-sm"
              style={{ borderColor: "var(--border)", background: "var(--surface-2)", color: "var(--ink)" }}
            >
              {lgdEad.dimensions.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ color: "var(--ink-3)" }}>
                  <th className="text-left">Segment</th>
                  <th className="text-right">LGD (economic)</th>
                  <th className="text-right">LGD (gross of MI)</th>
                  <th className="text-right">n</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.segment} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="font-mono py-1">{r.segment}</td>
                    <td className="tabular text-right">
                      {r.lgd_economic.value !== null ? fmtPct(r.lgd_economic.value) : "—"}
                    </td>
                    <td className="tabular text-right">
                      {r.lgd_gross_of_mi.value !== null ? fmtPct(r.lgd_gross_of_mi.value) : "—"}
                    </td>
                    <td className="tabular text-right">{fmtInt(r.lgd_economic.n)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {lgdEad.downturn.length > 0 && (
        <div className="mt-8">
          <h3 className="text-lg" style={{ color: "var(--ink)" }}>
            Downturn LGD by LTV band
          </h3>
          <p className="mt-1 text-sm" style={{ color: "var(--ink-3)" }}>
            Basis for the capital calculation.
          </p>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr style={{ color: "var(--ink-3)" }}>
                  <th className="text-left">LTV band</th>
                  <th className="text-right">Downturn LGD (gross of MI)</th>
                  <th className="text-right">n</th>
                </tr>
              </thead>
              <tbody>
                {lgdEad.downturn.map((r) => (
                  <tr key={r.ltv_band} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="font-mono py-1">{r.ltv_band}</td>
                    <td className="tabular text-right">
                      {r.lgd_gross_of_mi.value !== null ? fmtPct(r.lgd_gross_of_mi.value) : "—"}
                    </td>
                    <td className="tabular text-right">{fmtInt(r.lgd_gross_of_mi.n)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </section>
  );
}
