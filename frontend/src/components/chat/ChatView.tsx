"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useUser } from "@clerk/nextjs";
import { FolderKanban, SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/useChat";
import { useProjects } from "@/hooks/useProjects";
import { useChatStore } from "@/store/chatStore";
import { Message } from "./Message";
import { AgentActivity } from "./AgentActivity";
import { PlanStrip } from "./PlanStrip";
import { GreetingHeadline } from "./GreetingHeadline";
import { ModelPicker } from "./ModelPicker";

const MAX_COMPOSER_HEIGHT = 208; // px — ~8 lines, then scroll

function Composer({
  input,
  setInput,
  onSend,
  isStreaming,
  autoFocus,
}: {
  input: string;
  setInput: (v: string) => void;
  onSend: () => void;
  isStreaming: boolean;
  autoFocus?: boolean;
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
      <div className="flex items-center justify-between gap-2 px-3 pb-3 pt-1.5">
        <div className="flex min-w-0 items-center gap-1.5">
          <ModelPicker disabled={isStreaming} />
          <span className="hidden select-none text-xs text-muted-foreground/70 sm:inline">
            <kbd className="font-sans">Enter</kbd> to send ·{" "}
            <kbd className="font-sans">Shift</kbd>+
            <kbd className="font-sans">Enter</kbd> for a new line
          </span>
        </div>
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
  );
}

export function ChatView({ conversationId }: { conversationId?: string }) {
  const projectParam = useSearchParams().get("project");
  const { messages, send, isStreaming, project } = useChat(
    conversationId,
    projectParam,
  );
  const { data: projects } = useProjects();
  const { user } = useUser();
  const userName =
    user?.firstName || user?.username || user?.fullName || "You";
  const activeAgents = useChatStore((s) => s.activeAgents);
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  // Active agents whose message hasn't started yet → shown at the list tail.
  const pendingAgents = useMemo(() => {
    const claimed = new Set(messages.flatMap((m) => m.agents ?? []));
    return activeAgents.filter((a) => !claimed.has(a));
  }, [activeAgents, messages]);

  // The chat's project: from the loaded conversation, else the ?project= param.
  const activeProject = useMemo(() => {
    if (project) return project;
    if (projectParam && projects) {
      const p = projects.find((x) => x.id === projectParam);
      if (p) return { id: p.id, name: p.name };
    }
    return null;
  }, [project, projectParam, projects]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    void send(text);
  }

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {activeProject && (
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
              autoFocus
            />
            <p className="mt-2 text-center text-xs text-muted-foreground">
              Genie routes your message to the right specialists and streams back
              one answer.
            </p>
          </div>
        </div>
      ) : (
        <>
          <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-4 sm:px-6">
            {messages.map((m) => (
              <Message
                key={m.id}
                message={m}
                userName={userName}
                activeAgents={activeAgents}
              />
            ))}
            {pendingAgents.length > 0 && <AgentActivity agents={pendingAgents} />}
            <div ref={endRef} />
          </div>

          <div className="border-t border-border">
            <div className="p-3 sm:px-6">
              <Composer
                input={input}
                setInput={setInput}
                onSend={handleSend}
                isStreaming={isStreaming}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );
}
