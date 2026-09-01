"use client";

import { FileText, Loader2, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDeleteAttachment } from "@/hooks/useAttachments";
import { useChatStore } from "@/store/chatStore";

/** Staged attachments, shown inside the composer above the textarea. */
export function AttachmentChips() {
  const pending = useChatStore((s) => s.pendingAttachments);
  const removeLocal = useChatStore((s) => s.removePendingAttachment);
  const del = useDeleteAttachment();

  if (pending.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1.5 px-3 pt-3">
      {pending.map((a) => (
        <span
          key={a.id}
          className={cn(
            "inline-flex max-w-[220px] items-center gap-1.5 rounded-md border px-2 py-1 text-xs",
            a.status === "error"
              ? "border-red-400/40 bg-red-400/10 text-red-500"
              : "border-border bg-muted text-foreground",
          )}
        >
          {a.status === "uploading" ? (
            <Loader2 className="h-3 w-3 shrink-0 animate-spin" />
          ) : (
            <FileText className="h-3 w-3 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate">{a.filename}</span>
          {a.status === "error" && <span className="shrink-0">· failed</span>}
          <button
            type="button"
            aria-label={`Remove ${a.filename}`}
            onClick={() =>
              a.status === "ready" ? void del(a.id) : removeLocal(a.id)
            }
            className="shrink-0 rounded-sm opacity-60 hover:opacity-100"
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  );
}
