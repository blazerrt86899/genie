"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Check,
  ChevronDown,
  ChevronRight,
  FolderKanban,
  Pencil,
  Trash2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useDeleteConversation,
  usePatchConversation,
} from "@/hooks/useConversations";
import { useProjects } from "@/hooks/useProjects";
import { useChatStore, type ProjectRef } from "@/store/chatStore";

export function ChatHeader({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const title = useChatStore((s) => s.conversationTitle);
  const project = useChatStore((s) => s.project);
  const setTitle = useChatStore((s) => s.setConversationTitle);
  const setProject = useChatStore((s) => s.setProject);
  const reset = useChatStore((s) => s.reset);

  const { data: projects } = useProjects();
  const patch = usePatchConversation();
  const del = useDeleteConversation();

  const [open, setOpen] = useState(false);
  const [projOpen, setProjOpen] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
        setProjOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const label = title || "New chat";

  function startRename() {
    setDraft(title || "");
    setRenaming(true);
    setOpen(false);
  }
  function commitRename() {
    const next = draft.trim();
    setRenaming(false);
    if (next && next !== title) {
      setTitle(next);
      patch.mutate({ id: conversationId, body: { title: next } });
    }
  }
  function moveTo(p: ProjectRef | null) {
    setOpen(false);
    setProjOpen(false);
    setProject(p);
    patch.mutate({
      id: conversationId,
      body: { project_id: p ? p.id : null },
    });
  }
  function remove() {
    setOpen(false);
    if (!window.confirm(`Delete "${label}"? This cannot be undone.`)) return;
    del.mutate(conversationId, {
      onSuccess: () => {
        reset();
        router.push("/chat");
      },
    });
  }

  return (
    <div className="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-border bg-background/80 px-4 py-2 backdrop-blur sm:px-6">
      <div ref={menuRef} className="relative flex min-w-0 items-center gap-2">
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
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex min-w-0 items-center gap-1 rounded-md px-1.5 py-1 text-sm font-medium hover:bg-accent"
          >
            <span className="truncate">{label}</span>
            <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-60" />
          </button>
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

        {open && (
          <div className="absolute left-0 top-full z-30 mt-1.5 w-56 rounded-lg border border-border bg-card p-1 shadow-lg">
            <button
              type="button"
              onClick={startRename}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
            >
              <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
              Rename
            </button>

            <div className="relative">
              <button
                type="button"
                onClick={() => setProjOpen((v) => !v)}
                className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
              >
                <FolderKanban className="h-3.5 w-3.5 text-muted-foreground" />
                Add to project
                <ChevronRight
                  className={cn(
                    "ml-auto h-3.5 w-3.5 opacity-60 transition-transform",
                    projOpen && "rotate-90",
                  )}
                />
              </button>
              {projOpen && (
                <ul className="mt-1 max-h-60 overflow-y-auto rounded-md border border-border bg-background p-1">
                  {project && (
                    <li>
                      <button
                        type="button"
                        onClick={() => moveTo(null)}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent"
                      >
                        <X className="h-3.5 w-3.5" />
                        Remove from project
                      </button>
                    </li>
                  )}
                  {(projects ?? []).map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => moveTo({ id: p.id, name: p.name })}
                        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                      >
                        <Check
                          className={cn(
                            "h-3.5 w-3.5 shrink-0",
                            p.id === project?.id
                              ? "text-brand opacity-100"
                              : "opacity-0",
                          )}
                        />
                        <span className="truncate">{p.name}</span>
                      </button>
                    </li>
                  ))}
                  {(projects ?? []).length === 0 && (
                    <li className="px-2 py-1.5 text-xs text-muted-foreground">
                      No projects yet
                    </li>
                  )}
                </ul>
              )}
            </div>

            <div className="my-1 h-px bg-border" />
            <button
              type="button"
              onClick={remove}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-red-500 hover:bg-red-500/10"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
