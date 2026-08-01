"use client";

import { useEffect, useRef } from "react";
import { ArrowUp, ChevronDown, Database, RotateCcw, Sparkles } from "lucide-react";

import type { AskLedgerlyResponse } from "@/lib/api";
import { AskLedgerlyResponseRenderer } from "./chat-response";

export const ASK_LEDGERLY_SUGGESTIONS = [
  "Which customer is most overdue?",
  "Why did profit decrease this month?",
  "Will I face a cash shortage in the next 30 days?",
  "Which transactions need review?",
  "Where is most of my cash being spent?",
] as const;

function textDirection(value: string): "rtl" | "ltr" {
  return /[\u0590-\u08ff\ufb1d-\ufefc]/.test(value) ? "rtl" : "ltr";
}

type AskLedgerlyProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (question?: string) => void;
  onRetry: () => void;
  response: AskLedgerlyResponse | null;
  askedQuestion: string;
  loading: boolean;
  enabled: boolean;
  error: string;
  confidenceLabel?: string;
};

export function AskLedgerly({
  value,
  onChange,
  onSubmit,
  onRetry,
  response,
  askedQuestion,
  loading,
  enabled,
  error,
  confidenceLabel,
}: AskLedgerlyProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const direction = textDirection(value || askedQuestion);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 176)}px`;
  }, [value]);

  return (
    <section className="ask-ledgerly" id="ask-ledgerly" aria-labelledby="ask-ledgerly-title">
      <div className="ask-ledgerly-heading">
        <div className="ask-ledgerly-mark" aria-hidden="true"><Sparkles size={20} /></div>
        <div>
          <p>LEDGERLY AI</p>
          <h2 id="ask-ledgerly-title">Ask your numbers a question.</h2>
          <span>Direct answers, grounded in your uploaded business data.</span>
        </div>
        <span className="data-grounded"><Database size={13} /> Private to this workspace</span>
      </div>

      <div className={`ask-composer-shell ${loading ? "is-loading" : ""}`}>
        <label className="sr-only" htmlFor="ask-ledgerly-input">Ask about your business finances</label>
        <textarea
          ref={textareaRef}
          id="ask-ledgerly-input"
          rows={1}
          dir={direction}
          disabled={!enabled || loading}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              onSubmit();
            }
          }}
          placeholder={enabled ? "Ask about your business finances…" : "Upload business data to start asking questions"}
          aria-describedby="ask-ledgerly-help"
          aria-invalid={Boolean(error)}
        />
        <button
          className="ask-submit"
          type="button"
          onClick={() => onSubmit()}
          disabled={!enabled || loading || !value.trim()}
          aria-label={loading ? "Ledgerly is analyzing your data" : "Ask Ledgerly"}
        >
          {loading ? <span className="ask-spinner" /> : <ArrowUp size={19} />}
        </button>
        <div className="ask-composer-footer" id="ask-ledgerly-help">
          <span>{loading ? "Checking the evidence in your workspace…" : "Enter to send · Shift + Enter for a new line"}</span>
          <span>Answers stay within your data</span>
        </div>
      </div>

      {!response && !loading && !error && (
        <div className="suggested-questions" aria-label="Suggested questions">
          {ASK_LEDGERLY_SUGGESTIONS.map((suggestion) => (
            <button key={suggestion} disabled={!enabled} onClick={() => onSubmit(suggestion)}>
              {suggestion}<ArrowUp size={14} aria-hidden="true" />
            </button>
          ))}
        </div>
      )}

      {loading && (
        <div className="ledgerly-answer answer-loading" role="status" aria-live="polite">
          <span className="answer-pulse" /><div><strong>Ledgerly is checking your data</strong><p>Calculations come from your persisted business records.</p></div>
        </div>
      )}

      {error && !loading && (
        <div className="ledgerly-answer answer-error" role="alert">
          <div><strong>Ledgerly couldn’t complete that answer.</strong><p>{error}</p></div>
          <button onClick={onRetry}><RotateCcw size={14} /> Retry</button>
        </div>
      )}

      {response && !loading && !error && (
        <article className="ledgerly-answer" aria-live="polite" dir={textDirection(askedQuestion)}>
          <div className="answer-label"><span><Sparkles size={14} /> Answer</span>{confidenceLabel && <span>{confidenceLabel}</span>}</div>
          {askedQuestion && <p className="answered-question">{askedQuestion}</p>}
          <AskLedgerlyResponseRenderer response={response} />
          <details className="evidence-details">
            <summary><span>Evidence &amp; calculation details</span><ChevronDown size={15} /></summary>
            <dl>
              <div><dt>Source</dt><dd>Latest authenticated workspace upload</dd></div>
              {confidenceLabel && <div><dt>Confidence</dt><dd>{confidenceLabel}</dd></div>}
              <div><dt>Calculation</dt><dd>Produced by Ledgerly&apos;s deterministic analysis layer from persisted records.</dd></div>
              <div><dt>Reference</dt><dd>{response.correlation_id}</dd></div>
            </dl>
          </details>
        </article>
      )}
    </section>
  );
}
