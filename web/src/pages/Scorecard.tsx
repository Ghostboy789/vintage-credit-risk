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

interface Disc {
  sample: string;
  definition: string;
  model: string;
  gini: Estimate;
  ks: Estimate;
}

function Section({ title, intro, children }: { title: string; intro: string; children: ReactNode }) {
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
  const calibration = ((pd_models.calibration ?? []) as {
    sample: string;
    definition: string;
    grade: string;
    n: number;
    mean_pd: number;
    realised_rate: Estimate;
    result: string;
  }[]).filter((c) => c.sample === "dev_test" && c.definition === "primary");
  const challengerStatus = pd_models.challenger?.status ?? "not_run";
  const two = (v: number) => v.toFixed(2);

  return (
    <div className="mx-auto max-w-[1200px] px-4 pb-32 pt-12 md:px-8 lg:pb-16">
      <Prose>
        <h1 className="font-display" style={{ fontSize: "clamp(40px,5vw,64px)", lineHeight: 1 }}>
          Scorecard
        </h1>
        <p className="mt-3 max-w-[68ch] text-lg" style={{ color: "var(--ink-2)" }}>
          A points scorecard for 12-month default, graded on a fixed PD master scale. {pd_models.scaling.pd_label}.
        </p>
      </Prose>

      <section className="mt-10 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {oot && <KpiTile label="Gini, out of time" estimate={oot.gini} format={two} />}
        {oot && <KpiTile label="KS, out of time" estimate={oot.ks} format={two} />}
        {drop && <KpiTile label="Gini drop, relative" estimate={drop.relative} format={(v) => fmtPct(v, 1)} badge={<ResultBadge result={drop.rag} />} />}
        {psi && <KpiTile label="Score PSI, train vs out of time" estimate={psi.psi} format={two} badge={<ResultBadge result={psi.rag} />} />}
      </section>

      <Section title="Try it" intro="Pick a preset or enter a loan. Every change recomputes the points, grade, 12-month PD and reason codes from the published points table.">
        <Calculator model={pd_models} onResult={onResult} />
      </Section>

      <Section title="Pre-registered rules" intro="Each rule was written down before the model was scored. Failures sort first.">
        <Scoreboard rules={collectRules(data, ["pd_models"])} />
      </Section>

      <Section
        title="PD ladder"
        intro="Each grade's PD band on a log scale, with the predicted and realised default rate on the test sample. Your calculator result is highlighted."
      >
        <PdLadder grades={pd_models.grades} calibration={calibration} activeGrade={result?.grade} />
      </Section>

      <Section title="Features" intro="Information value per selected feature. Open a row to see its bins: weight of evidence, points and the default rate in each bin.">
        <FeatureList features={features} bins={pd_models.points_table} />
      </Section>

      <Section title="Challenger" intro="A gradient-boosted challenger is compared against the scorecard under a pre-registered rule.">
        <div className="flex items-center gap-3 text-sm">
          <ResultBadge result={challengerStatus === "not_run" ? "NOT_RUN" : challengerStatus} />
          <span style={{ color: "var(--ink-2)" }}>Not promoted unless it beats the champion under that rule, on the held-out sample.</span>
        </div>
      </Section>
    </div>
  );
}
