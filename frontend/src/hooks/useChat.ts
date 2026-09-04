"use client";

import { useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import {
  chatStreamUrl,
  getConversation,
  postChat,
  regenerateChat,
  sendMessageFeedback,
} from "@/lib/api";
import { parseSseStream } from "@/lib/sse";
import { useChatStore, type ChatMessage } from "@/store/chatStore";
import type { ConversationMessage } from "@/lib/api";

const CONVERSATIONS_KEY = ["conversations"] as const;

/** API messages → store messages (used on load and after a stream completes). */
function mapMessages(rows: ConversationMessage[]): ChatMessage[] {
  return rows.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    agents: m.agents ?? [],
    attachments: (m.attachments ?? []).map((a) => ({
      filename: a.filename,
      kind: a.kind,
    })),
    sources: m.sources ?? [],
    createdAt: m.created_at,
    feedback: m.feedback ?? null,
    cached: m.cached ?? false,
    guardrail: m.guardrail ?? null,
    thinking: m.thinking ?? undefined,
    thinkingMs: m.thinking_ms ?? null,
    files: m.files ?? [],
  }));
}

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
      // Fresh chat → start from the last-picked model (browser-remembered).
      if (s.model == null) {
        try {
          const saved = localStorage.getItem("genie.chat_model");
          if (saved) s.setModel(saved);
        } catch {
          /* private mode / storage disabled */
        }
      }
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
        s.setConversationTitle(conv.title);
        s.setConversationFlags({ pinned: conv.pinned, unread: false });
        s.setProject(conv.project);
        s.setModel(conv.model);
        // the GET marked it read server-side — refresh the sidebar's bullet
        qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
        s.setMessages(mapMessages(conv.messages));
      } catch {
        if (!cancelled) router.replace("/chat");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [conversationId, getToken, router]);

  /** Open the SSE stream for a run and fold every frame into the store.
   *  `firstId` is the pending assistant message tokens start flowing into. */
  const consumeStream = useCallback(
    async (cid: string, runId: string, firstId: string) => {
      const s = useChatStore.getState();
      const token = await getToken();
      let currentId = firstId;

      const res = await fetch(chatStreamUrl(cid, runId), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok || !res.body) throw new Error(`stream failed (${res.status})`);

      await parseSseStream(res.body, (event) => {
        if (event.type === "token") {
          s.appendToken(currentId, event.content);
        } else if (event.type === "thinking") {
          s.appendThinking(currentId, event.content);
        } else if (event.type === "thinking_done") {
          s.setThinkingDone(currentId, event.duration_ms);
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
        } else if (event.type === "sources") {
          s.setMessageSources(currentId, event.items);
        } else if (event.type === "files") {
          s.setMessageFiles(currentId, event.items);
        } else if (event.type === "guardrail") {
          s.setTurnGuardrail(event.message || "Sensitive data was hidden before sending.");
        } else if (event.type === "plan") {
          s.setPlan(event.steps);
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
          s.setConversationTitle(event.title);
          qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
        }
      });

      s.setMessagePending(currentId, false);
    },
    [getToken, qc],
  );

  /** Replace the optimistic (client-id) messages with the persisted rows, so
   *  the action bar gets real ids + dates and a follow-up regenerate works. */
  const refreshMessages = useCallback(async () => {
    const cid = useChatStore.getState().conversationId;
    if (!cid) return;
    try {
      const conv = await getConversation(cid, await getToken());
      if (useChatStore.getState().conversationId === cid) {
        useChatStore.getState().setMessages(mapMessages(conv.messages));
      }
    } catch {
      /* keep the optimistic view */
    }
  }, [getToken]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || useChatStore.getState().runId) return;

      const s = useChatStore.getState();
      const ready = s.pendingAttachments.filter((a) => a.status === "ready");
      s.addMessage({
        id: crypto.randomUUID(),
        role: "user",
        content: message,
        attachments: ready.map((a) => ({ filename: a.filename, kind: a.kind })),
      });
      const pendingId = crypto.randomUUID();
      s.addMessage({ id: pendingId, role: "assistant", content: "", pending: true });
      s.setActiveAgents([]);
      s.setPlan([]);
      s.setTurnGuardrail(null);
      s.clearPendingAttachments();

      const token = await getToken();
      const existingCid = useChatStore.getState().conversationId;
      const model = useChatStore.getState().model;
      const pendingProjectId = useChatStore.getState().pendingProjectId;

      try {
        const { run_id, conversation_id } = await postChat(
          message,
          existingCid,
          token,
          existingCid ? null : (pendingProjectId ?? projectId),
          model,
          ready.map((a) => a.id),
        );
        s.setRunId(run_id);
        s.setConversationId(conversation_id);
        s.setPendingProjectId(null);
        if (!existingCid) {
          qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
          const newProj = pendingProjectId ?? projectId;
          if (newProj) qc.invalidateQueries({ queryKey: ["project", newProj] });
          router.replace(`/chat/${conversation_id}`);
        }
        await consumeStream(conversation_id, run_id, pendingId);
        void refreshMessages();
      } catch (err) {
        s.appendToken(
          pendingId,
          `\n\n⚠️ ${err instanceof Error ? err.message : "Something went wrong"}`,
        );
        s.setMessagePending(pendingId, false);
      } finally {
        s.setRunId(null);
        s.setActiveAgents([]);
        qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
        qc.invalidateQueries({ queryKey: ["usage"] });
      }
    },
    [getToken, router, qc, projectId, consumeStream, refreshMessages],
  );

  /** Regenerate a Genie reply, or retry / edit one of the user's messages.
   *  Everything after the target is discarded and the turn re-runs. */
  const regenerate = useCallback(
    async (fromMessageId: string, edit?: string) => {
      const s = useChatStore.getState();
      if (s.runId) return;
      const cid = s.conversationId;
      const target = s.messages.find((m) => m.id === fromMessageId);
      if (!cid || !target) return;

      if (target.role === "assistant") {
        s.truncateAfter(fromMessageId, { inclusive: true });
      } else {
        if (edit != null) s.updateMessageContent(fromMessageId, edit.trim());
        s.truncateAfter(fromMessageId);
      }
      const pendingId = crypto.randomUUID();
      s.addMessage({ id: pendingId, role: "assistant", content: "", pending: true });
      s.setActiveAgents([]);
      s.setPlan([]);
      s.setTurnGuardrail(null);

      try {
        const { run_id } = await regenerateChat(
          cid,
          fromMessageId,
          edit != null ? edit.trim() : null,
          await getToken(),
        );
        s.setRunId(run_id);
        await consumeStream(cid, run_id, pendingId);
        void refreshMessages();
      } catch (err) {
        s.appendToken(
          pendingId,
          `\n\n⚠️ ${err instanceof Error ? err.message : "Something went wrong"}`,
        );
        s.setMessagePending(pendingId, false);
      } finally {
        s.setRunId(null);
        s.setActiveAgents([]);
        qc.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
        qc.invalidateQueries({ queryKey: ["usage"] });
      }
    },
    [getToken, qc, consumeStream, refreshMessages],
  );

  const voteMessage = useCallback(
    async (messageId: string, vote: "up" | "down") => {
      const s = useChatStore.getState();
      const cur = s.messages.find((m) => m.id === messageId)?.feedback ?? null;
      const next = cur === vote ? null : vote;
      s.setMessageFeedback(messageId, next);
      try {
        await sendMessageFeedback(messageId, next, await getToken());
      } catch {
        s.setMessageFeedback(messageId, cur); // revert
      }
    },
    [getToken],
  );

  return {
    messages: store.messages,
    isStreaming: store.runId !== null,
    project: store.project,
    title: store.conversationTitle,
    send,
    regenerate,
    voteMessage,
  };
}
