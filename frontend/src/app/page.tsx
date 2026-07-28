"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bot,
  Check,
  ChevronDown,
  CircleHelp,
  CloudUpload,
  Download,
  FileSpreadsheet,
  LayoutDashboard,
  Menu,
  MessageSquareText,
  Plus,
  Search,
  Send,
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
  getLatestPulse,
  getSettings,
  hasSession,
  listUploads,
  type Pulse,
  type User,
  updateProfile,
  uploadBusinessData,
} from "@/lib/api";

const revenue = [
  { month: "Jan", revenue: 38200, expenses: 24100 },
  { month: "Feb", revenue: 42800, expenses: 25300 },
  { month: "Mar", revenue: 40100, expenses: 24900 },
  { month: "Apr", revenue: 48600, expenses: 27100 },
  { month: "May", revenue: 51200, expenses: 28400 },
  { month: "Jun", revenue: 55842, expenses: 29510 },
];

const expenseMix = [
  { name: "Operations", value: 38, color: "#7357ff" },
  { name: "Payroll", value: 29, color: "#a99aff" },
  { name: "Marketing", value: 18, color: "#d4cbff" },
  { name: "Other", value: 15, color: "#eeebff" },
];

const nav = [
  { label: "Overview", icon: LayoutDashboard },
  { label: "Analytics", icon: BarChart3 },
  { label: "Ask Ledgerly", icon: MessageSquareText },
  { label: "Data sources", icon: FileSpreadsheet },
];

const quickQuestions = [
  "What changed this month?",
  "Where are costs increasing?",
  "Summarize cash flow",
];

function formatMoney(value: number) {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  }).format(value);
}

