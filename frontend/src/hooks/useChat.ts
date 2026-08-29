"use client";

import { useCallback } from "react";
import { useAuth } from "@clerk/nextjs";
import { chatStreamUrl, getConversation, postChat } from "@/lib/api";
import { parseSseStream } from "@/lib/sse";
import { useChatStore } from "@/store/chatStore";

const CID_KEY = "genie:conversation_id";

/**
 * Chat turn lifecycle: POST /chat → open the SSE stream → feed frames into the
 * store. Conversation memory lives server-side (LangGraph checkpointer); the id
 * is remembered in localStorage so a reload rehydrates the thread.
 */
export function useChat() {
  const { getToken } = useAuth();
  const store = useChatStore();
  const {
    messages,
    conversationId,
    runId,
    addMessage,
    setMessages,
    appendToken,
    setMessagePending,
    setRunId,
    setConversationId,
  } = store;

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || useChatStore.getState().runId) return;

      addMessage({ id: crypto.randomUUID(), role: "user", content: message });
      const assistantId = crypto.randomUUID();
      addMessage({ id: assistantId, role: "assistant", content: "", pending: true });

      const token = await getToken();
      const currentCid = useChatStore.getState().conversationId;

      try {
        const { run_id, conversation_id } = await postChat(
          message,
          currentCid,
          token,
        );
        setRunId(run_id);
        setConversationId(conversation_id);
        try {
          localStorage.setItem(CID_KEY, conversation_id);
        } catch {
          /* ignore */
        }

        const res = await fetch(chatStreamUrl(conversation_id, run_id), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok || !res.body) {
          throw new Error(`stream failed (${res.status})`);
        }

        await parseSseStream(res.body, (event) => {
          if (event.type === "token") {
            appendToken(assistantId, event.content);
          } else if (event.type === "error") {
            appendToken(assistantId, `\n\n⚠️ ${event.message}`);
          }
        });
      } catch (err) {
        appendToken(
          assistantId,
          `\n\n⚠️ ${err instanceof Error ? err.message : "Something went wrong"}`,
        );
      } finally {
        setMessagePending(assistantId, false);
        setRunId(null);
      }
    },
    [getToken, addMessage, appendToken, setMessagePending, setRunId, setConversationId],
  );

  const hydrate = useCallback(async () => {
    if (useChatStore.getState().messages.length > 0) return;
    let cid: string | null = null;
    try {
      cid = localStorage.getItem(CID_KEY);
    } catch {
      return;
    }
    if (!cid) return;
    try {
      const token = await getToken();
      const conv = await getConversation(cid, token);
      setConversationId(conv.id);
      setMessages(
        conv.messages.map((m) => ({
          id: m.id,
          role: m.role,
          content: m.content,
        })),
      );
    } catch {
      // stale id — drop it
      try {
        localStorage.removeItem(CID_KEY);
      } catch {
        /* ignore */
      }
    }
  }, [getToken, setConversationId, setMessages]);

  return {
    messages,
    conversationId,
    isStreaming: runId !== null,
    send,
    hydrate,
  };
}
