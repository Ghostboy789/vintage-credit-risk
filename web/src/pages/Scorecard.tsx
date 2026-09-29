import { useCallback, useState, type ReactNode } from "react";
import type { Artefacts } from "../lib/artefacts";
import type { Estimate } from "../lib/types";
import type { CalcResult } from "../lib/calculator";
import { Calculator } from "../components/Calculator";
import { KpiTile } from "../components/KpiTile";
import { Prose } from "../components/Prose";
import { ResultBadge } from "../components/ResultBadge";
import { Scoreboard } from "../components/Scoreboard";
import { FeatureList } from "../components/FeatureList";
import { PdLadder } from "../components/PdLadder";
import { collectRules } from "../lib/rules";
import { fmtPct } from "../lib/format";
import { Term } from "../components/Term";

interface Disc {
  sample: string;
  definition: string;
  model: string;
  gini: Estimate;
  ks: Estimate;
}

function Section({ title, intro, children }: { title: string; intro: ReactNode; children: ReactNode }) {
  return (
    <section className="mt-20 md:mt-24">
      <Prose>
        <h2 className="font-display text-3xl">{title}</h2>
        <p className="mt-2 max-w-[68ch]" style={{ color: "var(--ink-2)" }}>
          {intro}
        </p>
      </Prose>
      <div className="mt-8">{children}</div>
    </section>
  );
}

