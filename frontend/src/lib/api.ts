const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "https://ledgerly-z984.onrender.com"
).replace(/\/$/, "");

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

export type ChatResponse = {
  answer: string;
  confidence: string;
  sources: string[];
  disclaimer: string;
};

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

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...authHeaders(),
      ...init.headers,
    },
  });
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
  return request<ChatResponse>("/api/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function downloadLatestReport() {
  const response = await fetch(`${API_URL}/api/v1/reports/latest.pdf`, {
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
