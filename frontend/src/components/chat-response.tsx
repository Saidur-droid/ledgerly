import type {
  AnalysisCard,
  AnalysisColumn,
  AnalysisSection,
  AnalysisTable,
  AnalysisValue,
  RankingMetadata,
  StructuredAnalysis,
} from "@/lib/api";

import { ChatMarkdown, MarkdownBody } from "./chat-markdown";

const UNSUPPORTED_RESPONSE_MESSAGE =
  "Ledgerly received an unsupported analysis response. Please try the question again.";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isAnalysisValue(value: unknown): value is AnalysisValue {
  return (
    value === null ||
    typeof value === "string" ||
    (typeof value === "number" && Number.isFinite(value)) ||
    typeof value === "boolean"
  );
}

function isAnalysisColumn(value: unknown): value is AnalysisColumn {
  return (
    isRecord(value) &&
    typeof value.key === "string" &&
    typeof value.label === "string" &&
    (value.align === "left" || value.align === "right")
  );
}

function isAnalysisTable(value: unknown): value is AnalysisTable {
  return (
    isRecord(value) &&
    Array.isArray(value.columns) &&
    value.columns.length > 0 &&
    value.columns.every(isAnalysisColumn) &&
    Array.isArray(value.rows) &&
    value.rows.every(
      (row) =>
        isRecord(row) &&
        Object.values(row).every(isAnalysisValue),
    )
  );
}

function isAnalysisCard(value: unknown): value is AnalysisCard {
  return (
    isRecord(value) &&
    typeof value.label === "string" &&
    typeof value.value === "string" &&
    (value.detail === undefined ||
      value.detail === null ||
      typeof value.detail === "string")
  );
}

function isAnalysisSection(value: unknown): value is AnalysisSection {
  return (
    isRecord(value) &&
    typeof value.heading === "string" &&
    (value.markdown === undefined ||
      value.markdown === null ||
      typeof value.markdown === "string") &&
    (value.table === undefined ||
      value.table === null ||
      isAnalysisTable(value.table)) &&
    (value.cards === undefined ||
      (Array.isArray(value.cards) && value.cards.every(isAnalysisCard)))
  );
}

function isRankingMetadata(value: unknown): value is RankingMetadata {
  return (
    isRecord(value) &&
    typeof value.formula === "string" &&
    isRecord(value.weights) &&
    Object.values(value.weights).every(
      (weight) => typeof weight === "number" && Number.isFinite(weight),
    ) &&
    typeof value.normalization === "string" &&
    typeof value.first_period === "string" &&
    typeof value.interpretation === "string"
  );
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

export function isStructuredAnalysis(
  value: unknown,
): value is StructuredAnalysis {
  return (
    isRecord(value) &&
    value.kind === "structured_analysis" &&
    typeof value.title === "string" &&
    value.title.length > 0 &&
    (value.summary === undefined ||
      value.summary === null ||
      typeof value.summary === "string") &&
    (value.sections === undefined ||
      (Array.isArray(value.sections) &&
        value.sections.every(isAnalysisSection))) &&
    (value.scoring === undefined ||
      value.scoring === null ||
      isRankingMetadata(value.scoring)) &&
    (value.risks === undefined || isStringArray(value.risks)) &&
    (value.action_plan === undefined ||
      isStringArray(value.action_plan))
  );
}

export function formatUnsupportedChatAnswer(
  value: unknown,
  development = process.env.NODE_ENV === "development",
): string {
  if (!development) {
    return UNSUPPORTED_RESPONSE_MESSAGE;
  }
  try {
    return JSON.stringify(value, null, 2) ?? "null";
  } catch {
    return "Unable to serialize the unsupported response.";
  }
}

function displayValue(value: AnalysisValue | undefined): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function AnalysisTableView({ table }: { table: AnalysisTable }) {
  return (
    <div
      className="markdown-table-scroll structured-table-scroll"
      role="region"
      aria-label="Scrollable analysis table"
      tabIndex={0}
    >
      <table className="structured-analysis-table">
        <thead>
          <tr>
            {table.columns.map((column) => (
              <th key={column.key} className={`align-${column.align}`}>
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {table.columns.map((column) => (
                <td
                  key={column.key}
                  className={`align-${column.align}`}
                >
                  {displayValue(row[column.key])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalysisCards({ cards }: { cards: AnalysisCard[] }) {
  return (
    <div className="analysis-card-grid">
      {cards.map((card) => (
        <div className="analysis-detail-card" key={`${card.label}-${card.value}`}>
          <span>{card.label}</span>
          <strong>{card.value}</strong>
          {card.detail && <small>{card.detail}</small>}
        </div>
      ))}
    </div>
  );
}

function AnalysisSectionView({ section }: { section: AnalysisSection }) {
  return (
    <section className="analysis-section">
      <h3>{section.heading}</h3>
      {section.markdown && <MarkdownBody content={section.markdown} />}
      {section.cards && section.cards.length > 0 && (
        <AnalysisCards cards={section.cards} />
      )}
      {section.table && <AnalysisTableView table={section.table} />}
    </section>
  );
}

function ScoringDetails({ scoring }: { scoring: RankingMetadata }) {
  return (
    <section className="analysis-section scoring-details">
      <h3>Ranking method</h3>
      <p>
        <strong>Composite score:</strong> <code>{scoring.formula}</code>
      </p>
      <dl className="weight-list">
        {Object.entries(scoring.weights).map(([metric, weight]) => (
          <div key={metric}>
            <dt>{metric.replaceAll("_", " ")}</dt>
            <dd>{weight}%</dd>
          </div>
        ))}
      </dl>
      <p>{scoring.normalization}</p>
      <p>{scoring.interpretation}</p>
      <p>{scoring.first_period}</p>
    </section>
  );
}

function TextList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <section className="analysis-section">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function StructuredAnalysisView({
  analysis,
}: {
  analysis: StructuredAnalysis;
}) {
  return (
    <div className="message-content structured-analysis">
      <h2>{analysis.title}</h2>
      {analysis.summary && <MarkdownBody content={analysis.summary} />}
      {(analysis.sections ?? []).map((section, index) => (
        <AnalysisSectionView
          section={section}
          key={`${section.heading}-${index}`}
        />
      ))}
      {analysis.scoring && <ScoringDetails scoring={analysis.scoring} />}
      {analysis.risks && analysis.risks.length > 0 && (
        <TextList title="Risks" items={analysis.risks} />
      )}
      {analysis.action_plan && analysis.action_plan.length > 0 && (
        <TextList title="Action plan" items={analysis.action_plan} />
      )}
    </div>
  );
}

export function ChatResponseContent({ content }: { content: unknown }) {
  if (typeof content === "string") {
    return <ChatMarkdown content={content} />;
  }
  if (isStructuredAnalysis(content)) {
    return <StructuredAnalysisView analysis={content} />;
  }
  const development = process.env.NODE_ENV === "development";
  const fallback = formatUnsupportedChatAnswer(content, development);
  return (
    <div className="message-content unsupported-chat-response">
      {development ? <pre>{fallback}</pre> : <p>{fallback}</p>}
    </div>
  );
}
