"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FolderKanban, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import { relativeDay } from "@/lib/date";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import {
  useConversations,
  useSearchConversations,
} from "@/hooks/useConversations";
import type { ConversationSearchResult } from "@/lib/api";

export function SearchChatsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const [raw, setRaw] = useState("");
  const debounced = useDebouncedValue(raw, 180);
  const searching = debounced.trim().length >= 2;

  const { data: recent } = useConversations();
  const search = useSearchConversations(debounced);

  const rows = useMemo<ConversationSearchResult[]>(() => {
    if (searching) return search.data ?? [];
    return (recent ?? []).slice(0, 8).map((c) => ({ ...c, snippet: null }));
  }, [searching, search.data, recent]);

  const [active, setActive] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => setActive(0), [debounced, searching]);
  useEffect(() => {
    if (!open) setRaw("");
  }, [open]);
  useEffect(() => {
    listRef.current
      ?.querySelector<HTMLElement>(`[data-i="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active]);

  if (!open) return null;

  const select = (id: string) => {
    onClose();
    router.push(`/chat/${id}`);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, rows.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (rows[active]) select(rows[active].id);
    } else if (e.key === "Escape") {
      onClose();
    }
  };

  const empty =
    searching && !search.isPending && (search.data?.length ?? 0) === 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-[12vh] backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Search chats"
        className="w-full max-w-xl overflow-hidden rounded-3xl border border-border bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-3 border-b border-border px-4">
          <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
          {/* eslint-disable-next-line jsx-a11y/no-autofocus */}
          <input
            autoFocus
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
            placeholder="Search chats"
            className="h-14 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground/70"
          />
        </div>

        <div ref={listRef} className="max-h-[55vh] overflow-y-auto p-2">
          {!searching && (
            <p className="px-2 pb-1 pt-2 text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
              Recent
            </p>
          )}

          {empty ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              No chats match &ldquo;{debounced.trim()}&rdquo;
            </p>
          ) : rows.length === 0 ? (
            <p className="px-3 py-6 text-center text-sm text-muted-foreground">
              {searching ? "Searching…" : "No conversations yet."}
            </p>
          ) : (
            rows.map((c, i) => (
              <button
                key={c.id}
                data-i={i}
                type="button"
                onMouseMove={() => setActive(i)}
                onClick={() => select(c.id)}
                className={cn(
                  "flex w-full items-center gap-3 rounded-full px-3.5 py-2 text-left",
                  i === active && "bg-accent",
                )}
              >
                {c.project_id !== null && (
                  <FolderKanban className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" />
                )}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-foreground">
                    {c.title || "New chat"}
                  </span>
                  {c.snippet && (
                    <span className="block truncate text-xs text-muted-foreground">
                      {c.snippet}
                    </span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground/70">
                  {relativeDay(c.last_message_at ?? c.created_at)}
                </span>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
