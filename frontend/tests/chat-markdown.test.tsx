import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { ChatMarkdown } from "../src/components/chat-markdown";
import {
  ChatResponseContent,
  formatUnsupportedChatAnswer,
  isStructuredAnalysis,
} from "../src/components/chat-response";
import type { StructuredAnalysis } from "../src/lib/api";

const structuredAnswer: StructuredAnalysis = {
  kind: "structured_analysis",
  title: "Monthly performance ranking",
  summary: "**36 periods** analyzed.",
  sections: [
    {
      heading: "Best months",
      table: {
        columns: [
          { key: "month", label: "Month", align: "left" },
          { key: "profit", label: "Profit", align: "right" },
        ],
        rows: [
          { month: "December 2025", profit: "$82,000.00" },
        ],
      },
    },
  ],
  scoring: {
    formula: "40% profit + 35% net margin + 25% revenue growth",
    weights: { profit: 40, net_margin: 35, revenue_growth: 25 },
    normalization: "Inputs are min–max normalized.",
    first_period: "The first period receives a neutral growth score.",
    interpretation: "The highest-profit month may not rank first.",
  },
  risks: ["Revenue declined in two periods."],
  action_plan: ["Review the persisted monthly rows."],
};

test("renders GitHub-flavored Markdown tables without raw pipe syntax", () => {
  const html = renderToStaticMarkup(
    <ChatMarkdown
      content={[
        "### Best months",
        "",
        "| Month | Profit |",
        "|---|---:|",
        "| January 2026 | $10,000 |",
      ].join("\n")}
    />,
  );

  assert.match(html, /<h3>Best months<\/h3>/);
  assert.match(html, /<table>/);
  assert.match(html, /<th[^>]*>Month<\/th>/);
  assert.match(html, /<td[^>]*>January 2026<\/td>/);
  assert.doesNotMatch(html, /\|---/);
  assert.doesNotMatch(html, /\| Month \|/);
});

test("supports lists, bold text, numbered lists, and inline code", () => {
  const html = renderToStaticMarkup(
    <ChatMarkdown
      content={[
        "## Method",
        "",
        "- **Profit** is normalized",
        "- Margin is weighted",
        "",
        "1. Sort dates",
        "2. Calculate `growth`",
      ].join("\n")}
    />,
  );

  assert.match(html, /<h2>Method<\/h2>/);
  assert.match(html, /<ul>/);
  assert.match(html, /<ol>/);
  assert.match(html, /<strong>Profit<\/strong>/);
  assert.match(html, /<code>growth<\/code>/);
});

test("does not render malicious raw HTML", () => {
  const html = renderToStaticMarkup(
    <ChatMarkdown
      content={'<script>alert("xss")</script><img src=x onerror="alert(1)">'}
    />,
  );

  assert.doesNotMatch(html, /<script/i);
  assert.doesNotMatch(html, /<img/i);
  assert.doesNotMatch(html, /onerror/i);
});