export function Scorecard({ data }: { data: Artefacts }) {
  const { pd_models } = data;
  const [result, setResult] = useState<CalcResult | null>(null);
  const onResult = useCallback((r: CalcResult) => setResult(r), []);

  const disc = (pd_models.discrimination ?? []) as Disc[];
  const oot = disc.find((d) => d.sample === "oot" && d.definition === "primary" && d.model === "champion");
  const drop = ((pd_models.gini_drop ?? []) as { definition: string; relative: Estimate; rag: string }[]).find((g) => g.definition === "primary");
  const psi = (((data.monitoring as { score_psi?: unknown }).score_psi ?? []) as { comparison: string; psi: Estimate; rag: string }[]).find(
    (p) => p.comparison === "dev_train_vs_oot"
  );
  const features = (pd_models.features ?? []) as { feature: string; iv: Estimate; selected: boolean; drop_reason: string | null }[];
  const allCalibration = (pd_models.calibration ?? []) as {
    sample: string;
    definition: string;
    grade: string;
    n: number;
    mean_pd: number;
    realised_rate: Estimate;
    result: string;
  }[];
  const calibration = allCalibration.filter((c) => c.sample === "dev_test" && c.definition === "primary");
  // V-01: the site showed only the in-time (dev_test) calibration. S4b fails on 6 of 7 grades
  // out of time, so the ladder needs that sample too, not just a pass/fail badge for it.
  const calibrationOot = allCalibration.filter((c) => c.sample === "oot" && c.definition === "primary");
  // The challenger outcome comes from rule C1 and the challenger block of the artefact; its "status" only says the run happened.
  const c1 = collectRules(data, ["pd_models"]).find((r) => r.rule_id === "C1");
  const ch = (pd_models.challenger ?? {}) as { criteria?: { criterion: string; met: boolean }[]; delta_gini_oot?: Estimate };
  const challengerResult = c1?.result ?? (pd_models.challenger?.status === "run" ? "INSUFFICIENT" : "NOT_RUN");
  const two = (v: number) => v.toFixed(2);

  return (
    <div className="mx-auto max-w-[1200px] px-4 pb-32 pt-12 md:px-8 lg:pb-16">
      <Prose>
        <h1 className="font-display" style={{ fontSize: "clamp(40px,5vw,64px)", lineHeight: 1 }}>
          Scorecard
        </h1>
        <p className="mt-3 max-w-[68ch] text-lg" style={{ color: "var(--ink-2)" }}>
          A <Term k="scorecard">scorecard</Term> turns a loan's details into points, and the points into a risk{" "}
          <Term k="grade">grade</Term> from A (safest) to G. Try a loan below, then see how well the scores hold up on loans the model never saw.
        </p>
        <p className="mt-2 max-w-[68ch] text-sm" style={{ color: "var(--ink-3)" }}>
          A points scorecard for 12-month default, graded on a fixed <Term k="master scale">PD master scale</Term>. {pd_models.scaling.pd_label}.
        </p>
      </Prose>

      <section className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {oot && (
          <div>
            <KpiTile label="Gini, out of time" estimate={oot.gini} format={two} />
            <p className="mt-2 px-1 text-[13px] leading-snug" style={{ color: "var(--ink-2)" }}>
              <Term k="Gini">Gini</Term> says how well the score ranks risky loans above safe ones. 0 is a coin flip, 1 is perfect.
            </p>
          </div>
        )}
        {oot && (
          <div>
            <KpiTile label="KS, out of time" estimate={oot.ks} format={two} />
            <p className="mt-2 px-1 text-[13px] leading-snug" style={{ color: "var(--ink-2)" }}>
              <Term k="KS">KS</Term> is the widest gap between defaulters and the rest on the score. Higher means cleaner separation.
            </p>
          </div>
        )}
        {drop && (
          <div>
            <KpiTile label="Gini drop, relative" estimate={drop.relative} format={(v) => fmtPct(v, 1)} badge={<ResultBadge result={drop.rag} />} />
            <p className="mt-2 px-1 text-[13px] leading-snug" style={{ color: "var(--ink-2)" }}>
              How much Gini fell on later loans (<Term k="out of time">out of time</Term>) versus the loans it was built on.
            </p>
          </div>
        )}
        {psi && (
          <div>
            <KpiTile label="Score PSI, train vs out of time" estimate={psi.psi} format={two} badge={<ResultBadge result={psi.rag} />} />
            <p className="mt-2 px-1 text-[13px] leading-snug" style={{ color: "var(--ink-2)" }}>
              <Term k="PSI">PSI</Term> says whether the mix of scores has shifted. Under 0.1 means the borrowers look much the same.
            </p>
          </div>
        )}
      </section>

      <Section title="Try it" intro={<>Pick a preset or enter a loan. Every change recomputes the points, grade, 12-month <Term k="PD">PD</Term> and <Term k="reason codes">reason codes</Term> from the published points table.</>}>
        <Calculator model={pd_models} onResult={onResult} />
      </Section>

      <Section title="Pre-registered rules" intro={<>Each rule was <Term k="pre-registered">written down before</Term> the model was scored. Failures sort first.</>}>
        <Scoreboard rules={collectRules(data, ["pd_models"])} />
      </Section>

      <Section
        title="PD ladder"
        intro={<>Each grade's <Term k="PD">PD</Term> band on a log scale, with the predicted and realised default rate (<Term k="calibration">calibration</Term>). Switch samples: the development test sample is in time, the out-of-time sample (2017-2019, 2021-2024 originations) is where S4b fails in 6 of 7 grades. Your calculator result is highlighted.</>}
      >
        <PdLadder grades={pd_models.grades} calibration={calibration} calibrationOot={calibrationOot} activeGrade={result?.grade} />
      </Section>

      <Section title="Features" intro={<><Term k="information value">Information value</Term> per selected feature. Open a row to see its bins: weight of evidence, points and the default rate in each bin.</>}>
        <FeatureList features={features} bins={pd_models.points_table} />
      </Section>

      <Section
        title="Challenger"
        intro={<>A gradient-boosted <Term k="challenger">challenger</Term> is compared against the scorecard under a <Term k="pre-registered">pre-registered</Term> rule (C1).</>}
      >
        <div className="rounded-xl border p-5 md:p-6" style={{ borderColor: "var(--border)", background: "var(--surface)" }}>
          <div className="flex flex-wrap items-center gap-3">
            <ResultBadge result={challengerResult} />
            <span className="font-display text-xl">
              {challengerResult === "FAIL" ? "Challenger rejected: the scorecard stays" : challengerResult === "PASS" ? "Challenger beat the scorecard" : "Challenger result"}
            </span>
          </div>
          {ch.delta_gini_oot?.value != null && (
            <p className="mt-3 max-w-[68ch] text-sm" style={{ color: "var(--ink-2)" }}>
              Out-of-time Gini change against the scorecard:{" "}
              <span className="tabular font-medium" style={{ color: "var(--ink)" }}>
                {ch.delta_gini_oot.value.toFixed(4)}
              </span>
              {ch.delta_gini_oot.ci_low != null && ch.delta_gini_oot.ci_high != null && (
                <>
                  {" "}
                  (95% <Term k="bootstrap interval">bootstrap interval</Term> {ch.delta_gini_oot.ci_low.toFixed(4)} to {ch.delta_gini_oot.ci_high.toFixed(4)})
                </>
              )}
              . The rule needed the lower end of that interval to clear +0.02.
            </p>
          )}
          {ch.criteria && (
            <ul className="mt-4 space-y-2">
              {ch.criteria.map((c) => (
                <li key={c.criterion} className="flex items-start gap-3 text-sm">
                  <span className="mt-0.5 shrink-0">
                    <ResultBadge result={c.met ? "PASS" : "FAIL"} />
                  </span>
                  <span style={{ color: "var(--ink-2)" }}>{c.criterion}</span>
                </li>
              ))}
            </ul>
          )}
          {c1?.evidence && (
            <details className="mt-4 text-sm">
              <summary className="min-h-[44px] cursor-pointer py-3" style={{ color: "var(--ink-2)" }}>
                Full evidence for rule C1
              </summary>
              <p className="font-mono max-w-[80ch] text-xs leading-relaxed" style={{ color: "var(--ink-3)" }}>
                {c1.evidence}
              </p>
            </details>
          )}
        </div>
      </Section>
      <div id="page-end" aria-hidden />
    </div>
  );
}
