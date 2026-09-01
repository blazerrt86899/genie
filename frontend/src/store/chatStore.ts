import { create } from "zustand";
import type { PlanStepView } from "@/lib/sse";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  pending?: boolean;
  agents?: string[]; // agents that produced this assistant message
}

export interface ProjectRef {
  id: string;
  name: string;
}

interface ChatState {
  messages: ChatMessage[];
  activeAgents: string[];
  plan: PlanStepView[];
  runId: string | null;
  conversationId: string | null;
  project: ProjectRef | null;
  model: string | null; // picked chat-model id; null → server default
  setModel: (model: string | null) => void;
  setPlan: (plan: PlanStepView[]) => void;
  addMessage: (message: ChatMessage) => void;
  setMessages: (messages: ChatMessage[]) => void;
  appendToken: (id: string, token: string) => void;
  setMessagePending: (id: string, pending: boolean) => void;
  setMessageAgents: (id: string, agents: string[]) => void;
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
  project: null,
  model: null,
  setModel: (model) => set({ model }),
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
  setMessagePending: (id, pending) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, pending } : m)),
    })),
  setMessageAgents: (id, agents) =>
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, agents } : m)),
    })),
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
      project: null,
      // `model` is intentionally kept — the pick carries across new chats.
    }),
}));
