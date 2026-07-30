import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const components: Components = {
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

export function MarkdownBody({ content }: { content: string }) {
  return (
    <div className="chat-markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={components}
        skipHtml
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
