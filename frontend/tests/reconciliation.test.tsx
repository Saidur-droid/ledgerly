import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const page = fs.readFileSync(path.join(process.cwd(), "src/app/reconciliation/page.tsx"), "utf8");
const api = fs.readFileSync(path.join(process.cwd(), "src/lib/api.ts"), "utf8");
const css = fs.readFileSync(path.join(process.cwd(), "src/app/globals.css"), "utf8");

test("reconciliation review exposes classifications, filters, and evidence", () => {
  for (const text of ["exact", "possible", "unmatched", "exceptions", "Search transactions", "MATCH EVIDENCE", "Review note"]) assert.match(page, new RegExp(text, "i"));
});

test("manual, balance, completion and reopen actions use authenticated API helpers", () => {
  for (const helper of ["manualReconciliationMatch", "unmatchReconciliation", "reviewReconciliationMatch", "updateReconciliationBalance", "bulk-approve-exact", "complete", "reopen"]) assert.match(api, new RegExp(helper));
  assert.match(page, /Object\.values\(run\.checklist\)/);
  assert.match(page, /run\.status === "completed"/);
});

test("reconciliation layout has responsive and accessible states", () => {
  assert.match(css, /@media\(max-width:650px\)/);
  assert.match(page, /role="tablist"/);
  assert.match(page, /role="alert"/);
  assert.match(page, /No transactions match these filters/);
  assert.match(page, /Retry/);
});
