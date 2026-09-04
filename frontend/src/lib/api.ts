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

export interface Me {
  id: string;
  email: string;
  full_name: string | null;
  avatar_url: string | null;
  token_budget: number;
}

export function getMe(token?: string | null): Promise<Me> {
  return apiFetch<Me>("/api/v1/users/me", { token });
}

export interface UsageInfo {
  token_budget: number;
  tokens_used_30d: number;
  messages_30d: number;
  conversations: number;
}

export function getUsage(token?: string | null): Promise<UsageInfo> {
  return apiFetch<UsageInfo>("/api/v1/users/me/usage", { token });
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
  model?: string | null,
  attachmentIds?: string[],
): Promise<ChatAccepted> {
  return apiFetch<ChatAccepted>("/api/v1/chat", {
    method: "POST",
    token,
    body: JSON.stringify({
      message,
      conversation_id: conversationId,
      project_id: projectId ?? null,
      model: model ?? null,
      attachment_ids: attachmentIds ?? [],
      // the user's local hour — lets time-aware agents (greeting) get it right
      client_hour: new Date().getHours(),
    }),
  });
}

/** Truncate a conversation at a message and re-run — regenerate a Genie reply,
 *  or retry / edit one of the user's messages (pass `edit`). */
export function regenerateChat(
  conversationId: string,
  fromMessageId: string,
  edit: string | null,
  token?: string | null,
): Promise<ChatAccepted> {
  return apiFetch<ChatAccepted>(`/api/v1/chat/${conversationId}/regenerate`, {
    method: "POST",
    token,
    body: JSON.stringify({ from_message_id: fromMessageId, edit }),
  });
}

export function sendMessageFeedback(
  messageId: string,
  vote: "up" | "down" | null,
  token?: string | null,
): Promise<{ vote: string | null }> {
  return apiFetch<{ vote: string | null }>(
    `/api/v1/messages/${messageId}/feedback`,
    { method: "POST", token, body: JSON.stringify({ vote }) },
  );
}

// ─── Attachments (composer "+" menu) ───────────────────────────────────────

export interface AttachmentDto {
  id: string;
  filename: string;
  kind: "pdf" | "txt" | "md";
  char_count: number;
  token_estimate: number;
}

export async function uploadAttachment(
  file: File,
  token?: string | null,
): Promise<AttachmentDto> {
  const form = new FormData();
  form.append("file", file);
  // NOT apiFetch — multipart needs the browser to set the boundary header.
  const res = await fetch(`${API_BASE_URL}/api/v1/attachments`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body || res.statusText);
  }
  return (await res.json()) as AttachmentDto;
}

export function deleteAttachment(
  id: string,
  token?: string | null,
): Promise<void> {
  return apiFetch<void>(`/api/v1/attachments/${id}`, { method: "DELETE", token });
}

// ─── Models (the composer's model picker) ──────────────────────────────────

export interface ModelOption {
  id: string;
  label: string;
  provider: string;
  hint: string;
}

export interface ModelsResponse {
  models: ModelOption[];
  default: string | null;
}

export function listModels(token?: string | null): Promise<ModelsResponse> {
  return apiFetch<ModelsResponse>("/api/v1/models", { token });
}

export interface MessageAttachment {
  id: string;
  filename: string;
  kind: string;
  char_count: number;
}

export interface MessageSource {
  title: string;
  url: string;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  agents?: string[];
  attachments?: MessageAttachment[];
  sources?: MessageSource[];
  feedback?: "up" | "down" | null;
  cached?: boolean;
  guardrail?: { redacted: string[]; flagged: string[]; message: string } | null;
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  last_message_at: string | null;
  project_id: string | null;
  model: string | null;
  pinned: boolean;
  unread: boolean;
}

export interface ShareInfo {
  token: string;
  url: string;
  shared_at: string;
}

export interface ConversationDetail extends ConversationSummary {
  project: { id: string; name: string } | null;
  messages: ConversationMessage[];
  share: ShareInfo | null;
}

export function getConversation(
  id: string,
  token?: string | null,
): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/api/v1/conversations/${id}`, { token });
}

export function getConversationShare(
  id: string,
  token?: string | null,
): Promise<ShareInfo | null> {
  return apiFetch<ShareInfo | null>(`/api/v1/conversations/${id}/share`, {
    token,
  });
}

export function shareConversation(
  id: string,
  token?: string | null,
): Promise<ShareInfo> {
  return apiFetch<ShareInfo>(`/api/v1/conversations/${id}/share`, {
    method: "POST",
    token,
  });
}

export function unshareConversation(
  id: string,
  token?: string | null,
): Promise<void> {
  return apiFetch<void>(`/api/v1/conversations/${id}/share`, {
    method: "DELETE",
    token,
  });
}

// ─── Public (unauthenticated) shared-chat view ─────────────────────────────

export interface SharedConversation {
  title: string | null;
  shared_at: string;
  message_count: number;
  messages: ConversationMessage[];
}

export function getSharedConversation(
  shareToken: string,
): Promise<SharedConversation> {
  return apiFetch<SharedConversation>(
    `/api/v1/public/shared/${encodeURIComponent(shareToken)}`,
  );
}

export function listConversations(
  token?: string | null,
): Promise<ConversationSummary[]> {
  return apiFetch<ConversationSummary[]>("/api/v1/conversations", { token });
}

export interface ConversationSearchResult extends ConversationSummary {
  snippet: string | null; // excerpt of the matching message (content match only)
}

export function searchConversations(
  q: string,
  token?: string | null,
  limit = 30,
): Promise<ConversationSearchResult[]> {
  return apiFetch<ConversationSearchResult[]>(
    `/api/v1/conversations/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    { token },
  );
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

