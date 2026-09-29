import { test } from "node:test";
import assert from "node:assert/strict";
import { codeLabel } from "./labels.ts";

test("codeLabel turns segment and driver codes into plain text", () => {
  assert.equal(codeLabel("60_80"), "60–80%");
  assert.equal(codeLabel("gt_95"), "Over 95%");
  assert.equal(codeLabel("le_60"), "60% or less");
  assert.equal(codeLabel("pd_deterioration"), "PD deterioration");
  assert.equal(codeLabel("missing"), "Missing");
});
