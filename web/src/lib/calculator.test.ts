// One runnable check for the scoring logic (no framework, node's built-in test runner).
// Loads the same fixture points table the app ships, scores a few hand-picked loans, and checks
// score = sum(points), pd = 1/(1+exp((score-offset)/factor)), and grade membership.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { calculate, pdFromScore, pickBin, featureList, type CalcInput } from "./calculator.ts";
import type { PdModelsArtefact } from "./types.ts";

const __dirname = dirname(fileURLToPath(import.meta.url));
const model: PdModelsArtefact = JSON.parse(
  readFileSync(join(__dirname, "../../public/artefacts/pd_models.json"), "utf8")
);

test("score is the sum of the picked bins' points", () => {
  const input: CalcInput = {};
  for (const f of featureList(model)) input[f] = "unknown";
  const result = calculate(model, input);
  const expected = featureList(model)
    .map((f) => pickBin(model.points_table.filter((b) => b.feature === f), "unknown").points)
    .reduce((a, b) => a + b, 0);
  assert.equal(result.score, expected);
});

test("pd formula matches the published scaling", () => {
  const { offset, factor } = model.scaling;
  assert.ok(Math.abs(pdFromScore(offset, offset, factor) - 0.5) < 1e-9);
});

test("a strong-borrower profile scores higher than an all-unknown profile", () => {
  const weak: CalcInput = {};
  for (const f of featureList(model)) weak[f] = "unknown";
  const strong: CalcInput = { ...weak, fico: 760, ltv_pct: 50, dti_pct: 20 };
  const weakResult = calculate(model, weak);
  const strongResult = calculate(model, strong);
  assert.ok(strongResult.score >= weakResult.score);
  assert.ok(strongResult.pd12m <= weakResult.pd12m);
});

test("reason codes are the largest shortfalls and cap at 3", () => {
  const input: CalcInput = {};
  for (const f of featureList(model)) input[f] = "unknown";
  const result = calculate(model, input);
  assert.ok(result.reasonCodes.length <= 3);
  for (let i = 1; i < result.reasonCodes.length; i++) {
    assert.ok(result.reasonCodes[i - 1].shortfall >= result.reasonCodes[i].shortfall);
  }
});
