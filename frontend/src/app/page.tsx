"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Check,
  ChevronDown,
  CloudUpload,
  Download,
  FileSpreadsheet,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Plus,
  Settings,
  Sparkles,
  TrendingUp,
  Upload,
  X,
  Zap,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ApiError,
  askBusiness,
  clearSession,
  downloadLatestReport,
  getCurrentUser,
  getDataInbox,
  getLatestPulse,
  getSettings,
  hasSession,
  listUploads,
  approveMapping,
  reviewCleaningIssue,
  localMarkdownResponse,
  type AskLedgerlyResponse,
  type Pulse,
  type User,
  type DataInboxDetail,
  updateProfile,
  uploadBusinessData,
} from "@/lib/api";
import { AskLedgerly } from "@/components/ask-ledgerly";

const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(["csv", "xlsx", "pdf", "json"]);
const METRIC_COLORS = ["#7357ff", "#a99aff", "#d4cbff", "#eeebff"];
type ChatMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: AskLedgerlyResponse };

const nav = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "Analytics", icon: BarChart3 },
  { label: "Ask Ledgerly", icon: MessageSquareText },
  { label: "Data sources", icon: FileSpreadsheet },
];

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

function metricLabel(name: string) {
  return name.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatMetric(name: string, value: number) {
  if (name.includes("margin") || name.includes("rate")) return `${value.toFixed(1)}%`;
  if (["revenue", "expenses", "profit", "cash", "income", "sales"].includes(name)) {
    return formatMoney(value);
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 }).format(value);
}

