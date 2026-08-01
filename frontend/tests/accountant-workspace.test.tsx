import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";

const page=fs.readFileSync(path.join(process.cwd(),"src/app/accountant/page.tsx"),"utf8");
const css=fs.readFileSync(path.join(process.cwd(),"src/app/globals.css"),"utf8");
const api=fs.readFileSync(path.join(process.cwd(),"src/lib/api.ts"),"utf8");

test("accountant dashboard exposes all closing states and client periods",()=>{
 for(const state of ["complete","missing_data","reconciliation_pending","report_due"])assert.match(page,new RegExp(state));
 assert.match(page,/Client workspace periods/); assert.match(api,/getAccountantDashboard/);
});

test("accountant workspace includes accessible mobile and RTL states",()=>{
 assert.match(page,/aria-label="Closing status summary"/); assert.match(page,/role="alert"/);
 assert.match(css,/\[dir="rtl"\] \.accountant-table/); assert.match(css,/@media\(max-width:720px\)/);
});
