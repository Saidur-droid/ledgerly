const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL;
if (!configuredApiUrl && process.env.NODE_ENV === "production") {
  throw new Error("NEXT_PUBLIC_API_URL is required for production builds.");
}
const API_URL = (configuredApiUrl ?? "http://localhost:8000").replace(/\/$/, "");

const TOKEN_KEY = "ledgerly_access_token";

export type User = {
  id: number;
  email: string;
  full_name: string;
};

export type AuthSession = {
  access_token: string;
  token_type: "bearer";
  user: User;
};

export type UserSettings = {
  profile: User;
};

export type UploadRecord = {
  id: number;
  filename: string;
  file_type: string;
  row_count: number;
  confidence: number;
  created_at: string;
};

export type Pulse = {
  score: number;
  confidence: number;
  summary: string;
  factors: Array<Record<string, unknown>>;
  metrics: Record<string, number>;
  comparison: {
    changes: Record<
      string,
      { current: number; previous: number; percent_change: number }
    >;
    message: string;
  } | null;
};

export type AnalysisValue = string | number | boolean | null;

export type AnalysisColumn = {
  label: string;
  align: "left" | "right";
};

export type AnalysisMetric = {
  label: string;
  value: AnalysisValue;
  detail?: string | null;
};

export type TextSection = {
  type: "text";
  heading?: string | null;
  markdown: string;
};

export type MetricsSection = {
  type: "metrics";
  heading?: string | null;
  items: AnalysisMetric[];
};

export type TableSection = {
  type: "table";
  heading?: string | null;
  columns: AnalysisColumn[];
  rows: AnalysisValue[][];
};

export type ListSection = {
  type: "list";
  heading?: string | null;
  style: "bulleted" | "numbered";
  items: string[];
};

export type Scenario = {
  name: string;
  assumptions: string[];
  outcomes: AnalysisMetric[];
};

export type ScenariosSection = {
  type: "scenarios";
  heading?: string | null;
  scenarios: Scenario[];
};

export type ForecastSection = {
  type: "forecast";
  heading?: string | null;
  summary: string;
  horizon?: string | null;
  methodology?: string | null;
  metrics: AnalysisMetric[];
  caveats: string[];
};

export type Risk = {
  label: string;
  detail: string;
  severity: "low" | "medium" | "high" | "unknown";
};

export type RisksSection = {
  type: "risks";
  heading?: string | null;
  items: Risk[];
};

export type AnalysisAction = {
  label: string;
  detail?: string | null;
  priority: "low" | "medium" | "high" | "unprioritized";
};

export type ActionsSection = {
  type: "actions";
  heading?: string | null;
  items: AnalysisAction[];
};

export type NoticeSection = {
  type: "notice";
  heading?: string | null;
  tone: "info" | "warning" | "policy" | "error";
  message: string;
};

export type AnalysisSection =
  | TextSection
  | MetricsSection
  | TableSection
  | ListSection
  | ScenariosSection
  | ForecastSection
  | RisksSection
  | ActionsSection
  | NoticeSection;

type ChatResponseBase = {
  schema_version: 1;
  correlation_id: string;
};

export type MarkdownChatResponse = ChatResponseBase & {
  type: "markdown";
  content: string;
  sections: [];
};

export type StructuredChatResponse = ChatResponseBase & {
  type: "structured";
  content: null;
  sections: AnalysisSection[];
};

export type PolicyNoticeChatResponse = ChatResponseBase & {
  type: "policy_notice";
  content: string;
  sections: AnalysisSection[];
};

export type ErrorChatResponse = ChatResponseBase & {
  type: "error";
  content: string;
  sections: [];
};

export type AskLedgerlyResponse =
  | MarkdownChatResponse
  | StructuredChatResponse
  | PolicyNoticeChatResponse
  | ErrorChatResponse;

const RESPONSE_LIMITS = {
  sections: 24,
  columns: 12,
  rows: 50,
  text: 20_000,
  cell: 500,
} as const;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasOnlyKeys(value: Record<string, unknown>, keys: readonly string[]) {
  return Object.keys(value).every((key) => keys.includes(key));
}

function isText(value: unknown, maximum: number = RESPONSE_LIMITS.text): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= maximum;
}

function isOptionalText(value: unknown, maximum: number = RESPONSE_LIMITS.text) {
  return value === undefined || value === null || isText(value, maximum);
}

