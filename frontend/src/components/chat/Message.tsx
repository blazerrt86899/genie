"use client";

import { useState } from "react";
import { CheckSquare, FileText, Globe, ShieldAlert, Sparkles, Zap } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/store/chatStore";
import { StreamingDot } from "./StreamingDot";
import { SourceCards } from "./SourceCards";
import { Markdown } from "./Markdown";
import { MessageActions } from "./MessageActions";

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "");
  return letters.join("") || "Y";
}

const AGENT_LABELS: Record<string, { icon: typeof Globe; live: string; done: string }> = {
  web_search: { icon: Globe, live: "Searching the web", done: "Searched the web" },
  kb_search: {
    icon: FileText,
    live: "Searching your knowledge base",
    done: "Searched your knowledge base",
  },
  greeting: { icon: Sparkles, live: "Greeting you", done: "Greeted you" },
  rag: { icon: Globe, live: "Reading your documents", done: "Read your documents" },
  task_creator: { icon: CheckSquare, live: "Updating your tasks", done: "Updated your tasks" },
  task_summary: { icon: CheckSquare, live: "Summarising the task", done: "Summarised the task" },
  cache: { icon: Zap, live: "Checking the cache", done: "Answered from cache" },
};

function AgentTrail({
  agents,
  activeAgents,
}: {
  agents: string[];
  activeAgents: string[];
}) {
  const items = [...new Set(agents)];
  if (items.length === 0) return null;

  return (
    <div className="mb-1 flex flex-wrap items-center gap-2 px-1">
      {items.map((agent) => {
        const meta = AGENT_LABELS[agent];
        const Icon = meta?.icon ?? Globe;
        const live = activeAgents.includes(agent);
        const label = meta ? (live ? meta.live : meta.done) : agent.replace(/_/g, " ");
        return (
          <span
            key={agent}
            className={cn(
              "inline-flex items-center gap-1.5 text-[11px] font-medium",
              live ? "text-brand" : "text-muted-foreground",
            )}
          >
            {live ? (
              <span className="relative flex h-1.5 w-1.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-75" />
                <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand" />
              </span>
            ) : (
              <Icon className="h-3 w-3" />
            )}
            {label}
            {live ? "…" : ""}
          </span>
        );
      })}
    </div>
  );
}

export function Message({
  message,
  userName = "You",
  activeAgents = [],
  isStreaming = false,
  onRegenerate,
  onRetry,
  onEdit,
  onVote,
}: {
  message: ChatMessage;
  userName?: string;
  activeAgents?: string[];
  isStreaming?: boolean;
  onRegenerate?: (id: string) => void;
  onRetry?: (id: string) => void;
  onEdit?: (id: string, text: string) => void;
  onVote?: (id: string, vote: "up" | "down") => void;
}) {
  const isUser = message.role === "user";
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content);

  const interactive = !!(onRegenerate || onRetry || onEdit || onVote);
  // Show the row for its actions, or (read-only, e.g. the public /share page)
  // just to carry the date.
  const showActions =
    !message.pending && !editing && (interactive || !!message.createdAt);

  function commitEdit() {
    const next = draft.trim();
    setEditing(false);
    if (next && next !== message.content) onEdit?.(message.id, next);
  }

  // Genie's messages blend into the page (no bubble, Claude-style); the user's
  // sit in a subtle right-aligned box.
  return (
    <div className={cn("flex flex-col gap-1.5", isUser ? "items-end" : "items-start")}>
      {!isUser && message.agents && message.agents.length > 0 && (
        <AgentTrail agents={message.agents} activeAgents={activeAgents} />
      )}

      {isUser && (
        <span className="select-none px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
          {initials(userName)}
        </span>
      )}

      {isUser && message.attachments && message.attachments.length > 0 && (
        <div className="flex flex-wrap justify-end gap-1.5 px-1">
          {message.attachments.map((a, i) => (
            <span
              key={i}
              className="inline-flex items-center gap-1 rounded-md border border-border bg-muted px-2 py-1 text-xs text-foreground"
            >
              <FileText className="h-3 w-3 text-muted-foreground" />
              {a.filename}
            </span>
          ))}
        </div>
      )}

      {isUser ? (
        editing ? (
          <div className="w-full max-w-[80%]">
            <textarea
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) commitEdit();
                if (e.key === "Escape") setEditing(false);
              }}
              rows={Math.min(8, draft.split("\n").length + 1)}
              className="w-full resize-none rounded-2xl border border-input bg-background px-3.5 py-2.5 text-[15px] leading-relaxed outline-none focus:ring-2 focus:ring-ring"
            />
            <div className="mt-1.5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setEditing(false)}
                className="rounded-md px-2.5 py-1 text-xs text-muted-foreground hover:bg-accent"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={commitEdit}
                className="rounded-md bg-brand px-2.5 py-1 text-xs font-medium text-brand-foreground hover:opacity-90"
              >
                Save &amp; submit
              </button>
            </div>
          </div>
        ) : (
          <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-muted px-3.5 py-2.5 text-[15px] leading-relaxed text-foreground">
            {message.content}
          </div>
        )
      ) : (
        <div className="w-full leading-relaxed text-foreground">
          {message.content ? (
            <Markdown>{message.content}</Markdown>
          ) : null}
          {message.pending && (
            <span className="align-middle">
              <StreamingDot />
            </span>
          )}
        </div>
      )}

      {isUser && message.guardrail && message.guardrail.message && (
        <div className="mt-1 flex max-w-[80%] items-start gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-2.5 py-1.5 text-[12px] text-amber-700 dark:text-amber-300">
          <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{message.guardrail.message}</span>
        </div>
      )}

      {!isUser && message.sources && message.sources.length > 0 && (
        <SourceCards sources={message.sources} />
      )}

      {showActions && (
        <MessageActions
          message={message}
          isStreaming={isStreaming}
          onCopy={() => navigator.clipboard.writeText(message.content).catch(() => {})}
          onRegenerate={
            !isUser && onRegenerate ? () => onRegenerate(message.id) : undefined
          }
          onRetry={isUser && onRetry ? () => onRetry(message.id) : undefined}
          onEdit={
            isUser && onEdit
              ? () => {
                  setDraft(message.content);
                  setEditing(true);
                }
              : undefined
          }
          onVote={
            !isUser && onVote ? (v) => onVote(message.id, v) : undefined
          }
        />
      )}
    </div>
  );
}
