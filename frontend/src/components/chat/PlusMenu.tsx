"use client";

import { useEffect, useRef, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ChevronRight,
  FolderKanban,
  Paperclip,
  Plus,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { patchConversation } from "@/lib/api";
import { useProjects } from "@/hooks/useProjects";
import { useUploadAttachment } from "@/hooks/useAttachments";
import { useChatStore } from "@/store/chatStore";

const ACCEPT = ".pdf,.txt,.md";

export function PlusMenu({
  conversationId,
  disabled,
}: {
  conversationId?: string;
  disabled?: boolean;
}) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  const { data: projects } = useProjects();
  const upload = useUploadAttachment();
  const project = useChatStore((s) => s.project);
  const pendingProjectId = useChatStore((s) => s.pendingProjectId);
  const setProject = useChatStore((s) => s.setProject);
  const setPendingProjectId = useChatStore((s) => s.setPendingProjectId);

  const [open, setOpen] = useState(false);
  const [projOpen, setProjOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setProjOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const currentProjectId = project?.id ?? pendingProjectId ?? null;

  async function moveTo(pid: string | null) {
    setOpen(false);
    setProjOpen(false);
    if (conversationId) {
      const updated = await patchConversation(
        conversationId,
        { project_id: pid },
        await getToken(),
      );
      const p = pid ? projects?.find((x) => x.id === pid) : null;
      setProject(p ? { id: p.id, name: p.name } : null);
      qc.invalidateQueries({ queryKey: ["conversations"] });
      qc.invalidateQueries({ queryKey: ["projects"] });
      if (updated.project_id) {
        qc.invalidateQueries({ queryKey: ["project", updated.project_id] });
      }
    } else {
      setPendingProjectId(pid);
    }
  }

  return (
    <div ref={ref} className="relative">
      <input
        ref={fileRef}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          files.forEach((f) => void upload(f));
          e.target.value = "";
          setOpen(false);
        }}
      />

      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        aria-label="Add files or move to a project"
        className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
      >
        <Plus className="h-4 w-4" />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-20 mt-1.5 w-56 rounded-lg border border-border bg-card p-1 shadow-lg">
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
          >
            <Paperclip className="h-4 w-4 text-muted-foreground" />
            Add files
            <span className="ml-auto text-[11px] text-muted-foreground/70">
              pdf · txt · md
            </span>
          </button>

          <div className="relative">
            <button
              type="button"
              onClick={() => setProjOpen((v) => !v)}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
            >
              <FolderKanban className="h-4 w-4 text-muted-foreground" />
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
                {currentProjectId && (
                  <li>
                    <button
                      type="button"
                      onClick={() => void moveTo(null)}
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
                      onClick={() => void moveTo(p.id)}
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                    >
                      <Check
                        className={cn(
                          "h-3.5 w-3.5 shrink-0",
                          p.id === currentProjectId
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
        </div>
      )}
    </div>
  );
}
