"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { FolderKanban, SendHorizontal, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/useChat";
import { useProjects } from "@/hooks/useProjects";
import { useScrollShadow } from "@/hooks/useScrollShadow";
import { cn } from "@/lib/utils";
import { useChatStore } from "@/store/chatStore";
import { Message } from "./Message";
import { AgentActivity } from "./AgentActivity";
import { PlanStrip } from "./PlanStrip";
import { GreetingHeadline } from "./GreetingHeadline";
import { ModelPicker } from "./ModelPicker";
import { PlusMenu } from "./PlusMenu";
import { AttachmentChips } from "./AttachmentChips";
import { ChatHeader } from "./ChatHeader";
import { AuroraBackdrop } from "./AuroraBackdrop";

const MAX_COMPOSER_HEIGHT = 208; // px — ~8 lines, then scroll

function Composer({
  input,
  setInput,
  onSend,
  isStreaming,
  autoFocus,
  conversationId,
}: {
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  isStreaming: boolean;
  autoFocus?: boolean;
  conversationId?: string;
}) {
  const taRef = useRef<HTMLTextAreaElement>(null);

  // Auto-grow the textarea with its content, up to a cap.
  useLayoutEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_COMPOSER_HEIGHT)}px`;
  }, [input]);

  return (
    <div className="rounded-2xl border border-input bg-background shadow-sm transition-colors focus-within:border-brand/40 focus-within:ring-2 focus-within:ring-ring">
      <AttachmentChips />
      <textarea
        ref={taRef}
        // eslint-disable-next-line jsx-a11y/no-autofocus
        autoFocus={autoFocus}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        rows={2}
        placeholder="Message Genie…"
        disabled={isStreaming}
        className="block max-h-52 min-h-[64px] w-full resize-none bg-transparent px-4 pt-3.5 text-[15px] leading-relaxed outline-none placeholder:text-muted-foreground/70 disabled:opacity-60"
      />
      <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-2">
        <PlusMenu conversationId={conversationId} disabled={isStreaming} />
        <div className="flex items-center gap-1.5">
          <ModelPicker disabled={isStreaming} />
          <Button
            variant="brand"
            size="icon"
            onClick={onSend}
            disabled={isStreaming || !input.trim()}
            aria-label="Send"
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ChatView({ conversationId }: { conversationId?: string }) {
  const projectParam = useSearchParams().get("project");
  const { messages, send, regenerate, voteMessage, isStreaming, project } =
    useChat(conversationId, projectParam);
  const { data: projects } = useProjects();
  const { user } = useUser();
  const userName =
    user?.firstName || user?.username || user?.fullName || "You";
  const activeAgents = useChatStore((s) => s.activeAgents);
  const turnGuardrail = useChatStore((s) => s.turnGuardrail);
  const pendingAttachments = useChatStore((s) => s.pendingAttachments);
  const pendingProjectId = useChatStore((s) => s.pendingProjectId);
  const storedConversationId = useChatStore((s) => s.conversationId);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const {
    ref: scrollRef,
    onScroll,
    atTop,
    atBottom,
  } = useScrollShadow<HTMLDivElement>();

  const uploading = pendingAttachments.some((a) => a.status === "uploading");

  // Active agents whose message hasn't started yet → shown at the list tail.
  const pendingAgents = useMemo(() => {
    const claimed = new Set(messages.flatMap((m) => m.agents ?? []));
    return activeAgents.filter((a) => !claimed.has(a));
  }, [activeAgents, messages]);

  // The chat's project: from the loaded conversation, the "+ → Add to project"
  // pick on a new chat, else the ?project= param.
  const activeProject = useMemo(() => {
    if (project) return project;
    const pid = pendingProjectId ?? projectParam;
    if (pid && projects) {
      const p = projects.find((x) => x.id === pid);
      if (p) return { id: p.id, name: p.name };
    }
    return null;
  }, [project, pendingProjectId, projectParam, projects]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    const text = input.trim();
    if (!text || isStreaming || uploading) return;
    setInput("");
    void send(text);
  }

  const isEmpty = messages.length === 0;
  const cid = conversationId ?? storedConversationId ?? undefined;

  return (
    <div className="relative isolate flex h-full flex-col">
      <AuroraBackdrop subtle={!isEmpty} />

      {!isEmpty && cid && (
        <ChatHeader conversationId={cid} elevated={!atTop} />
      )}

      {/* Fresh chat in a project (no header yet) still shows the project chip */}
      {isEmpty && activeProject && (
        <div className="border-b border-border px-4 py-2 sm:px-6">
          <Link
            href={`/projects/${activeProject.id}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-brand/30 bg-brand/10 px-2.5 py-0.5 text-xs font-medium text-brand hover:bg-brand/20"
          >
            <FolderKanban className="h-3 w-3" />
            {activeProject.name}
          </Link>
        </div>
      )}

      <PlanStrip />

      {isEmpty ? (
        /* Centered welcome — greeting + composer, like a fresh chat window */
        <div className="flex flex-1 flex-col items-center justify-center gap-8 overflow-y-auto p-6">
          {activeProject ? (
            <div className="text-center">
              <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
                New chat in {activeProject.name}
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Genie will follow this project&apos;s instructions here.
              </p>
            </div>
          ) : (
            <GreetingHeadline />
          )}
          <div className="w-full max-w-2xl">
            <Composer
              input={input}
              setInput={setInput}
              onSend={handleSend}
              isStreaming={isStreaming}
              conversationId={conversationId}
              autoFocus
            />
          </div>
        </div>
      ) : (
        <>
          <div
            ref={scrollRef}
            onScroll={onScroll}
            className="flex flex-1 flex-col gap-8 overflow-y-auto p-4 py-6 sm:px-6"
          >
            {messages.map((m) => (
              <Message
                key={m.id}
                message={m}
                userName={userName}
                activeAgents={activeAgents}
                isStreaming={isStreaming}
                onRegenerate={regenerate}
                onRetry={regenerate}
                onEdit={regenerate}
                onVote={voteMessage}
              />
            ))}
            {pendingAgents.length > 0 && <AgentActivity agents={pendingAgents} />}
            <div ref={endRef} />
          </div>

          <div
            className={cn(
              "border-t transition-shadow",
              atBottom
                ? "border-border"
                : "border-transparent shadow-[0_-6px_16px_-10px_rgba(0,0,0,0.5)]",
            )}
          >
            {turnGuardrail && (
              <div className="mx-3 mt-2 flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[12px] text-amber-700 dark:text-amber-300 sm:mx-6">
                <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>{turnGuardrail}</span>
              </div>
            )}
            <div className="p-3 sm:px-6">
              <Composer
                input={input}
                setInput={setInput}
                onSend={handleSend}
                isStreaming={isStreaming}
                conversationId={conversationId}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