function isAnalysisValue(value: unknown): value is AnalysisValue {
  return value === null ||
    typeof value === "boolean" ||
    typeof value === "string" && value.length <= RESPONSE_LIMITS.cell ||
    typeof value === "number" && Number.isFinite(value);
}

function isMetric(value: unknown): value is AnalysisMetric {
  return isRecord(value) &&
    hasOnlyKeys(value, ["label", "value", "detail"]) &&
    isText(value.label, 500) &&
    isAnalysisValue(value.value) &&
    isOptionalText(value.detail, 500);
}

function isStringList(value: unknown, maximum: number): value is string[] {
  return Array.isArray(value) && value.length <= maximum &&
    value.every((item) => isText(item, 500));
}

function isSection(value: unknown): value is AnalysisSection {
  if (!isRecord(value) || typeof value.type !== "string") return false;
  const heading = isOptionalText(value.heading, 500);
  switch (value.type) {
    case "text":
      return hasOnlyKeys(value, ["type", "heading", "markdown"]) &&
        heading && isText(value.markdown);
    case "metrics":
      return hasOnlyKeys(value, ["type", "heading", "items"]) && heading &&
        Array.isArray(value.items) && value.items.length > 0 &&
        value.items.length <= 20 && value.items.every(isMetric);
    case "table": {
      if (!hasOnlyKeys(value, ["type", "heading", "columns", "rows"]) ||
        !heading || !Array.isArray(value.columns) || value.columns.length === 0 ||
        value.columns.length > RESPONSE_LIMITS.columns ||
        !Array.isArray(value.rows) || value.rows.length > RESPONSE_LIMITS.rows) {
        return false;
      }
      const columnCount = value.columns.length;
      return value.columns.every((column) => isRecord(column) &&
          hasOnlyKeys(column, ["label", "align"]) &&
          isText(column.label, 500) &&
          (column.align === "left" || column.align === "right")) &&
        value.rows.every((row) => Array.isArray(row) &&
          row.length === columnCount && row.every(isAnalysisValue));
    }
    case "list":
      return hasOnlyKeys(value, ["type", "heading", "style", "items"]) &&
        heading && (value.style === "bulleted" || value.style === "numbered") &&
        isStringList(value.items, 30);
    case "scenarios":
      return hasOnlyKeys(value, ["type", "heading", "scenarios"]) && heading &&
        Array.isArray(value.scenarios) && value.scenarios.length > 0 &&
        value.scenarios.length <= 10 && value.scenarios.every((scenario) =>
          isRecord(scenario) &&
          hasOnlyKeys(scenario, ["name", "assumptions", "outcomes"]) &&
          isText(scenario.name, 500) &&
          isStringList(scenario.assumptions, 20) &&
          Array.isArray(scenario.outcomes) && scenario.outcomes.length <= 20 &&
          scenario.outcomes.every(isMetric));
    case "forecast":
      return hasOnlyKeys(value, ["type", "heading", "summary", "horizon", "methodology", "metrics", "caveats"]) &&
        heading && isText(value.summary) && isOptionalText(value.horizon, 500) &&
        isOptionalText(value.methodology) && Array.isArray(value.metrics) &&
        value.metrics.length <= 20 && value.metrics.every(isMetric) &&
        isStringList(value.caveats, 20);
    case "risks":
      return hasOnlyKeys(value, ["type", "heading", "items"]) && heading &&
        Array.isArray(value.items) && value.items.length <= 30 &&
        value.items.every((risk) => isRecord(risk) &&
          hasOnlyKeys(risk, ["label", "detail", "severity"]) &&
          isText(risk.label, 500) && isText(risk.detail, 500) &&
          ["low", "medium", "high", "unknown"].includes(String(risk.severity)));
    case "actions":
      return hasOnlyKeys(value, ["type", "heading", "items"]) && heading &&
        Array.isArray(value.items) && value.items.length <= 30 &&
        value.items.every((action) => isRecord(action) &&
          hasOnlyKeys(action, ["label", "detail", "priority"]) &&
          isText(action.label, 500) && isOptionalText(action.detail, 500) &&
          ["low", "medium", "high", "unprioritized"].includes(String(action.priority)));
    case "notice":
      return hasOnlyKeys(value, ["type", "heading", "tone", "message"]) &&
        heading && ["info", "warning", "policy", "error"].includes(String(value.tone)) &&
        isText(value.message);
    default:
      return false;
  }
}

