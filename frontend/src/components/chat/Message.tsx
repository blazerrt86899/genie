import { CheckSquare, FileText, Globe, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/store/chatStore";
import { StreamingDot } from "./StreamingDot";
import { SourceCards } from "./SourceCards";
import { Markdown } from "./Markdown";

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
}: {
  message: ChatMessage;
  userName?: string;
  activeAgents?: string[];
}) {
  const isUser = message.role === "user";

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
        <div className="max-w-[80%] whitespace-pre-wrap rounded-2xl rounded-tr-sm bg-muted px-3.5 py-2.5 text-[15px] leading-relaxed text-foreground">
          {message.content}
        </div>
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

      {!isUser && message.sources && message.sources.length > 0 && (
        <SourceCards sources={message.sources} />
      )}
    </div>
  );
}
