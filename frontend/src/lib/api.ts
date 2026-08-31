/**
 * Typed fetch wrapper. All API calls go through here (CLAUDE.md §17).
 * Attaches the Clerk bearer token when a getter is provided.
 */

// Use 127.0.0.1, not "localhost": on many machines the browser resolves
// localhost to IPv6 (::1) first, where a default uvicorn (IPv4-only) isn't
// listening — which makes the health check spuriously fail.
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type FetchOptions = RequestInit & { token?: string | null };

export async function apiFetch<T = unknown>(
  path: string,
  { token, headers, ...options }: FetchOptions = {},
): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
  });

  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export interface HealthResponse {
  status: string;
}

export function getHealth(): Promise<HealthResponse> {
  return apiFetch<HealthResponse>("/health");
}

// ─── Chat ──────────────────────────────────────────────────────────────────

export interface ChatAccepted {
  run_id: string;
  conversation_id: string;
}

export function postChat(
  message: string,
  conversationId: string | null,
  token?: string | null,
  projectId?: string | null,
): Promise<ChatAccepted> {
  return apiFetch<ChatAccepted>("/api/v1/chat", {
    method: "POST",
    token,
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      project_id: projectId ?? null,
      // the user's local hour — lets time-aware agents (greeting) get it right
      client_hour: new Date().getHours(),
    }),
  });
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  agents?: string[];
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string | null;
  project_id: string | null;
}

export interface ConversationDetail extends ConversationSummary {
  project: { id: string; name: string } | null;
  messages: ConversationMessage[];
}

export function getConversation(
  id: string,
  token?: string | null,
): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/api/v1/conversations/${id}`, { token });
}

export function listConversations(
  token?: string | null,
): Promise<ConversationSummary[]> {
  return apiFetch<ConversationSummary[]>("/api/v1/conversations", { token });
}

export function deleteConversation(
  id: string,
  token?: string | null,
): Promise<void> {
  return apiFetch<void>(`/api/v1/conversations/${id}`, {
    method: "DELETE",
    token,
  });
}

// ─── Projects ──────────────────────────────────────────────────────────────

export interface Project {
  id: string;
  name: string;
  description: string | null;
  instructions: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectSummary extends Project {
  conversation_count: number;
}

export interface ProjectDetail extends Project {
  conversations: ConversationSummary[];
}

export interface ProjectInput {
  name?: string;
  description?: string | null;
  instructions?: string | null;
}

export function listProjects(token?: string | null): Promise<ProjectSummary[]> {
  return apiFetch<ProjectSummary[]>("/api/v1/projects", { token });
}

export function getProject(
  id: string,
  token?: string | null,
): Promise<ProjectDetail> {
  return apiFetch<ProjectDetail>(`/api/v1/projects/${id}`, { token });
}

export function createProject(
  body: ProjectInput,
  token?: string | null,
): Promise<Project> {
  return apiFetch<Project>("/api/v1/projects", {
    method: "POST",
    token,
    body: JSON.stringify(body),
  });
}

export function updateProject(
  id: string,
  body: ProjectInput,
  token?: string | null,
): Promise<Project> {
  return apiFetch<Project>(`/api/v1/projects/${id}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(body),
  });
}

export function deleteProject(
  id: string,
  token?: string | null,
): Promise<void> {
  return apiFetch<void>(`/api/v1/projects/${id}`, { method: "DELETE", token });
}

export function chatStreamUrl(conversationId: string, runId: string): string {
  return `${API_BASE_URL}/api/v1/chat/${conversationId}/stream?run_id=${encodeURIComponent(runId)}`;
}
