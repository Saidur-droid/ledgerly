import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { renderToStaticMarkup } from "react-dom/server";

import { ChatMarkdown } from "../src/components/chat-markdown";

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