export default function Dashboard() {
  const [uploadOpen, setUploadOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [period, setPeriod] = useState("Last 6 months");
  const [fileName, setFileName] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [profileName, setProfileName] = useState("");
  const [profileEmail, setProfileEmail] = useState("");
  const [savingProfile, setSavingProfile] = useState(false);
  const [uploadCount, setUploadCount] = useState(6);
  const [livePulse, setLivePulse] = useState<Pulse | null>(null);
  const [authenticatedSession, setAuthenticatedSession] = useState(false);
  const [businessDataLoaded, setBusinessDataLoaded] = useState(false);
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState([
    {
      role: "assistant",
      text: "Hi Maya — I understand your latest business data. Ask me about revenue, expenses, margins, or changes since your previous upload.",
    },
  ]);
  const fileInput = useRef<HTMLInputElement>(null);
  const margin = useMemo(
    () => Math.round(livePulse?.metrics.net_margin ?? ((55842 - 29510) / 55842) * 100),
    [livePulse],
  );

  useEffect(() => {
    if (!hasSession()) {
      setBusinessDataLoaded(true);
      return;
    }
    setAuthenticatedSession(true);
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
            text: "Upload your first business file, then ask me to explain its revenue, expenses, margins, or trends.",
          }]);
        }
      }
      if (pulseResult.status === "fulfilled") setLivePulse(pulseResult.value);
      setBusinessDataLoaded(true);
    });
  }, []);

  const authenticatedEmpty = authenticatedSession && businessDataLoaded && uploadCount === 0;

  async function openSettings() {
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    try {
      const settings = await getSettings();
      setProfileName(settings.profile.full_name);
      setProfileEmail(settings.profile.email);
      setSettingsOpen(true);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to load settings.");
    }
  }

  async function saveProfile(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSavingProfile(true);
    try {
      const user = await updateProfile({
        full_name: profileName,
        email: profileEmail,
      });
      setCurrentUser(user);
      setSettingsOpen(false);
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to update your profile.");
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
    setMessages((current) => [...current, { role: "user", text: clean }]);
    setQuestion("");
    if (!hasSession()) {
      setMessages((current) => [...current, {
        role: "assistant",
        text: "Revenue rose 9.3% versus your previous upload, led by stronger May and June sales. Operating costs grew more slowly at 3.8%, so your net margin improved by 2.1 percentage points. This is an explanation of your uploaded data, not financial advice.",
      }]);
      return;
    }
    try {
      const response = await askBusiness(clean);
      setMessages((current) => [...current, { role: "assistant", text: response.answer }]);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      setMessages((current) => [...current, {
        role: "assistant",
        text: error instanceof Error ? error.message : "I couldn’t reach your business data.",
      }]);
    }
  }

  async function exportReport() {
    if (!hasSession()) {
      window.print();
      return;
    }
    try {
      await downloadLatestReport();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to export the report.");
    }
  }

  async function analyzeFile() {
    if (!selectedFile) return;
    if (!hasSession()) {
      window.location.href = "/login";
      return;
    }
    try {
      const pulse = await uploadBusinessData(selectedFile);
      setLivePulse(pulse);
      setUploadCount((count) => count + 1);
      setUploadOpen(false);
      setSelectedFile(null);
      setFileName("");
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "Unable to analyze this file.");
    }
  }

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

        <button className="workspace-switch">
          <span className="workspace-avatar">N</span>
          <span><strong>Northstar Studio</strong><small>Business workspace</small></span>
          <ChevronDown size={14} />
        </button>

        <nav className="main-nav">
          <span className="nav-caption">Workspace</span>
          {nav.map(({ label, icon: Icon }, index) => (
            <button key={label} className={index === 0 ? "nav-item active" : "nav-item"} onClick={() => index === 2 && setChatOpen(true)}>
              <Icon size={18} /><span>{label}</span>{label === "Ask Ledgerly" && <span className="ai-pill">AI</span>}
            </button>
          ))}
        </nav>

        <div className="sidebar-bottom">
          <div className="pulse-mini">
            <div className="pulse-mini-top"><Zap size={15} fill="currentColor" /><span>Business Pulse™</span><strong>{authenticatedEmpty ? "—" : (livePulse?.score ?? 86)}</strong></div>
            <div className="progress-track"><span style={{ width: authenticatedEmpty ? "0%" : `${livePulse?.score ?? 86}%` }} /></div>
            <small>{authenticatedEmpty ? "Waiting for your first upload" : "Strong · Updated today"}</small>
          </div>
          <button className="nav-item"><CircleHelp size={18} /><span>Help & support</span></button>
          <button className="nav-item" onClick={openSettings}><Settings size={18} /><span>Settings</span></button>
          <div className="profile-row" role="button" tabIndex={0} onClick={openSettings} onKeyDown={(event) => event.key === "Enter" && openSettings()}>
            <div className="profile-avatar">MP</div>
            <span><strong>{currentUser?.full_name ?? "Maya Patel"}</strong><small>{currentUser?.email ?? "maya@northstar.co"}</small></span>
            <ChevronDown size={14} />
          </div>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <button className="menu-button" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation"><Menu size={20} /></button>
          <div className="search-box"><Search size={17} /><input aria-label="Search" placeholder="Search your business..." /><kbd>⌘ K</kbd></div>
          <div className="top-actions">
            <button className="icon-button" aria-label="Notifications"><Bell size={18} /><i /></button>
            <button className="secondary-button" onClick={exportReport}><Download size={16} />Export report</button>
            <button className="primary-button" onClick={() => setUploadOpen(true)}><Plus size={17} />Add data</button>
          </div>
        </header>

        <div className="page">
          <section className="page-heading">
            <div>
              <p className="eyebrow"><span /> LIVE BUSINESS VIEW</p>
              <h1>Good morning, {currentUser?.full_name.split(" ")[0] ?? "Maya"}.</h1>
              <p>Here&apos;s what your business is telling us today.</p>
            </div>
            <div className="period-control">
              <button onClick={() => setPeriod(period === "Last 6 months" ? "This year" : "Last 6 months")}>
                {period}<ChevronDown size={14} />
              </button>
              <span>Compared with previous period</span>
            </div>
          </section>

          {authenticatedEmpty ? (
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
          ) : (
          <>
          <section className="pulse-card">
            <div className="pulse-score">
              <div className="score-ring"><span>{livePulse?.score ?? 86}</span><small>/100</small></div>
              <div><p>Business Pulse™</p><h2>Your business looks strong</h2><span className="confidence"><Check size={13} />High confidence</span></div>
            </div>
            <div className="pulse-copy">
              <Sparkles size={18} />
              <p>Revenue is growing faster than expenses, and your cash position is healthy. Profitability improved for the third consecutive month.</p>
            </div>
            <button onClick={() => setChatOpen(true)}>See full explanation <ArrowUpRight size={15} /></button>
          </section>

          <section className="kpi-grid">
            <Metric label="Revenue" value="$55,842" delta="9.3%" direction="up" note="vs previous period" spark={[35, 45, 39, 56, 65, 79]} />
            <Metric label="Net profit" value="$16,420" delta="14.8%" direction="up" note="vs previous period" spark={[25, 32, 31, 46, 54, 72]} />
            <Metric label="Total expenses" value="$29,510" delta="3.8%" direction="up" note="vs previous period" spark={[35, 40, 38, 43, 45, 49]} neutral />
            <Metric label="Net margin" value={`${margin}%`} delta="2.1 pts" direction="up" note="vs previous period" spark={[30, 28, 41, 48, 54, 67]} />
          </section>

          <section className="chart-grid">
            <article className="panel revenue-panel">
              <div className="panel-heading">
                <div><h3>Revenue & expenses</h3><p>Your income is outpacing costs</p></div>
                <div className="legend"><span><i className="purple" />Revenue</span><span><i className="lilac" />Expenses</span></div>
              </div>
              <div className="chart-wrap">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={revenue} margin={{ top: 18, right: 8, left: -18, bottom: 0 }}>
                    <defs>
                      <linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#7357ff" stopOpacity={0.24} /><stop offset="100%" stopColor="#7357ff" stopOpacity={0} /></linearGradient>
                      <linearGradient id="expenseFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#c9beff" stopOpacity={0.2} /><stop offset="100%" stopColor="#c9beff" stopOpacity={0} /></linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="#edeaf4" />
                    <XAxis dataKey="month" axisLine={false} tickLine={false} tick={{ fill: "#8a8497", fontSize: 11 }} dy={10} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: "#8a8497", fontSize: 11 }} tickFormatter={(v) => `$${v / 1000}k`} />
                    <Tooltip formatter={(value) => formatMoney(Number(value))} contentStyle={{ border: "1px solid #e8e4f0", borderRadius: 12, boxShadow: "0 10px 30px rgba(40,30,80,.1)" }} />
                    <Area type="monotone" dataKey="revenue" stroke="#7357ff" strokeWidth={2.5} fill="url(#revenueFill)" />
                    <Area type="monotone" dataKey="expenses" stroke="#b8a9ff" strokeWidth={2} fill="url(#expenseFill)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </article>

            <article className="panel expense-panel">
              <div className="panel-heading"><div><h3>Expense breakdown</h3><p>Where your money went</p></div><button className="more-button">•••</button></div>
              <div className="expense-body">
                <div className="donut-wrap">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart><Pie data={expenseMix} dataKey="value" innerRadius={48} outerRadius={66} paddingAngle={3} stroke="none">{expenseMix.map((entry) => <Cell key={entry.name} fill={entry.color} />)}</Pie></PieChart>
                  </ResponsiveContainer>
                  <div className="donut-label"><strong>$29.5k</strong><span>Total</span></div>
                </div>
                <div className="expense-list">
                  {expenseMix.map((entry) => <div key={entry.name}><span><i style={{ background: entry.color }} />{entry.name}</span><strong>{entry.value}%</strong></div>)}
                </div>
              </div>
            </article>
          </section>

          <section className="bottom-grid">
            <article className="panel insight-panel">
              <div className="panel-heading"><div><h3>What changed</h3><p>Compared to your previous upload</p></div><span className="new-badge">3 insights</span></div>
              <Insight icon={<ArrowUpRight />} tone="green" title="Revenue accelerated" text="June revenue was your strongest this year, up 9.3% from May." />
              <Insight icon={<ArrowDownRight />} tone="purple" title="Marketing became more efficient" text="Spend fell 4.2% while revenue continued to grow." />
              <Insight icon={<TrendingUp />} tone="amber" title="Subscriptions are trending up" text="Recurring tools increased $620 over the last two uploads." />
            </article>
            <article className="panel memory-panel">
              <div className="memory-icon"><Zap size={22} /></div>
              <span className="memory-kicker">BUSINESS MEMORY</span>
              <h3>Ledgerly remembers your story.</h3>
              <p>This is your {uploadCount}th upload. We compare every new file with your history so context is never lost.</p>
              <div className="memory-stats"><div><strong>{uploadCount}</strong><span>Uploads</span></div><div><strong>18 mo</strong><span>History</span></div><div><strong>94%</strong><span>Data match</span></div></div>
              <button onClick={() => setUploadOpen(true)}><Upload size={15} />Upload new data</button>
            </article>
          </section>
          </>
          )}
        </div>
      </main>

      <button className="chat-fab" onClick={() => setChatOpen(true)}><Sparkles size={17} />Ask Ledgerly</button>

      {uploadOpen && (
        <div className="modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && setUploadOpen(false)}>
          <div className="upload-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
            <button className="modal-close" onClick={() => setUploadOpen(false)}><X size={18} /></button>
            <div className="modal-icon"><CloudUpload size={24} /></div>
            <h2 id="upload-title">Connect your business data</h2>
            <p>Upload a statement or export. Ledgerly will identify your business metrics automatically.</p>
            <input ref={fileInput} hidden type="file" accept=".csv,.xlsx,.pdf,.json" onChange={(e) => { const file = e.target.files?.[0] ?? null; setSelectedFile(file); setFileName(file?.name ?? ""); }} />
            <button className="dropzone" onClick={() => fileInput.current?.click()}>
              <Upload size={24} />
              <strong>{fileName || "Drop your file here, or browse"}</strong>
              <span>CSV, XLSX, PDF, or JSON · Up to 20 MB</span>
            </button>
            <div className="privacy-note"><Check size={14} /><span>Your data is encrypted and used only to explain your business.</span></div>
            <button className="modal-primary" disabled={!fileName} onClick={analyzeFile}>{fileName ? "Analyze this file" : "Choose a file"}</button>
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
              <button className="sign-in-button" disabled={savingProfile}>{savingProfile ? "Saving..." : "Save profile"}</button>
              <button type="button" className="demo-button" onClick={logout}>Log out</button>
            </form>
          </div>
        </div>
      )}

      <aside className={`chat-panel ${chatOpen ? "chat-panel-open" : ""}`}>
        <div className="chat-header"><div><span className="bot-icon"><Bot size={18} /></span><span><strong>Ask Ledgerly</strong><small><i />Ready with your business context</small></span></div><button onClick={() => setChatOpen(false)}><X size={18} /></button></div>
        <div className="chat-context"><Sparkles size={14} /><span>Answering only from <strong>Northstar Studio</strong> data</span></div>
        <div className="messages">
          {messages.map((message, index) => <div key={`${message.role}-${index}`} className={`message ${message.role}`}><p>{message.text}</p>{message.role === "assistant" && <small>Based on your {uploadCount} uploads · High confidence</small>}</div>)}
          {messages.length === 1 && <div className="quick-questions">{quickQuestions.map((item) => <button key={item} onClick={() => submitQuestion(item)}>{item}</button>)}</div>}
        </div>
        <div className="chat-composer"><textarea value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submitQuestion(); } }} placeholder="Ask about your business..." /><button onClick={() => submitQuestion()}><Send size={16} /></button><small>Ledgerly explains your data — it doesn&apos;t give financial advice.</small></div>
      </aside>
    </div>
  );
}

function Metric({ label, value, delta, direction, note, spark, neutral = false }: { label: string; value: string; delta: string; direction: "up" | "down"; note: string; spark: number[]; neutral?: boolean }) {
  const points = spark.map((item, index) => `${index * 18},${35 - item / 2.5}`).join(" ");
  return <article className="metric-card"><div className="metric-top"><span>{label}</span><button>•••</button></div><div className="metric-main"><strong>{value}</strong><svg viewBox="0 0 90 36" aria-hidden="true"><polyline points={points} fill="none" stroke={neutral ? "#a99aff" : "#6d50f5"} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" /></svg></div><div className="metric-foot"><span className={neutral ? "delta neutral" : "delta"}>{direction === "up" ? <ArrowUpRight size={13} /> : <ArrowDownRight size={13} />}{delta}</span><small>{note}</small></div></article>;
}

function Insight({ icon, tone, title, text }: { icon: React.ReactNode; tone: string; title: string; text: string }) {
  return <div className="insight-row"><div className={`insight-icon ${tone}`}>{icon}</div><div><strong>{title}</strong><p>{text}</p></div><button><ArrowUpRight size={15} /></button></div>;
}
