"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ChevronDown, FolderKanban, Pin, Share } from "lucide-react";
import {
  ConversationMenu,
  type ConversationMenuTarget,
} from "./ConversationMenu";
import { ShareChatModal } from "./ShareChatModal";
import { usePatchConversation } from "@/hooks/useConversations";
import { useChatStore } from "@/store/chatStore";
import { cn } from "@/lib/utils";

export function ChatHeader({
  conversationId,
  elevated = false,
}: {
  conversationId: string;
  elevated?: boolean;
}) {
  const router = useRouter();
  const title = useChatStore((s) => s.conversationTitle);
  const project = useChatStore((s) => s.project);
  const pinned = useChatStore((s) => s.conversationPinned);
  const unread = useChatStore((s) => s.conversationUnread);
  const setTitle = useChatStore((s) => s.setConversationTitle);
  const setProject = useChatStore((s) => s.setProject);
  const setFlags = useChatStore((s) => s.setConversationFlags);
  const reset = useChatStore((s) => s.reset);
  const patch = usePatchConversation();

  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const [shareOpen, setShareOpen] = useState(false);

  const label = title || "New chat";
  const target: ConversationMenuTarget = {
    id: conversationId,
    title,
    pinned,
    unread,
    projectId: project?.id ?? null,
  };

  function commitRename() {
    const next = draft.trim();
    setRenaming(false);
    if (next && next !== title) {
      setTitle(next);
      patch.mutate({ id: conversationId, body: { title: next } });
    }
  }

  return (
    <div
      className={cn(
        "z-10 flex items-center justify-between gap-3 border-b bg-background px-4 py-2 transition-shadow sm:px-6",
        elevated
          ? "border-transparent shadow-[0_6px_16px_-10px_rgba(0,0,0,0.5)]"
          : "border-border",
      )}
    >
      <div className="flex min-w-0 items-center gap-2">
        {renaming ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") setRenaming(false);
            }}
            className="w-64 max-w-full rounded-md border border-input bg-background px-2 py-1 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        ) : (
          <ConversationMenu
            conversation={target}
            onRename={() => {
              setDraft(title || "");
              setRenaming(true);
            }}
            onDeleted={() => {
              reset();
              router.push("/chat");
            }}
            onLocalChange={(p) => {
              if (p.pinned !== undefined || p.unread !== undefined) setFlags(p);
              if (p.projectId !== undefined)
                setProject(
                  p.projectId
                    ? { id: p.projectId, name: project?.name ?? "Project" }
                    : null,
                );
            }}
            trigger={
              <span className="flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 text-sm font-medium text-foreground hover:bg-accent">
                {pinned && <Pin className="h-3 w-3 shrink-0 text-brand" />}
                <span className="truncate">{label}</span>
                <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
              </span>
            }
          />
        )}

        {project && (
          <Link
            href={`/projects/${project.id}`}
            className="hidden shrink-0 items-center gap-1 rounded-full border border-brand/30 bg-brand/10 px-2 py-0.5 text-xs font-medium text-brand hover:bg-brand/20 sm:inline-flex"
          >
            <FolderKanban className="h-3 w-3" />
            {project.name}
          </Link>
        )}
      </div>

      <button
        type="button"
        onClick={() => setShareOpen(true)}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
      >
        <Share className="h-3.5 w-3.5" />
        Share
      </button>

      <ShareChatModal
        conversationId={conversationId}
        open={shareOpen}
        onClose={() => setShareOpen(false)}
      />
    </div>
  );
}
