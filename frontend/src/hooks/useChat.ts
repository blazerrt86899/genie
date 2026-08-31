"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import { chatStreamUrl, getConversation, postChat } from "@/lib/api";
import { parseSseStream } from "@/lib/sse";
import { useChatStore } from "@/store/chatStore";

const CONVERSATIONS_KEY = ["conversations"] as const;

/**
 * Drives one chat view. The route is the source of truth:
 *   /chat        → conversationId undefined → blank new chat
 *   /chat/<uuid> → load that conversation's messages
 * On the first message of a new chat we POST, learn the id, and
 * `router.replace('/chat/<id>')` (messages already in the store, so no flash).
 */
export function useChat(conversationId?: string, projectId?: string | null) {
  const { getToken } = useAuth();
  const router = useRouter();
  const qc = useQueryClient();
  const store = useChatStore();

  useEffect(() => {
    const s = useChatStore.getState();

    if (!conversationId) {
      if (s.conversationId !== null || s.messages.length > 0) s.reset();
      return;
    }
    if (s.conversationId === conversationId) return; // already loaded (or just created)

    let cancelled = false;
    (async () => {
      s.reset();
      try {
        const conv = await getConversation(conversationId, await getToken());
        if (cancelled) return;
        s.setConversationId(conv.id);
        s.setProject(conv.project);
        s.setMessages(
          conv.messages.map((m) => ({
            id: m.id,
            role: m.role,
            content: m.content,
            agents: m.agents ?? [],
          })),
        );
      } catch {
        if (!cancelled) router.replace("/chat");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, getToken, router]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || useChatStore.getState().runId) return;

      const s = useChatStore.getState();
      s.addMessage({ id: crypto.randomUUID(), role: "user", content: message });
      // One turn can produce several assistant messages (e.g. greeting, then the
      // answer); `currentId` points at the one tokens currently flow into.
      let currentId = crypto.randomUUID();
      s.addMessage({ id: currentId, role: "assistant", content: "", pending: true });
      s.setActiveAgents([]);

      const token = await getToken();
      const existingCid = useChatStore.getState().conversationId;

      try {
        const { run_id, conversation_id } = await postChat(
          message,
          existingCid,
          token,
          existingCid ? null : projectId,
        );
        s.setRunId(run_id);
        s.setConversationId(conversation_id);
        if (!existingCid) {
          qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
          if (projectId) {
            qc.invalidateQueries({ queryKey: ["project", projectId] });
          }
          router.replace(`/chat/${conversation_id}`);
        }

        const res = await fetch(chatStreamUrl(conversation_id, run_id), {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok || !res.body) throw new Error(`stream failed (${res.status})`);

        await parseSseStream(res.body, (event) => {
          if (event.type === "token") {
            s.appendToken(currentId, event.content);
          } else if (event.type === "message_break") {
            s.setMessagePending(currentId, false);
            currentId = crypto.randomUUID();
            s.addMessage({
              id: currentId,
              role: "assistant",
              content: "",
              pending: true,
            });
          } else if (event.type === "message_agents") {
            s.setMessageAgents(currentId, event.agents);
          } else if (event.type === "agent_start") {
            s.agentStarted(event.agent);
          } else if (event.type === "agent_end") {
            s.agentEnded(event.agent);
          } else if (
            event.type === "task_created" ||
            event.type === "task_updated" ||
            event.type === "tasks_archived"
          ) {
            qc.invalidateQueries({ queryKey: ["tasks"] });
          } else if (event.type === "error") {
            s.appendToken(currentId, `\n\n⚠️ ${event.message}`);
          } else if (event.type === "title") {
            qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
          }
        });
      } catch (err) {
        s.appendToken(
          currentId,
          `\n\n⚠️ ${err instanceof Error ? err.message : "Something went wrong"}`,
        );
      } finally {
        s.setMessagePending(currentId, false);
        s.setRunId(null);
        s.setActiveAgents([]);
        qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
      }
    },
    [getToken, router, qc, projectId],
  );

  return {
    messages: store.messages,
    isStreaming: store.runId !== null,
    project: store.project,
    send,
  };
}
