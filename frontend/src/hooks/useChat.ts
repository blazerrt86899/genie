/**
 * Chat lifecycle hook — STUB (Phase 1).
 *
 * Planned: POST /api/v1/chat -> { run_id, conversation_id }, then
 * GET /api/v1/chat/{conversation_id}/stream?run_id=... and feed frames through
 * `parseSseStream` into `useChatStore` (appendToken / agentStarted / agentEnded).
 */

import { useChatStore } from "@/store/chatStore";

export function useChat() {
  const store = useChatStore();

  async function send(message: string): Promise<void> {
    void message;
    throw new Error("useChat.send not implemented yet (Phase 1)");
  }

  return { messages: store.messages, activeAgents: store.activeAgents, send };
}
