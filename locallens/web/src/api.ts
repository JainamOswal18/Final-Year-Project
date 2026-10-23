import type { Answer, Completion, CheckResult, Conversation, ConversationSummary, DatasetDetail, DatasetSummary, Feedback, Prefs, Registry, TablePayload, User } from "./types";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

type Listener = () => void;
let onUnauthorized: Listener = () => {};
export const setUnauthorizedHandler = (fn: Listener) => { onUnauthorized = fn; };

async function request<T>(method: string, path: string, body?: unknown, form?: FormData): Promise<T> {
  const headers: Record<string, string> = { "X-Requested-With": "LocalLens" };
  let payload: BodyInit | undefined;
  if (form) payload = form;
  else if (body !== undefined) { headers["Content-Type"] = "application/json"; payload = JSON.stringify(body); }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Check that it is running.");
  }
  if (res.status === 401 && !path.startsWith("/api/auth/login") && !path.startsWith("/api/auth/setup")) onUnauthorized();
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch { /* not JSON */ }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}
const get = <T,>(p: string) => request<T>("GET", p);
const post = <T,>(p: string, b?: unknown) => request<T>("POST", p, b ?? {});
const put = <T,>(p: string, b: unknown) => request<T>("PUT", p, b);
const patch = <T,>(p: string, b: unknown) => request<T>("PATCH", p, b);
const del = <T,>(p: string) => request<T>("DELETE", p);

export const api = {
  status: () => get<{ setup_required: boolean }>("/api/auth/status"),
  health: () => get<{ ok: boolean; model_loaded: boolean; model_present: boolean; model_error: string }>("/api/health"),
  setup: (username: string, password: string) => post<User>("/api/auth/setup", { username, password }),
  login: (username: string, password: string) => post<User>("/api/auth/login", { username, password }),
  logout: () => post<{ ok: boolean }>("/api/auth/logout"),
  me: () => get<User>("/api/auth/me"),
  changePassword: (current_password: string, new_password: string) => post("/api/auth/password", { current_password, new_password }),

  users: () => get<User[]>("/api/users"),
  createUser: (username: string, role: string, password?: string) => post<User & { temporary_password: string }>("/api/users", { username, role, password: password || null }),
  patchUser: (id: number, body: { role?: string; active?: boolean; new_password?: string }) => patch<User & { temporary_password?: string }>(`/api/users/${id}`, body),
  deleteUser: (id: number) => del(`/api/users/${id}`),
  feedback: (onlyNegative = true) => get<Feedback[]>(`/api/admin/feedback?only_negative=${onlyNegative}`),

  datasets: () => get<DatasetSummary[]>("/api/datasets"),
  dataset: (id: string) => get<DatasetDetail>(`/api/datasets/${id}`),
  createDataset: (name: string, files: File[]) => {
    const f = new FormData(); f.append("name", name); files.forEach((x) => f.append("files", x));
    return request<DatasetSummary>("POST", "/api/datasets", undefined, f);
  },
  demoDataset: () => post<DatasetSummary>("/api/datasets/demo"),
  patchDataset: (id: string, body: { name?: string; visibility?: string }) => patch<DatasetSummary>(`/api/datasets/${id}`, body),
  deleteDataset: (id: string) => del(`/api/datasets/${id}`),
  saveRegistry: (id: string, reg: Registry) => put<{ registry: Registry; problems: string[] }>(`/api/datasets/${id}/registry`, reg),
  preview: (id: string, table: string, limit = 50) => get<TablePayload>(`/api/datasets/${id}/preview?table=${encodeURIComponent(table)}&limit=${limit}`),
  check: (id: string, kind: "measure" | "column" | "rule", expression: string) => post<CheckResult>(`/api/datasets/${id}/check-expression`, { kind, expression }),
  complete: (id: string, q: string) => get<Completion[]>(`/api/datasets/${id}/complete?q=${encodeURIComponent(q)}`),
  suggestions: (id: string) => get<string[]>(`/api/datasets/${id}/suggestions`),

  conversations: (datasetId: string) => get<ConversationSummary[]>(`/api/datasets/${datasetId}/conversations`),
  conversation: (id: string) => get<Conversation>(`/api/conversations/${id}`),
  deleteConversation: (id: string) => del(`/api/conversations/${id}`),
  ask: (datasetId: string, question: string, conversation_id: string | null, overrides?: Record<string, string>) =>
    post<{ conversation_id: string; message_id: string; response: Answer }>(`/api/datasets/${datasetId}/ask`, { question, conversation_id, overrides: overrides ?? null }),
  rate: (messageId: string, rating: number, note = "") => post(`/api/messages/${messageId}/feedback`, { rating, note }),
  saveExample: (messageId: string) => post<{ ok: boolean; already: boolean }>(`/api/messages/${messageId}/example`),
  exportUrl: (messageId: string, kind: string) => `/api/messages/${messageId}/export/${kind}`,

  prefs: () => get<Prefs>("/api/prefs"),
  savePrefs: (p: { sort: string; chart_overrides: Record<string, string>; default_agg: string }) => put<Prefs>("/api/prefs", p),
};
