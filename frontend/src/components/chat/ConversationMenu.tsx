"use client";

import { useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronRight,
  EyeOff,
  FolderKanban,
  MoreVertical,
  Pencil,
  Pin,
  PinOff,
  Trash2,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  useDeleteConversation,
  usePatchConversation,
} from "@/hooks/useConversations";
import { useProjects } from "@/hooks/useProjects";

export interface ConversationMenuTarget {
  id: string;
  title: string | null;
  pinned: boolean;
  unread: boolean;
  projectId: string | null;
}

/** The ⋯ dropdown shared by the sidebar rows and the chat header. */
export function ConversationMenu({
  conversation,
  onRename,
  onDeleted,
  onLocalChange,
  align = "left",
  trigger,
}: {
  conversation: ConversationMenuTarget;
  onRename: () => void;
  onDeleted?: () => void;
  onLocalChange?: (patch: Partial<ConversationMenuTarget>) => void;
  align?: "left" | "right";
  trigger?: React.ReactNode;
}) {
  const { data: projects } = useProjects();
  const patch = usePatchConversation();
  const del = useDeleteConversation();

  const [open, setOpen] = useState(false);
  const [projOpen, setProjOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

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

  const run = (body: Parameters<typeof patch.mutate>[0]["body"], local: Partial<ConversationMenuTarget>) => {
    setOpen(false);
    setProjOpen(false);
    onLocalChange?.(local);
    patch.mutate({ id: conversation.id, body });
  };

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        aria-label="Conversation options"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((v) => !v);
        }}
        className={cn(
          !trigger &&
            "grid h-6 w-6 place-items-center rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground",
        )}
      >
        {trigger ?? <MoreVertical className="h-3.5 w-3.5" />}
      </button>

      {open && (
        <div
          className={cn(
            "absolute top-full z-50 mt-1 w-52 rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-xl ring-1 ring-black/5",
            align === "right" ? "right-0" : "left-0",
          )}
          onClick={(e) => e.stopPropagation()}
        >
          <MenuItem
            icon={conversation.pinned ? PinOff : Pin}
            onClick={() =>
              run({ pinned: !conversation.pinned }, { pinned: !conversation.pinned })
            }
          >
            {conversation.pinned ? "Unpin" : "Pin"}
          </MenuItem>
          <MenuItem
            icon={EyeOff}
            onClick={() =>
              run({ unread: !conversation.unread }, { unread: !conversation.unread })
            }
          >
            {conversation.unread ? "Mark as read" : "Mark as unread"}
          </MenuItem>
          <MenuItem
            icon={Pencil}
            onClick={() => {
              setOpen(false);
              onRename();
            }}
          >
            Rename
          </MenuItem>

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
              <ul className="mt-1 max-h-56 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-lg">
                {conversation.projectId && (
                  <li>
                    <button
                      type="button"
                      onClick={() => run({ project_id: null }, { projectId: null })}
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
                      onClick={() =>
                        run({ project_id: p.id }, { projectId: p.id })
                      }
                      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent"
                    >
                      <Check
                        className={cn(
                          "h-3.5 w-3.5 shrink-0",
                          p.id === conversation.projectId
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
          <MenuItem
            icon={Trash2}
            danger
            onClick={() => {
              setOpen(false);
              if (!window.confirm("Delete this conversation? This cannot be undone."))
                return;
              del.mutate(conversation.id, { onSuccess: onDeleted });
            }}
          >
            Delete
          </MenuItem>
        </div>
      )}
    </div>
  );
}

function MenuItem({
  icon: Icon,
  children,
  onClick,
  danger,
}: {
  icon: typeof Pin;
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm",
        danger ? "text-red-500 hover:bg-red-500/10" : "hover:bg-accent",
      )}
    >
      <Icon className={cn("h-3.5 w-3.5", !danger && "text-muted-foreground")} />
      {children}
    </button>
  );
}