export function parseAskLedgerlyResponse(value: unknown): AskLedgerlyResponse | null {
  if (!isRecord(value) ||
    !hasOnlyKeys(value, ["schema_version", "type", "content", "sections", "correlation_id"]) ||
    value.schema_version !== 1 || !isText(value.correlation_id, 64) ||
    !Array.isArray(value.sections) ||
    value.sections.length > RESPONSE_LIMITS.sections) return null;
  if (value.type === "markdown") {
    return isText(value.content) && value.sections.length === 0
      ? value as MarkdownChatResponse : null;
  }
  if (value.type === "structured") {
    return value.content === null && value.sections.every(isSection)
      ? value as StructuredChatResponse : null;
  }
  if (value.type === "policy_notice") {
    return isText(value.content) && value.sections.every(isSection)
      ? value as PolicyNoticeChatResponse : null;
  }
  if (value.type === "error") {
    return isText(value.content) && value.sections.length === 0
      ? value as ErrorChatResponse : null;
  }
  return null;
}

export function localMarkdownResponse(markdown: string): MarkdownChatResponse {
  return {
    schema_version: 1,
    type: "markdown",
    correlation_id: "local-ui",
    content: markdown,
    sections: [],
  };
}
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function accessToken() {
  return typeof window === "undefined"
    ? null
    : window.sessionStorage.getItem(TOKEN_KEY);
}

function authHeaders(): HeadersInit {
  const token = accessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function parseError(response: Response) {
  try {
    const payload = (await response.json()) as { detail?: string };
    return payload.detail ?? `Request failed with status ${response.status}.`;
  } catch {
    return `Request failed with status ${response.status}.`;
  }
}

async function apiFetch(path: string, init: RequestInit = {}) {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...authHeaders(),
        ...init.headers,
      },
    });
  } catch {
    throw new ApiError(
      "Ledgerly could not reach the API. Please try again in a moment.",
      0,
    );
  }
  if (response.status === 401 && accessToken()) {
    clearSession();
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
  return response;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await apiFetch(path, init);
  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  return response.json() as Promise<T>;
}

export function hasSession() {
  return Boolean(accessToken());
}

export function clearSession() {
  window.sessionStorage.removeItem(TOKEN_KEY);
}

function saveSession(session: AuthSession) {
  window.sessionStorage.setItem(TOKEN_KEY, session.access_token);
  return session;
}

function accountNameFromEmail(email: string) {
  const localPart = email.split("@", 1)[0] ?? "";
  const name = localPart
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
  return name || "Ledgerly User";
}

export async function register(email: string, password: string) {
  const session = await request<AuthSession>("/api/v1/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      email,
      password,
      full_name: accountNameFromEmail(email),
    }),
  });
  return saveSession(session);
}

export async function login(email: string, password: string) {
  const form = new URLSearchParams({ username: email, password });
  const session = await request<AuthSession>("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
  });
  return saveSession(session);
}

export function getCurrentUser() {
  return request<User>("/api/v1/me");
}

export function getSettings() {
  return request<UserSettings>("/api/v1/settings");
}

export function updateProfile(profile: Pick<User, "email" | "full_name">) {
  return request<User>("/api/v1/settings/profile", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
}

export function listUploads() {
  return request<UploadRecord[]>("/api/v1/uploads");
}

export function getLatestPulse() {
  return request<Pulse>("/api/v1/pulse/latest");
}

export function uploadBusinessData(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<Pulse>("/api/v1/uploads", { method: "POST", body: form });
}

export function askBusiness(question: string) {
  return request<unknown>("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  }).then((payload) => {
    const response = parseAskLedgerlyResponse(payload);
    if (!response) {
      throw new ApiError(
        "Ledgerly received an invalid analysis response. Please try again.",
        502,
      );
    }
    return response;
  });
}

export async function downloadLatestReport() {
  const response = await apiFetch("/api/v1/reports/latest.pdf", {
    headers: authHeaders(),
  });
  if (!response.ok) {
    throw new ApiError(await parseError(response), response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "ledgerly-report.pdf";
  anchor.click();
  URL.revokeObjectURL(url);
}
