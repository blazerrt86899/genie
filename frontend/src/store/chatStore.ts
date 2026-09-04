import { create } from "zustand";
import type { MessageFileView, PlanStepView } from "@/lib/sse";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  pending?: boolean;
  agents?: string[]; // agents that produced this assistant message
  attachments?: { filename: string; kind: string }[]; // files sent with a user message
  sources?: { title: string; url: string }[]; // link cards under an assistant message
  createdAt?: string; // ISO — absent on optimistic (not-yet-persisted) messages
  feedback?: "up" | "down" | null; // the user's 👍/👎 on an assistant message
  cached?: boolean; // assistant reply served from the response cache
  guardrail?: { redacted: string[]; flagged: string[]; message: string } | null; // on a user message
  thinking?: string; // the reasoning trace behind this message (thinking-capable models)
  thinkingMs?: number | null; // how long that reasoning took, once done
  thinkingActive?: boolean; // a trace is currently streaming in
  files?: MessageFileView[]; // generated, downloadable files produced this turn
}

export interface ProjectRef {
  id: string;
  name: string;
}

export interface PendingAttachment {
  id: string; // real id once ready; a temp uuid while uploading
  filename: string;
  kind: string;
  status: "uploading" | "ready" | "error";
}

interface ChatState {
  messages: ChatMessage[];
  activeAgents: string[];
  plan: PlanStepView[];
  runId: string | null;
  conversationId: string | null;
  conversationTitle: string | null;
  setConversationTitle: (title: string | null) => void;
  conversationPinned: boolean;
  conversationUnread: boolean;
  setConversationFlags: (f: { pinned?: boolean; unread?: boolean }) => void;
  turnGuardrail: string | null; // transient banner while a guarded turn streams
  setTurnGuardrail: (message: string | null) => void;
  project: ProjectRef | null;
  model: string | null; // picked chat-model id; null → server default
  setModel: (model: string | null) => void;
  pendingAttachments: PendingAttachment[]; // staged for the next message
  addPendingAttachment: (a: PendingAttachment) => void;
  updatePendingAttachment: (id: string, patch: Partial<PendingAttachment>) => void;
  removePendingAttachment: (id: string) => void;
  clearPendingAttachments: () => void;
  pendingProjectId: string | null; // "Add to project" chosen before a new chat exists
  setPendingProjectId: (id: string | null) => void;
  setPlan: (plan: PlanStepView[]) => void;
  addMessage: (message: ChatMessage) => void;
  setMessages: (messages: ChatMessage[]) => void;
  appendToken: (id: string, token: string) => void;
  appendThinking: (id: string, delta: string) => void;
  setThinkingDone: (id: string, ms: number) => void;
  setMessagePending: (id: string, pending: boolean) => void;
  setMessageAgents: (id: string, agents: string[]) => void;
  setMessageSources: (id: string, sources: { title: string; url: string }[]) => void;
  setMessageFiles: (id: string, files: MessageFileView[]) => void;
  setMessageFeedback: (id: string, feedback: "up" | "down" | null) => void;
  updateMessageContent: (id: string, content: string) => void;
  truncateAfter: (id: string, opts?: { inclusive?: boolean }) => void;
  setActiveAgents: (agents: string[]) => void;
  agentStarted: (agent: string) => void;
  agentEnded: (agent: string) => void;
  setRunId: (runId: string | null) => void;
  setConversationId: (conversationId: string | null) => void;
  setProject: (project: ProjectRef | null) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  activeAgents: [],
  plan: [],
  runId: null,
  conversationId: null,
  conversationTitle: null,
  setConversationTitle: (conversationTitle) => set({ conversationTitle }),
  conversationPinned: false,
  conversationUnread: false,
  setConversationFlags: (f) =>
    set((s) => ({
      conversationPinned: f.pinned ?? s.conversationPinned,
      conversationUnread: f.unread ?? s.conversationUnread,
    })),
  turnGuardrail: null,
  setTurnGuardrail: (turnGuardrail) => set({ turnGuardrail }),
  project: null,
  model: null,
  setModel: (model) => set({ model }),
  pendingAttachments: [],
  addPendingAttachment: (a) =>
    set((s) => ({ pendingAttachments: [...s.pendingAttachments, a] })),
  updatePendingAttachment: (id, patch) =>
    set((s) => ({
      pendingAttachments: s.pendingAttachments.map((a) =>
        a.id === id ? { ...a, ...patch } : a,
      ),
    })),
  removePendingAttachment: (id) =>
    set((s) => ({
      pendingAttachments: s.pendingAttachments.filter((a) => a.id !== id),
    })),
  clearPendingAttachments: () => set({ pendingAttachments: [] }),
  pendingProjectId: null,
  setPendingProjectId: (pendingProjectId) => set({ pendingProjectId }),
  setPlan: (plan) => set({ plan }),
  addMessage: (message) =>
    set((s) => ({ messages: [...s.messages, message] })),
  setMessages: (messages) => set({ messages }),
  appendToken: (id, token) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + token } : m,
      ),
    })),
  appendThinking: (id, delta) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id
          ? { ...m, thinking: (m.thinking ?? "") + delta, thinkingActive: true }
          : m,
      ),
    })),
  setThinkingDone: (id, ms) =>
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, thinkingMs: ms, thinkingActive: false } : m,
      ),
    })),
  setMessagePending: (id, pending) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, pending } : m)),
    })),
  setMessageAgents: (id, agents) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, agents } : m)),
    })),
  setMessageSources: (id, sources) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, sources } : m)),
    })),
  setMessageFiles: (id, files) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, files } : m)),
    })),
  setMessageFeedback: (id, feedback) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, feedback } : m)),
    })),
  updateMessageContent: (id, content) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, content } : m)),
    })),
  truncateAfter: (id, opts) =>
    set((s) => {
      const i = s.messages.findIndex((m) => m.id === id);
      if (i === -1) return {};
      return { messages: s.messages.slice(0, opts?.inclusive ? i : i + 1) };
    }),
  setActiveAgents: (agents) => set({ activeAgents: agents }),
  agentStarted: (agent) =>
    set((s) => ({
      activeAgents: s.activeAgents.includes(agent)
        ? s.activeAgents
        : [...s.activeAgents, agent],
    })),
  agentEnded: (agent) =>
    set((s) => ({ activeAgents: s.activeAgents.filter((a) => a !== agent) })),
  setRunId: (runId) => set({ runId }),
  setConversationId: (conversationId) => set({ conversationId }),
  setProject: (project) => set({ project }),
  reset: () =>
    set({
      messages: [],
      activeAgents: [],
      plan: [],
      runId: null,
      conversationId: null,
      conversationTitle: null,
      conversationPinned: false,
      conversationUnread: false,
      turnGuardrail: null,
      project: null,
      pendingAttachments: [],
      pendingProjectId: null,
      // `model` is intentionally kept — the pick carries across new chats.
    }),
}));