test("wraps tables in a keyboard-accessible horizontal scroll region", () => {
  const html = renderToStaticMarkup(
    <ChatMarkdown content={"| A | B |\n|---|---|\n| 1 | 2 |"} />,
  );
  const css = readFileSync("src/app/globals.css", "utf8");

  assert.match(html, /class="markdown-table-scroll"/);
  assert.match(html, /role="region"/);
  assert.match(html, /tabindex="0"/);
  assert.match(
    css,
    /\.markdown-table-scroll\s*\{[\s\S]*?max-width:\s*100%/,
  );
  assert.match(
    css,
    /\.markdown-table-scroll\s*\{[\s\S]*?overflow-x:\s*auto/,
  );
  assert.match(css, /\.message\s*\{[\s\S]*?min-width:\s*0/);
  assert.match(css, /\.chat-markdown th,[\s\S]*?text-align:\s*right/);
  assert.match(
    css,
    /\.chat-markdown th:nth-child\(2\),[\s\S]*?text-align:\s*left/,
  );
});

test("renders a plain string response through safe Markdown", () => {
  const html = renderToStaticMarkup(
    <ChatResponseContent content={"**Revenue:** $100"} />,
  );

  assert.match(html, /<strong>Revenue:<\/strong>/);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("renders a structured response with tables and ranking metadata", () => {
  const html = renderToStaticMarkup(
    <ChatResponseContent content={structuredAnswer} />,
  );

  assert.equal(isStructuredAnalysis(structuredAnswer), true);
  assert.match(html, /Monthly performance ranking/);
  assert.match(html, /<table class="structured-analysis-table">/);
  assert.match(html, /December 2025/);
  assert.match(
    html,
    /40% profit \+ 35% net margin \+ 25% revenue growth/,
  );
  assert.match(html, /Inputs are min–max normalized/);
  assert.match(html, /Risks/);
  assert.match(html, /Action plan/);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("accepts structured responses with mixed optional fields", () => {
  const mixed = {
    kind: "structured_analysis",
    title: "Scenario analysis",
    sections: [
      {
        heading: "Scenario",
        markdown: "Revenue increases by **5%**.",
        cards: [
          { label: "Projected revenue", value: "$105,000" },
          {
            label: "Margin",
            value: "22%",
            detail: "Mechanical scenario only.",
          },
        ],
        table: {
          columns: [
            { key: "case", label: "Scenario", align: "left" },
            { key: "revenue", label: "Revenue", align: "right" },
          ],
          rows: [
            { case: "Baseline", revenue: "$100,000" },
            { case: "Illustrative", revenue: "$105,000" },
          ],
        },
      },
      {
        heading: "Forecast",
        markdown: "A historical projection, **not a guarantee**.",
      },
    ],
  };
  const html = renderToStaticMarkup(
    <ChatResponseContent content={mixed} />,
  );

  assert.equal(isStructuredAnalysis(mixed), true);
  assert.match(html, /Scenario analysis/);
  assert.match(html, /<strong>5%<\/strong>/);
  assert.match(html, /Projected revenue/);
  assert.match(html, /Mechanical scenario only/);
  assert.match(html, /Illustrative/);
  assert.match(html, /Forecast/);
  assert.match(html, /<strong>not a guarantee<\/strong>/);
  assert.doesNotMatch(html, /\[object Object\]/);
});

test("uses safe fallbacks for null and invalid response payloads", () => {
  const invalid = { unexpected: { nested: true } };
  const nullHtml = renderToStaticMarkup(
    <ChatResponseContent content={null} />,
  );
  const invalidHtml = renderToStaticMarkup(
    <ChatResponseContent content={invalid} />,
  );
  const developmentDetails = formatUnsupportedChatAnswer(invalid, true);
  const productionMessage = formatUnsupportedChatAnswer(invalid, false);

  assert.equal(isStructuredAnalysis(null), false);
  assert.equal(isStructuredAnalysis(invalid), false);
  assert.match(nullHtml, /unsupported analysis response/);
  assert.match(invalidHtml, /unsupported analysis response/);
  assert.match(developmentDetails, /"nested": true/);
  assert.doesNotMatch(productionMessage, /nested/);
  assert.doesNotMatch(nullHtml, /\[object Object\]/);
  assert.doesNotMatch(invalidHtml, /\[object Object\]/);
});

test("structured content cannot inject executable HTML", () => {
  const malicious = {
    ...structuredAnswer,
    title: "<img src=x onerror=alert(1)>",
    summary: '<script>alert("xss")</script>Safe summary',
    sections: [
      {
        heading: "<script>bad()</script>",
        markdown: '<iframe src="javascript:alert(1)"></iframe>Safe section',
      },
    ],
  };
  const html = renderToStaticMarkup(
    <ChatResponseContent content={malicious} />,
  );

  assert.equal(isStructuredAnalysis(malicious), true);
  assert.doesNotMatch(html, /<script/i);
  assert.doesNotMatch(html, /<img/i);
  assert.doesNotMatch(html, /<iframe/i);
  assert.doesNotMatch(html, /\[object Object\]/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
});
