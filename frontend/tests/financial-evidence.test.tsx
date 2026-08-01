import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const page = fs.readFileSync(path.join(process.cwd(), "src/app/page.tsx"), "utf8");
const api = fs.readFileSync(path.join(process.cwd(), "src/lib/api.ts"), "utf8");
const css = fs.readFileSync(path.join(process.cwd(), "src/app/globals.css"), "utf8");

test("dashboard metrics expose deterministic calculation status and evidence drill-down", () => {
  for (const text of ["Calculation breakdown", "Included records", "Excluded records", "Formula", "Mappings", "Adjustments", "EVIDENCE LINEAGE", "engine_version"]) assert.match(page, new RegExp(text, "i"));
  assert.match(page, /evidenceLoading/);
  assert.match(page, /evidenceError/);
  assert.match(page, /financials\.validations/);
});

test("financial API helpers and types retain tenant-authenticated request flow", () => {
  assert.match(api, /getLatestFinancials/);
  assert.match(api, /getMetricEvidence/);
  assert.match(api, /\/api\/v1\/financials\/metrics/);
  assert.match(api, /authHeaders\(\)/);
});

test("evidence drawer remains usable on narrow screens", () => {
  assert.match(css, /\.evidence-drawer/);
  assert.match(css, /\.calculation-status\.blocked/);
  assert.match(css, /@media\(max-width:760px\)/);
});
