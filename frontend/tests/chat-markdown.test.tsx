import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { ChatMarkdown } from "../src/components/chat-markdown";
import { AskLedgerlyResponseRenderer } from "../src/components/chat-response";
import { parseAskLedgerlyResponse } from "../src/lib/api";

const fixtures = JSON.parse(
  readFileSync("../contracts/ask-ledgerly-v1.fixtures.json", "utf8"),
) as Record<string, unknown>;

test("validates and renders the shared markdown contract", () => {
  assert.ok(parseAskLedgerlyResponse(fixtures.markdown));
  const html = renderToStaticMarkup(
    <AskLedgerlyResponseRenderer response={fixtures.markdown} />,
  );
  assert.match(html, /<h2>Revenue<\/h2>/);
  assert.match(html, /<strong>Revenue:<\/strong>/);
  assert.match(html, /rel="noopener noreferrer"/);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("renders every structured section type through one renderer", () => {
  assert.ok(parseAskLedgerlyResponse(fixtures.structured));
  const html = renderToStaticMarkup(
    <AskLedgerlyResponseRenderer response={fixtures.structured} />,
  );
  for (const expected of [
    "Audit summary", "Headline metrics", "Monthly ranking", "Observations",
    "Scenarios", "Forecast", "Risks", "Action plan",
  ]) assert.match(html, new RegExp(expected));
  assert.match(html, /<table class="structured-analysis-table">/);
  assert.match(html, /December 2025/);
  assert.match(html, /Revenue \+5%/);
  assert.match(html, /not a guarantee/);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("renders GFM tables without raw pipe syntax and blocks raw HTML", () => {
  const html = renderToStaticMarkup(
    <ChatMarkdown content={"| Month | Profit |\n|---|---:|\n| Jan | $10 |\n\n<script>alert(1)</script>"} />,
  );
  assert.match(html, /<table>/);
  assert.doesNotMatch(html, /\|---/);
  assert.doesNotMatch(html, /<script/i);
});

test("sanitizes dangerous Markdown URLs", () => {
  const html = renderToStaticMarkup(
    <ChatMarkdown content={"[bad](javascript:alert(1)) [good](https://example.com)"} />,
  );
  assert.doesNotMatch(html, /javascript:/i);
  assert.match(html, /href="https:\/\/example.com"/);
});

test("rejects malformed, unknown, version-mismatched, and nested payloads safely", () => {
  const malformed = [
    null,
    {},
    { ...fixtures.markdown as object, schema_version: 2 },
    { ...fixtures.structured as object, sections: [{ type: "unknown" }] },
    { ...fixtures.markdown as object, content: { nested: true } },
    { ...fixtures.structured as object, sections: [{ type: "list", style: "bulleted", items: [{}] }] },
    { ...fixtures.structured as object, sections: [{ type: "text", markdown: { nested: { again: true } } }] },
    { ...fixtures.markdown as object, content: "x".repeat(20_001) },
  ];
  for (const payload of malformed) {
    assert.equal(parseAskLedgerlyResponse(payload), null);
    const html = renderToStaticMarkup(
      <AskLedgerlyResponseRenderer response={payload} />,
    );
    assert.match(html, /could not safely display/);
    assert.doesNotMatch(html, /\[object Object\]/);
    assert.doesNotMatch(html, /nested/);
  }
});

test("fuzzed JSON shapes never crash, stringify objects, or create blank bubbles", () => {
  const values: unknown[] = [
    undefined, true, false, 0, 1, "", "text", [], [null], [{ a: 1 }],
    { type: "markdown" }, { schema_version: 1 }, { sections: [[], {}] },
  ];
  for (let index = 0; index < 150; index += 1) {
    values.push({
      schema_version: index % 3,
      type: index % 2 ? "structured" : "other",
      content: index % 4 ? null : { index },
      sections: Array.from({ length: index % 5 }, (_, item) => ({ type: `fuzz-${item}`, value: { index } })),
    });
  }
  for (const value of values) {
    const html = renderToStaticMarkup(
      <AskLedgerlyResponseRenderer response={value} />,
    );
    assert.ok(html.trim().length > 0);
    assert.doesNotMatch(html, /\[object Object\]/);
    assert.doesNotMatch(html, /<script/i);
  }
});

test("table and sidebar CSS contain horizontal and mobile overflow guards", () => {
  const css = readFileSync("src/app/globals.css", "utf8");
  assert.match(css, /\.markdown-table-scroll\s*\{[\s\S]*?overflow-x:\s*auto/);
  assert.match(css, /\.messages\s*\{[\s\S]*?overflow-x:\s*hidden/);
  assert.match(css, /\.structured-analysis\s*\{[\s\S]*?max-width:\s*100%/);
  assert.match(css, /@media \(max-width: 480px\)[\s\S]*?\.chat-panel\s*\{\s*width:\s*100%/);
});

test("empty structured sections render a readable nonblank state", () => {
  const value = {
    ...(fixtures.structured as object),
    sections: [],
  };
  assert.ok(parseAskLedgerlyResponse(value));
  const html = renderToStaticMarkup(
    <AskLedgerlyResponseRenderer response={value} />,
  );
  assert.match(html, /No analysis details were returned/);
});

test("renders policy notices after allowed analytical sections", () => {
  const value = {
    ...(fixtures.structured as object),
    type: "policy_notice",
    content: "Ledgerly cannot guarantee future outcomes.",
  };
  assert.ok(parseAskLedgerlyResponse(value));
  const html = renderToStaticMarkup(
    <AskLedgerlyResponseRenderer response={value} />,
  );
  assert.match(html, /Monthly ranking/);
  assert.match(html, /Scope notice/);
  assert.match(html, /cannot guarantee future outcomes/);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("renders validated errors and rejects null content safely", () => {
  const error = {
    schema_version: 1,
    type: "error",
    content: "Analysis unavailable. Reference: safe-id",
    sections: [],
    correlation_id: "safe-error-id",
  };
  const invalid = { ...error, content: null };
  assert.ok(parseAskLedgerlyResponse(error));
  assert.equal(parseAskLedgerlyResponse(invalid), null);
  const html = renderToStaticMarkup(
    <AskLedgerlyResponseRenderer response={error} />,
  );
  assert.match(html, /Analysis unavailable/);
  assert.doesNotMatch(html, /\[object Object\]/);
});