export default function Dashboard() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [fileName, setFileName] = useState("");
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const [inboxDetail, setInboxDetail] = useState<DataInboxDetail | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [profileName, setProfileName] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [settingsError, setSettingsError] = useState("");
  const [uploadCount, setUploadCount] = useState(0);
  const [livePulse, setLivePulse] = useState<Pulse | null>(null);
  const [businessDataLoaded, setBusinessDataLoaded] = useState(false);
  const [pageError, setPageError] = useState("");
  const [feedback, setFeedback] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [uploading, setUploading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState("");
  const [lastQuestion, setLastQuestion] = useState("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: "assistant",
      content: localMarkdownResponse("Ask me about the metrics and trends in your latest business upload."),
    },
  ]);
  const fileInput = useRef<HTMLInputElement>(null);
  const metrics = useMemo(() => livePulse?.metrics ?? {}, [livePulse]);
  const metricCards = useMemo(() => {
    const preferred = ["revenue", "profit", "expenses", "net_margin"];
    const names = [
      ...preferred.filter((name) => Number.isFinite(metrics[name])),
      ...Object.keys(metrics).filter(
        (name) => !preferred.includes(name) && Number.isFinite(metrics[name]),
      ),
    ].slice(0, 4);
    return names.map((name) => {
      const change = livePulse?.comparison?.changes[name];
      return {
        name,
        value: metrics[name],
        change,
        spark: change ? [change.previous, change.current] : [metrics[name]],
      };
    });
  }, [livePulse, metrics]);
  const trendData = useMemo(() => {
    const revenueChange = livePulse?.comparison?.changes.revenue;
    const expenseChange = livePulse?.comparison?.changes.expenses;
    const current = {
      period: "Current",
      revenue: metrics.revenue,
      expenses: metrics.expenses,
    };
    if (!revenueChange && !expenseChange) return [current];
    return [
      {
        period: "Previous",
        revenue: revenueChange?.previous,
        expenses: expenseChange?.previous,
      },
      current,
    ];
  }, [livePulse, metrics]);
  const metricMix = useMemo(
    () =>
      Object.entries(metrics)
        .filter(
          ([name, value]) =>
            name !== "net_margin" && Number.isFinite(value) && value > 0,
        )
        .slice(0, 4)
        .map(([name, value], index) => ({
          name: metricLabel(name),
          value,
          color: METRIC_COLORS[index],
        })),
    [metrics],
  );
  const insights = useMemo(() => {
    const changes = Object.entries(livePulse?.comparison?.changes ?? {});
    if (changes.length > 0) {
      return changes.slice(0, 3).map(([name, change]) => ({
        title: `${metricLabel(name)} ${
          change.percent_change >= 0 ? "increased" : "decreased"
        }`,
        text: `${formatMetric(name, change.current)} versus ${formatMetric(
          name,
          change.previous,
        )} previously (${Math.abs(change.percent_change)}%).`,
        direction: change.percent_change >= 0 ? ("up" as const) : ("down" as const),
      }));
    }
    return (livePulse?.factors ?? []).slice(0, 3).map((factor) => ({
      title: String(factor.name ?? "Pulse factor"),
      text: String(factor.explanation ?? "Derived from the latest upload."),
      direction: "up" as const,
    }));
  }, [livePulse]);

  useEffect(() => {
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    void Promise.allSettled([
      getCurrentUser(),
      listUploads(),
      getLatestPulse(),
    ]).then(([userResult, uploadsResult, pulseResult]) => {
      if (userResult.status === "fulfilled") setCurrentUser(userResult.value);
      if (uploadsResult.status === "fulfilled") {
        setUploadCount(uploadsResult.value.length);
        if (uploadsResult.value.length === 0) {
          setMessages([{
            role: "assistant",
            content: localMarkdownResponse("Upload your first business file, then ask me to explain its revenue, expenses, margins, or trends."),
          }]);
        }
      }
      if (pulseResult.status === "fulfilled") {
        setLivePulse(pulseResult.value);
      } else if (
        !(pulseResult.reason instanceof ApiError && pulseResult.reason.status === 404)
      ) {
        setPageError(
          pulseResult.reason instanceof Error
            ? pulseResult.reason.message
            : "Unable to load your latest Business Pulse.",
        );
      }
      if (userResult.status === "rejected" || uploadsResult.status === "rejected") {
        const reason =
          userResult.status === "rejected"
            ? userResult.reason
            : uploadsResult.status === "rejected"
              ? uploadsResult.reason
              : null;
        setPageError(
          reason instanceof Error
            ? reason.message
            : "Unable to load your business workspace.",
        );
      }
      setBusinessDataLoaded(true);
    });
  }, []);

  const authenticatedEmpty = businessDataLoaded && uploadCount === 0;

  async function openSettings() {
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    setPageError("");
    setSettingsError("");
    try {
      const settings = await getSettings();
      setProfileName(settings.profile.full_name);
      setProfileEmail(settings.profile.email);
      setSettingsOpen(true);
    } catch (error) {
      setPageError(
        error instanceof Error ? error.message : "Unable to load settings.",
      );
    }
  }

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingProfile(true);
    setSettingsError("");
    try {
      const user = await updateProfile({
        full_name: profileName,
        email: profileEmail,
      });
      setCurrentUser(user);
      setSettingsOpen(false);
    } catch (error) {
      setSettingsError(
        error instanceof Error ? error.message : "Unable to update your profile.",
      );
    } finally {
      setSavingProfile(false);
    }
  }

  function logout() {
    clearSession();
    window.location.href = "/login";
  }

  async function submitQuestion(prompt = question) {
    const clean = prompt.trim();
    if (!clean) return;
    setMessages((current) => [...current, { role: "user", content: clean }]);
    setLastQuestion(clean);
    setChatError("");
    setQuestion("");
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    setChatLoading(true);
    try {
      const response = await askBusiness(clean);
      setMessages((current) => [
        ...current,
        { role: "assistant", content: response },
      ]);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      setChatError(error instanceof Error ? error.message : "Ledgerly couldn’t reach your business data.");
    } finally {
      setChatLoading(false);
    }
  }

  async function exportReport() {
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    setExporting(true);
    setPageError("");
    try {
      await downloadLatestReport();
      setFeedback("Your PDF report was downloaded.");
    } catch (error) {
      setPageError(
        error instanceof Error ? error.message : "Unable to export the report.",
      );
    } finally {
      setExporting(false);
    }
  }

  function selectFiles(files: File[]) {
    setUploadError("");
    setFeedback("");
    if (!files.length) {
      setSelectedFiles([]);
      setFileName("");
      return;
    }
    if (files.some((file) => !ALLOWED_EXTENSIONS.has(file.name.split(".").pop()?.toLowerCase() ?? ""))) {
      setUploadError("Choose a CSV, XLSX, PDF, or JSON file.");
      setSelectedFiles([]);
      setFileName("");
      return;
    }
    if (files.some((file) => file.size > MAX_UPLOAD_BYTES)) {
      setUploadError("The file exceeds the 20 MB upload limit.");
      setSelectedFiles([]);
      setFileName("");
      return;
    }
    setSelectedFiles(files);
    setFileName(files.length === 1 ? files[0].name : `${files.length} files selected`);
  }

  async function analyzeFile() {
    if (!selectedFiles.length) return;
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    setUploading(true);
    setUploadError("");
    setPageError("");
    try {
      let pulse: Pulse | null = null;
      for (const file of selectedFiles) pulse = await uploadBusinessData(file);
      if (pulse) setLivePulse(pulse);
      setUploadCount((count) => count + selectedFiles.length);
      const uploads = await listUploads();
      if (uploads[0]) setInboxDetail(await getDataInbox(uploads[0].id));
      setFeedback(`${selectedFiles.length} file${selectedFiles.length === 1 ? " was" : "s were"} analyzed. Review mappings and cleaning suggestions below.`);
      setUploadOpen(false);
      setSelectedFiles([]);
      setFileName("");
      if (fileInput.current) fileInput.current.value = "";
    } catch (error) {
      setUploadError(
        error instanceof Error ? error.message : "Unable to analyze this file.",
      );
    } finally {
      setUploading(false);
    }
  }

  async function approveCurrentMapping() {
    if (!inboxDetail) return;
    await approveMapping(inboxDetail.upload.id, inboxDetail.profile);
    setInboxDetail(await getDataInbox(inboxDetail.upload.id));
    setFeedback("Column mapping approved and saved for this source.");
  }

  async function decideIssue(issueId: number, status: "approved" | "rejected", suggested: unknown) {
    if (!inboxDetail) return;
    await reviewCleaningIssue(inboxDetail.upload.id, issueId, status, suggested);
    setInboxDetail(await getDataInbox(inboxDetail.upload.id));
  }

  const firstName = currentUser?.full_name.split(" ")[0] ?? "";
  const workspaceName = firstName ? `${firstName}'s workspace` : "Business workspace";
  const initials = currentUser?.full_name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "L";
  const confidenceLabel =
    (livePulse?.confidence ?? 0) >= 0.8
      ? "High confidence"
      : (livePulse?.confidence ?? 0) >= 0.6
        ? "Medium confidence"
        : "Low confidence";

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNavOpen ? "sidebar-open" : ""}`}>
        <div className="brand-row">
          <div className="brand-mark"><TrendingUp size={18} strokeWidth={2.7} /></div>
          <span>Ledgerly</span>
          <button className="mobile-close" onClick={() => setMobileNavOpen(false)} aria-label="Close navigation">
            <X size={18} />
          </button>
        </div>

        <div className="workspace-switch">
          <span className="workspace-avatar">{initials}</span>
          <span><strong>{workspaceName}</strong><small>Business workspace</small></span>
        </div>

        <nav className="main-nav">
          <span className="nav-caption">Workspace</span>
          {nav.map(({ label, icon: Icon }, index) => (
            <button
              key={label}
              className={index === 0 ? "nav-item active" : "nav-item"}
              onClick={() => {
                setMobileNavOpen(false);
                if (index === 0) window.scrollTo({ top: 0, behavior: "smooth" });
                if (index === 1) document.getElementById("analytics")?.scrollIntoView({ behavior: "smooth" });
                if (index === 2) document.getElementById("ask-ledgerly")?.scrollIntoView({ behavior: "smooth", block: "center" });
                if (index === 3) setUploadOpen(true);
              }}
            >
              <Icon size={18} /><span>{label}</span>{label === "Ask Ledgerly" && <span className="ai-pill">AI</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="pulse-mini">
            <div className="pulse-mini-top"><Zap size={15} fill="currentColor" /><span>Business Pulse™</span><strong>{livePulse?.score ?? "—"}</strong></div>
            <div className="progress-track"><span style={{ width: `${livePulse?.score ?? 0}%` }} /></div>
            <small>{livePulse ? `${confidenceLabel} · Latest upload` : "Waiting for your first upload"}</small>
          </div>
          <button className="nav-item" onClick={openSettings}><Settings size={18} /><span>Settings</span></button>
          <div className="profile-row" role="button" tabIndex={0} onClick={openSettings} onKeyDown={(event) => event.key === "Enter" && openSettings()}>
            <div className="profile-avatar">{initials}</div>
            <span><strong>{currentUser?.full_name ?? "Loading profile"}</strong><small>{currentUser?.email ?? ""}</small></span>
            <ChevronDown size={14} />
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button className="menu-button" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <div className="top-actions">
            <button className="secondary-button" disabled={!livePulse || exporting} onClick={exportReport}><Download size={16} />{exporting ? "Preparing..." : "Export report"}</button>
            <button className="primary-button" onClick={() => setUploadOpen(true)}><Plus size={17} />Add data</button>
          </div>
        </header>

        <div className="page">
          <section className="page-heading">
            <div>
              <p className="eyebrow"><span /> LIVE BUSINESS VIEW</p>
              <h1>{firstName ? `Good morning, ${firstName}.` : "Your business overview"}</h1>
              <p>Here&apos;s what your business is telling us today.</p>
            </div>
          </section>

          {pageError && <div className="status-banner status-error" role="alert">{pageError}</div>}
          {feedback && <div className="status-banner status-success" role="status">{feedback}</div>}

          {inboxDetail && (
            <section className="panel inbox-review" aria-labelledby="inbox-heading">
              <div className="panel-heading"><div><p className="eyebrow">DATA INBOX</p><h3 id="inbox-heading">Review {inboxDetail.upload.filename}</h3><p>Source values remain unchanged until you approve each suggestion.</p></div><span className="review-count">{inboxDetail.summary.pending} pending</span></div>
              <div className="inbox-profile"><span><small>Role</small><strong>{metricLabel(inboxDetail.profile.role)}</strong></span><span><small>Period</small><strong>{inboxDetail.profile.period ?? "Not detected"}</strong></span><span><small>Currency</small><strong>{inboxDetail.profile.currency ?? "Not detected"}</strong></span><button className="secondary-button" onClick={approveCurrentMapping}>{inboxDetail.profile.mapping_approved ? "Mapping saved" : "Approve mapping"}</button></div>
              <div className="mapping-chips">{Object.entries(inboxDetail.profile.column_mapping).map(([target, source]) => <span key={target}>{source} → {target}</span>)}</div>
              <div className="issue-list">{inboxDetail.issues.slice(0, 12).map((issue) => <div className="issue-row" key={issue.id}><div><strong>{metricLabel(issue.issue_type)}</strong><p>Row {issue.row_number ?? "—"}{issue.column_name ? ` · ${issue.column_name}` : ""} — {issue.explanation}</p></div><span className={`issue-status ${issue.severity}`}>{issue.status}</span>{issue.status === "pending" && <div className="issue-actions"><button onClick={() => decideIssue(issue.id, "rejected", issue.original_value)}>Keep original</button>{issue.suggested_value !== null && <button onClick={() => decideIssue(issue.id, "approved", issue.suggested_value)}>Approve suggestion</button>}</div>}</div>)}</div>
            </section>
          )}

          {!businessDataLoaded ? (
            <section className="pulse-card loading-card" aria-live="polite">
              <div className="loading-spinner" />
              <div><h2>Loading your business data</h2><p>Reading your latest persisted results.</p></div>
            </section>
          ) : authenticatedEmpty ? (
            <>
            <section className="pulse-card">
              <div className="pulse-score">
                <div className="memory-icon"><CloudUpload size={22} /></div>
                <div><p>BUSINESS PULSE™</p><h2>Upload your first business file</h2></div>
              </div>
              <div className="pulse-copy">
                <Sparkles size={18} />
                <p>Ledgerly will detect your metrics, build an explainable Business Pulse, and remember each upload.</p>
              </div>
              <button onClick={() => setUploadOpen(true)}>Add data <ArrowUpRight size={15} /></button>
            </section>
            <AskLedgerly
              value={question}
              onChange={setQuestion}
              onSubmit={submitQuestion}
              onRetry={() => submitQuestion(lastQuestion)}
              response={null}
              askedQuestion=""
              loading={false}
              enabled={false}
              error=""
            />
            </>
          ) : livePulse ? (
          <>
          <section className="pulse-card">
            <div className="pulse-score">
              <div className="score-ring" style={{ background: `radial-gradient(circle at center, white 57%, transparent 59%), conic-gradient(#7153ef 0 ${livePulse.score}%, #e8e3fb ${livePulse.score}%)` }}><span>{livePulse.score}</span><small>/100</small></div>
              <div><p>Business Pulse™</p><h2>Latest uploaded data</h2><span className="confidence"><Check size={13} />{confidenceLabel}</span></div>
            </div>
            <div className="pulse-copy">
              <Sparkles size={18} />
              <p>{livePulse.summary}</p>
            </div>
            <button onClick={() => document.getElementById("ask-ledgerly")?.scrollIntoView({ behavior: "smooth", block: "center" })}>Ask about this <ArrowUpRight size={15} /></button>
          </section>

          <section className="kpi-grid">
            {metricCards.map(({ name, value, change, spark }) => (
              <Metric
                key={name}
                label={metricLabel(name)}
                value={formatMetric(name, value)}
                delta={change ? `${Math.abs(change.percent_change)}%` : "Current"}
                direction={(change?.percent_change ?? 0) >= 0 ? "up" : "down"}
                note={change ? "vs previous upload" : "latest upload"}
                spark={spark}
                neutral={name === "expenses"}
              />
            ))}
          </section>

          <AskLedgerly
            value={question}
            onChange={setQuestion}
            onSubmit={submitQuestion}
            onRetry={() => submitQuestion(lastQuestion)}
            response={messages.length > 1 && messages.at(-1)?.role === "assistant" ? messages.at(-1)?.content as AskLedgerlyResponse : null}
            askedQuestion={lastQuestion}
            loading={chatLoading}
            enabled={Boolean(livePulse)}
            error={chatError}
            confidenceLabel={confidenceLabel}
          />

          <section className="chart-grid" id="analytics">
            <article className="panel revenue-panel">
              <div className="panel-heading">
                <div><h3>Revenue & expenses</h3><p>Latest persisted upload{trendData.length > 1 ? " compared with the previous upload" : ""}</p></div>
                <div className="legend"><span><i className="purple" />Revenue</span><span><i className="lilac" />Expenses</span></div>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trendData} margin={{ top: 18, right: 8, left: -18, bottom: 0 }}>
                    <defs>
                      <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7357ff" stopOpacity={0.24} /><stop offset="100%" stopColor="#7357ff" stopOpacity={0} /></linearGradient>
                      <linearGradient id="expenseFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c9beff" stopOpacity={0.2} /><stop offset="100%" stopColor="#c9beff" stopOpacity={0} /></linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="#edeaf4" />
                    <XAxis dataKey="period" axisLine={false} tickLine={false} tick={{ fill: "#8a8497", fontSize: 11 }} dy={10} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: "#8a8497", fontSize: 11 }} tickFormatter={(v) => `$${v / 1000}k`} />
                    <Tooltip formatter={(value) => formatMoney(Number(value))} contentStyle={{ border: "1px solid #e8e4f0", borderRadius: 12, boxShadow: "0 10px 30px rgba(40,30,80,.1)" }} />
                    <Area type="monotone" dataKey="revenue" stroke="#7357ff" strokeWidth={2.5} fill="url(#revenueFill)" />
                    <Area type="monotone" dataKey="expenses" stroke="#b8a9ff" strokeWidth={2} fill="url(#expenseFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="panel expense-panel">
              <div className="panel-heading"><div><h3>Detected metrics</h3><p>Relative size in the latest upload</p></div></div>
              <div className="expense-body">
                <div className="donut-wrap">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart><Pie data={metricMix} dataKey="value" innerRadius={48} outerRadius={66} paddingAngle={3} stroke="none">{metricMix.map((entry) => <Cell key={entry.name} fill={entry.color} />)}</Pie></PieChart>
                  </ResponsiveContainer>
                  <div className="donut-label"><strong>{metricMix.length}</strong><span>Metrics</span></div>
                </div>
                <div className="expense-list">
                  {metricMix.map((entry) => <div key={entry.name}><span><i style={{ background: entry.color }} />{entry.name}</span><strong>{new Intl.NumberFormat("en-US", { notation: "compact" }).format(entry.value)}</strong></div>)}
                </div>
              </div>
            </article>
          </section>

          <section className="bottom-grid">
            <article className="panel insight-panel">
              <div className="panel-heading"><div><h3>{livePulse.comparison ? "What changed" : "Pulse factors"}</h3><p>{livePulse.comparison ? "Compared with your previous upload" : "Derived from your latest upload"}</p></div><span className="new-badge">{insights.length} insights</span></div>
              {insights.map((insight, index) => (
                <Insight
                  key={`${insight.title}-${index}`}
                  icon={insight.direction === "down" ? <ArrowDownRight /> : <ArrowUpRight />}
                  tone={insight.direction === "down" ? "purple" : index === 0 ? "green" : "amber"}
                  title={insight.title}
                  text={insight.text}
                />
              ))}
            </article>
            <article className="panel memory-panel">
              <div className="memory-icon"><Zap size={22} /></div>
              <span className="memory-kicker">BUSINESS MEMORY</span>
              <h3>Ledgerly remembers your story.</h3>
              <p>Ledgerly has persisted {uploadCount} {uploadCount === 1 ? "upload" : "uploads"} for this account and compares matching metrics over time.</p>
              <div className="memory-stats"><div><strong>{uploadCount}</strong><span>Uploads</span></div><div><strong>{Object.keys(metrics).length}</strong><span>Metrics</span></div><div><strong>{Math.round(livePulse.confidence * 100)}%</strong><span>Confidence</span></div></div>
              <button onClick={() => setUploadOpen(true)}><Upload size={15} />Upload new data</button>
            </article>
          </section>
          </>
          ) : (
            <section className="pulse-card">
              <div className="pulse-score">
                <div className="memory-icon"><CloudUpload size={22} /></div>
                <div><p>BUSINESS PULSE™</p><h2>Your latest Pulse could not be loaded</h2></div>
              </div>
              <div className="pulse-copy">
                <Sparkles size={18} />
                <p>Refresh the page or upload the file again after the service is available.</p>
              </div>
            </section>
          )}
        </div>
      </main>

      {uploadOpen && (
        <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setUploadOpen(false)}>
          <div className="upload-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
            <button className="modal-close" onClick={() => setUploadOpen(false)}><X size={18} /></button>
            <div className="modal-icon"><CloudUpload size={24} /></div>
            <h2 id="upload-title">Connect your business data</h2>
            <p>Upload a statement or export. Ledgerly will identify your business metrics automatically.</p>
            <input ref={fileInput} hidden multiple type="file" accept=".csv,.xlsx,.pdf,.json" onChange={(e) => selectFiles(Array.from(e.target.files ?? []))} />
            <button className="dropzone" onClick={() => fileInput.current?.click()}>
              <Upload size={24} />
              <strong>{fileName || "Choose a file to upload"}</strong>
              <span>Multiple CSV, XLSX, PDF, or JSON files · Up to 20 MB each</span>
            </button>
            {uploadError && <p className="form-error" role="alert">{uploadError}</p>}
            <div className="privacy-note"><Check size={14} /><span>Your data is encrypted and used only to explain your business.</span></div>
            <button className="modal-primary" disabled={!fileName || uploading} onClick={analyzeFile}>{uploading ? "Analyzing..." : fileName ? "Analyze this file" : "Choose a file"}</button>
          </div>
        </div>
      )}

      {settingsOpen && (
        <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setSettingsOpen(false)}>
          <div className="upload-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <button className="modal-close" onClick={() => setSettingsOpen(false)} aria-label="Close settings"><X size={18} /></button>
            <form className="login-card" onSubmit={saveProfile}>
              <h2 id="settings-title">Profile settings</h2>
              <p>Keep your Ledgerly account details current.</p>
              <label>Full name<div className="password-input"><input type="text" required minLength={2} value={profileName} onChange={(event) => setProfileName(event.target.value)} /></div></label>
              <label>Email address<input type="email" required value={profileEmail} onChange={(event) => setProfileEmail(event.target.value)} /></label>
              {settingsError && <p className="form-error" role="alert">{settingsError}</p>}
              <button className="sign-in-button" disabled={savingProfile}>{savingProfile ? "Saving..." : "Save profile"}</button>
              <button type="button" className="secondary-form-button" onClick={logout}>Log out</button>
            </form>
          </div>
        </div>
      )}

    </div>
  );
}

function Metric({ label, value, delta, direction, note, spark, neutral = false }: { label: string; value: string; delta: string; direction: "up" | "down"; note: string; spark: number[]; neutral?: boolean }) {
  const minimum = Math.min(...spark);
  const maximum = Math.max(...spark);
  const range = maximum - minimum || 1;
  const points = spark.length > 1
    ? spark.map((item, index) => `${index * 80 / (spark.length - 1) + 5},${30 - ((item - minimum) / range) * 22}`).join(" ")
    : "5,19 85,19";
  return <article className="metric-card"><div className="metric-top"><span>{label}</span></div><div className="metric-main"><strong>{value}</strong><svg viewBox="0 0 90 36" aria-hidden="true"><polyline points={points} fill="none" stroke={neutral ? "#a99aff" : "#6d50f5"} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg></div><div className="metric-foot"><span className={neutral ? "delta neutral" : "delta"}>{direction === "up" ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{delta}</span><small>{note}</small></div></article>;
}

function Insight({ icon, tone, title, text }: { icon: React.ReactNode; tone: string; title: string; text: string }) {
  return <div className="insight-row"><div className={`insight-icon ${tone}`}>{icon}</div><div><strong>{title}</strong><p>{text}</p></div></div>;
}