export function patchConversation(
  id: string,
  body: {
    project_id?: string | null;
    title?: string;
    pinned?: boolean;
    unread?: boolean;
  },
  token?: string | null,
): Promise<ConversationSummary> {
  return apiFetch<ConversationSummary>(`/api/v1/conversations/${id}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(body),
  });
}

// ─── Projects ──────────────────────────────────────────────────────────────

export type SearchStrategy =
  | "vector"
  | "hybrid"
  | "multi_query_vector"
  | "multi_query_hybrid";

export interface RagSettings {
  embedding_model: string;
  search_strategy: SearchStrategy;
  chunks_per_search: number;
  final_context_size: number;
  similarity_threshold: number;
  num_queries: number;
  chunk_size: number;
  chunk_overlap: number;
}

export interface Project {
  id: string;
  name: string;
  description: string | null;
  instructions: string | null;
  rag_settings: RagSettings;
  document_count: number;
  rag_locked: boolean;
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
  rag_settings?: Partial<RagSettings>;
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

// ─── Knowledge Base documents ──────────────────────────────────────────────

export interface DocumentDto {
  id: string;
  project_id: string;
  filename: string;
  kind: "pdf" | "md" | "txt";
  status: "queued" | "processing" | "ready" | "failed";
  phase: "upload" | "partition" | "chunk" | "vectorize" | "store" | "done";
  error: string | null;
  stats: {
    elements?: Record<string, number>;
    chunk_count?: number;
  };
  chunk_count: number;
  byte_size: number;
  created_at: string;
  processed_at: string | null;
}

export interface ChunkDto {
  chunk_index: number;
  content: string;
  token_count: number;
  metadata: { page?: number | null; element_types?: string[]; heading?: string | null };
}

export async function uploadDocument(
  projectId: string,
  file: File,
  token?: string | null,
): Promise<DocumentDto> {
  const form = new FormData();
  form.append("project_id", projectId);
  form.append("file", file);
  const res = await fetch(`${API_BASE_URL}/api/v1/documents`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, (await res.text()) || res.statusText);
  return (await res.json()) as DocumentDto;
}

export function listDocuments(
  projectId: string,
  token?: string | null,
): Promise<DocumentDto[]> {
  return apiFetch<DocumentDto[]>(`/api/v1/documents?project_id=${projectId}`, { token });
}

export function getDocument(id: string, token?: string | null): Promise<DocumentDto> {
  return apiFetch<DocumentDto>(`/api/v1/documents/${id}`, { token });
}

export function listChunks(
  id: string,
  token?: string | null,
  opts: { limit?: number; offset?: number } = {},
): Promise<ChunkDto[]> {
  const q = new URLSearchParams({
    limit: String(opts.limit ?? 50),
    offset: String(opts.offset ?? 0),
  });
  return apiFetch<ChunkDto[]>(`/api/v1/documents/${id}/chunks?${q}`, { token });
}

export function deleteDocument(id: string, token?: string | null): Promise<void> {
  return apiFetch<void>(`/api/v1/documents/${id}`, { method: "DELETE", token });
}

export function documentStreamUrl(id: string): string {
  return `${API_BASE_URL}/api/v1/documents/${id}/stream`;
}

// ─── Tasks ─────────────────────────────────────────────────────────────────

export interface TaskDto {
  id: string;
  title: string;
  description: string | null;
  status: "todo" | "in_progress" | "done" | "archived";
  conversation_id: string | null;
  source_agent: string | null;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
}

export function listTasks(
  token?: string | null,
  includeArchived = false,
): Promise<TaskDto[]> {
  const q = includeArchived ? "?include_archived=true" : "";
  return apiFetch<TaskDto[]>(`/api/v1/tasks${q}`, { token });
}

export function getTask(id: string, token?: string | null): Promise<TaskDto> {
  return apiFetch<TaskDto>(`/api/v1/tasks/${id}`, { token });
}

export function createTask(
  body: { title: string; description?: string | null },
  token?: string | null,
): Promise<TaskDto> {
  return apiFetch<TaskDto>("/api/v1/tasks", {
    method: "POST",
    token,
    body: JSON.stringify(body),
  });
}

export function patchTask(
  id: string,
  body: { title?: string; description?: string | null; status?: string },
  token?: string | null,
): Promise<TaskDto> {
  return apiFetch<TaskDto>(`/api/v1/tasks/${id}`, {
    method: "PATCH",
    token,
    body: JSON.stringify(body),
  });
}

export function archiveDoneTasks(
  token?: string | null,
): Promise<{ archived: number }> {
  return apiFetch<{ archived: number }>("/api/v1/tasks/archive-done", {
    method: "POST",
    token,
  });
}

export function summarizeTask(
  id: string,
  token?: string | null,
): Promise<TaskDto> {
  return apiFetch<TaskDto>(`/api/v1/tasks/${id}/summarize`, {
    method: "POST",
    token,
  });
}

export function deleteTask(id: string, token?: string | null): Promise<void> {
  return apiFetch<void>(`/api/v1/tasks/${id}`, { method: "DELETE", token });
}
