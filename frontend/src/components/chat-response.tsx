import type {
  ActionsSection,
  AnalysisMetric,
  AnalysisSection,
  AnalysisValue,
  AskLedgerlyResponse,
  ForecastSection,
  ListSection,
  MetricsSection,
  NoticeSection,
  RisksSection,
  ScenariosSection,
  TableSection,
  TextSection,
} from "@/lib/api";
import { parseAskLedgerlyResponse } from "@/lib/api";

import { ChatMarkdown, MarkdownBody } from "./chat-markdown";

const MALFORMED_RESPONSE =
  "Ledgerly could not safely display this analysis. Please try again.";

function assertNever(value: never): never {
  throw new Error(`Unhandled Ask Ledgerly contract variant: ${typeof value}`);
}

function displayValue(value: AnalysisValue): string {
  if (value === null) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return new Intl.NumberFormat("en-US").format(value);
  return value;
}

function Heading({ value }: { value?: string | null }) {
  return value ? <h3>{value}</h3> : null;
}

function Metrics({ items }: { items: AnalysisMetric[] }) {
  return <div className="analysis-card-grid">{items.map((item, index) =>
    <div className="analysis-detail-card" key={`${item.label}-${index}`}>
      <span>{item.label}</span><strong>{displayValue(item.value)}</strong>
      {item.detail && <small>{item.detail}</small>}
    </div>)}</div>;
}

function TextSectionView({ section }: { section: TextSection }) {
  return <section className="analysis-section"><Heading value={section.heading} /><MarkdownBody content={section.markdown} /></section>;
}

function MetricsSectionView({ section }: { section: MetricsSection }) {
  return <section className="analysis-section"><Heading value={section.heading} /><Metrics items={section.items} /></section>;
}

function TableSectionView({ section }: { section: TableSection }) {
  return <section className="analysis-section"><Heading value={section.heading} />
    <div className="markdown-table-scroll structured-table-scroll" role="region" aria-label={section.heading ?? "Scrollable analysis table"} tabIndex={0}>
      <table className="structured-analysis-table">
        <thead><tr>{section.columns.map((column, index) => <th key={`${column.label}-${index}`} className={`align-${column.align}`}>{column.label}</th>)}</tr></thead>
        <tbody>{section.rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, columnIndex) => <td key={columnIndex} className={`align-${section.columns[columnIndex].align}`}>{displayValue(cell)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  </section>;
}

function ListSectionView({ section }: { section: ListSection }) {
  const items = section.items.map((item, index) => <li key={`${item}-${index}`}>{item}</li>);
  return <section className="analysis-section"><Heading value={section.heading} />{section.style === "numbered" ? <ol>{items}</ol> : <ul>{items}</ul>}</section>;
}

function ScenariosSectionView({ section }: { section: ScenariosSection }) {
  return <section className="analysis-section"><Heading value={section.heading} />{section.scenarios.map((scenario, index) =>
    <article className="analysis-subsection" key={`${scenario.name}-${index}`}><h4>{scenario.name}</h4>
      {scenario.assumptions.length > 0 && <ul>{scenario.assumptions.map((item, itemIndex) => <li key={`${item}-${itemIndex}`}>{item}</li>)}</ul>}
      <Metrics items={scenario.outcomes} />
    </article>)}</section>;
}

function ForecastSectionView({ section }: { section: ForecastSection }) {
  return <section className="analysis-section"><Heading value={section.heading} /><MarkdownBody content={section.summary} />
    {section.horizon && <p><strong>Horizon:</strong> {section.horizon}</p>}
    {section.methodology && <MarkdownBody content={section.methodology} />}
    {section.metrics.length > 0 && <Metrics items={section.metrics} />}
    {section.caveats.length > 0 && <ul>{section.caveats.map((item, index) => <li key={`${item}-${index}`}>{item}</li>)}</ul>}
  </section>;
}

function RisksSectionView({ section }: { section: RisksSection }) {
  return <section className="analysis-section"><Heading value={section.heading} /><ul className="analysis-risk-list">{section.items.map((risk, index) =>
    <li key={`${risk.label}-${index}`}><strong>{risk.label}</strong> <span className={`analysis-badge ${risk.severity}`}>{risk.severity}</span><p>{risk.detail}</p></li>)}</ul></section>;
}

function ActionsSectionView({ section }: { section: ActionsSection }) {
  return <section className="analysis-section"><Heading value={section.heading} /><ol>{section.items.map((action, index) =>
    <li key={`${action.label}-${index}`}><strong>{action.label}</strong>{action.detail && <p>{action.detail}</p>}</li>)}</ol></section>;
}

function NoticeSectionView({ section }: { section: NoticeSection }) {
  return <section className={`analysis-notice ${section.tone}`} role={section.tone === "error" ? "alert" : "status"}><Heading value={section.heading} /><p>{section.message}</p></section>;
}

function SectionRenderer({ section }: { section: AnalysisSection }) {
  switch (section.type) {
    case "text": return <TextSectionView section={section} />;
    case "metrics": return <MetricsSectionView section={section} />;
    case "table": return <TableSectionView section={section} />;
    case "list": return <ListSectionView section={section} />;
    case "scenarios": return <ScenariosSectionView section={section} />;
    case "forecast": return <ForecastSectionView section={section} />;
    case "risks": return <RisksSectionView section={section} />;
    case "actions": return <ActionsSectionView section={section} />;
    case "notice": return <NoticeSectionView section={section} />;
    default: return assertNever(section);
  }
}

function ValidatedResponse({ response }: { response: AskLedgerlyResponse }) {
  switch (response.type) {
    case "markdown": return <ChatMarkdown content={response.content} />;
    case "structured":
      return <div className="message-content structured-analysis">
        {response.sections.map((section, index) => <SectionRenderer section={section} key={`${section.type}-${index}`} />)}
        {response.sections.length === 0 && <p>No analysis details were returned.</p>}
      </div>;
    case "policy_notice":
      return <div className="message-content structured-analysis">
        {response.sections.map((section, index) => <SectionRenderer section={section} key={`${section.type}-${index}`} />)}
        <section className="analysis-notice policy" role="status"><h3>Scope notice</h3><p>{response.content}</p></section>
      </div>;
    case "error":
      return <div className="message-content unsupported-chat-response" role="alert"><p>{response.content}</p></div>;
    default: return assertNever(response);
  }
}

export function AskLedgerlyResponseRenderer({ response }: { response: unknown }) {
  const validated = parseAskLedgerlyResponse(response);
  return validated
    ? <ValidatedResponse response={validated} />
    : <div className="message-content unsupported-chat-response" role="alert"><p>{MALFORMED_RESPONSE}</p></div>;
}
