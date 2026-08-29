import { create } from "zustand";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  pending?: boolean;
}

interface ChatState {
  messages: ChatMessage[];
  activeAgents: string[];
  runId: string | null;
  addMessage: (message: ChatMessage) => void;
  appendToken: (id: string, token: string) => void;
  setMessagePending: (id: string, pending: boolean) => void;
  setActiveAgents: (agents: string[]) => void;
  agentStarted: (agent: string) => void;
  agentEnded: (agent: string) => void;
  setRunId: (runId: string | null) => void;
  reset: () => void;
}

export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  activeAgents: [],
  runId: null,
  addMessage: (message) =>
    set((s) => ({ messages: [...s.messages, message] })),
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
  reset: () => set({ messages: [], activeAgents: [], runId: null }),
}));
