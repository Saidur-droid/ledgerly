import type { Components } from "react-markdown";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
  a({ children, href }) {
    return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
  },
  table({ children }) {
    return (
      <div
        className="markdown-table-scroll"
        role="region"
        aria-label="Scrollable analysis table"
        tabIndex={0}
      >
        <table>{children}</table>
      </div>
    );
  },
};

function safeUrlTransform(url: string) {
  const normalized = defaultUrlTransform(url);
  if (normalized.startsWith("/") || normalized.startsWith("#") || /^(https?:|mailto:)/i.test(normalized)) {
    return normalized;
  }
  return "";
}

export function MarkdownBody({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        skipHtml
        urlTransform={safeUrlTransform}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export function ChatMarkdown({ content }: { content: string }) {
  return (
    <div className="message-content">
      <MarkdownBody content={content} />
    </div>
  );
}
