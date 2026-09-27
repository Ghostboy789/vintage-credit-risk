// Every number the Capital, LGD & EAD and ECL sections display must equal the artefact's own
// published value — read the raw JSON here, independently of the page's import path, and check
// the selector functions the pages actually render from give back exactly that value.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { test } from "node:test";
import assert from "node:assert/strict";
import { selectCapital } from "./capital.ts";
import { selectLgdEad } from "./lgd.ts";
import { eclDates, stageTotals } from "./ecl.ts";

const here = dirname(fileURLToPath(import.meta.url));
const artefactsDir = join(here, "../../public/artefacts");
const readArtefact = (name: string) => JSON.parse(readFileSync(join(artefactsDir, `${name}.json`), "utf8"));

test("Capital page: totals and by-grade rows equal artefacts/capital.json exactly", () => {
  const raw = readArtefact("capital");
  const view = selectCapital(raw);

  assert.equal(view.status, raw.status);
  assert.deepEqual(view.byGrade, raw.by_grade);
  assert.deepEqual(view.totals, raw.totals);

  // Cross-check: the published totals equal the sum over by_grade (catches a stale totals field).
  const summed = raw.by_grade.reduce((s: number, g: { rwa: { value: number } }) => s + g.rwa.value, 0);
  assert.ok(
    Math.abs(summed - raw.totals.rwa.value) / raw.totals.rwa.value < 1e-6,
    `totals.rwa (${raw.totals.rwa.value}) should equal the sum over by_grade (${summed})`,
  );
});

test("LGD & EAD section equals artefacts/lgd_ead.json exactly", () => {
  const raw = readArtefact("lgd_ead");
  const view = selectLgdEad(raw);

  assert.deepEqual(view.meanEad, raw.ead.mean_ead);
  assert.deepEqual(view.downturn, raw.downturn_lgd ?? []);
  assert.equal(view.modelUsed, raw.lgd_model?.used_in_ecl ?? false);

  const overall = raw.lgd_segments.find((s: { dimension: string }) => s.dimension === "overall");
  assert.deepEqual(view.overall, overall);

  // Every segment the dimension picker can show is drawn straight from lgd_segments, with none
  // dropped or invented.
  for (const dim of view.dimensions) {
    const rawRows = raw.lgd_segments.filter((s: { dimension: string }) => s.dimension === dim);
    const viewRows = view.segments.filter((s) => s.dimension === dim);
    assert.deepEqual(viewRows, rawRows, `segments for dimension ${dim}`);
  }
});

test("ECL page: dates and stage totals equal artefacts/ecl.json exactly", () => {
  const raw = readArtefact("ecl");
  const dates = eclDates(raw.by_date);

  // Independently recomputed from the raw rows (a plain Set, not the same reduce as the lib).
  const expectedDates = Array.from(new Set<string>(raw.by_date.map((r: { reporting_date: string }) => r.reporting_date))).sort();
  assert.deepEqual(dates, expectedDates);
  assert.ok(dates.length > 0);

  for (const date of [dates[0], dates[Math.floor(dates.length / 2)], dates[dates.length - 1]]) {
    const totals = stageTotals(raw.by_date, date);
    for (const t of totals) {
      const atDateAndStage = raw.by_date.filter(
        (r: { reporting_date: string; stage: string }) => r.reporting_date === date && r.stage === t.stage,
      );
      const expectedN = atDateAndStage.reduce((s: number, r: { n_loans: number }) => s + r.n_loans, 0);
      const expectedEcl = atDateAndStage.reduce(
        (s: number, r: { ecl: { value: number | null } }) => s + (r.ecl.value ?? 0),
        0,
      );
      assert.equal(t.n, expectedN, `n_loans for stage ${t.stage} at ${date}`);
      assert.ok(Math.abs(t.ecl - expectedEcl) < 1e-6, `ecl for stage ${t.stage} at ${date}`);
    }
  }
});
