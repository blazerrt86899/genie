"use client";

import { useState } from "react";
import {
  Check,
  Copy,
  Pencil,
  RotateCw,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/store/chatStore";

function fmtDate(iso: string) {
  const d = new Date(iso);
  return {
    short: d.toLocaleDateString(undefined, { month: "short", day: "numeric" }),
    full: d.toLocaleString(),
  };
}

function IconButton({
  label,
  onClick,
  disabled,
  active,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  active?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "grid h-6 w-6 place-items-center rounded transition-colors disabled:opacity-40",
        active
          ? "text-brand"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

/** The subtle action row under every message (like Claude / ChatGPT). */
export function MessageActions({
  message,
  isStreaming,
  onCopy,
  onRegenerate,
  onRetry,
  onEdit,
  onVote,
}: {
  message: ChatMessage;
  isStreaming: boolean;
  onCopy: () => void;
  onRegenerate?: () => void; // assistant
  onRetry?: () => void; // user
  onEdit?: () => void; // user
  onVote?: (vote: "up" | "down") => void; // assistant
}) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const date = message.createdAt ? fmtDate(message.createdAt) : null;

  function copy() {
    onCopy();
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
  }

  const dateEl = date ? (
    <span
      className="select-none text-[11px] text-muted-foreground/70"
      title={date.full}
    >
      {date.short}
    </span>
  ) : null;

  const copyBtn = (
    <IconButton label="Copy" onClick={copy}>
      {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
    </IconButton>
  );

  return (
    <div
      className={cn(
        "mt-1 flex items-center gap-0.5",
        isUser ? "justify-end pr-1" : "pl-0",
      )}
    >
      {isUser ? (
        <>
          {dateEl}
          {onRetry && (
            <IconButton label="Retry" onClick={onRetry} disabled={isStreaming}>
              <RotateCw className="h-3.5 w-3.5" />
            </IconButton>
          )}
          {onEdit && (
            <IconButton label="Edit" onClick={onEdit} disabled={isStreaming}>
              <Pencil className="h-3.5 w-3.5" />
            </IconButton>
          )}
          {copyBtn}
        </>
      ) : (
        <>
          {copyBtn}
          {onVote && (
            <>
              <IconButton
                label="Good response"
                onClick={() => onVote("up")}
                disabled={isStreaming}
                active={message.feedback === "up"}
              >
                <ThumbsUp
                  className="h-3.5 w-3.5"
                  fill={message.feedback === "up" ? "currentColor" : "none"}
                />
              </IconButton>
              <IconButton
                label="Bad response"
                onClick={() => onVote("down")}
                disabled={isStreaming}
                active={message.feedback === "down"}
              >
                <ThumbsDown
                  className="h-3.5 w-3.5"
                  fill={message.feedback === "down" ? "currentColor" : "none"}
                />
              </IconButton>
            </>
          )}
          {onRegenerate && (
            <IconButton
              label="Regenerate"
              onClick={onRegenerate}
              disabled={isStreaming}
            >
              <RotateCw className="h-3.5 w-3.5" />
            </IconButton>
          )}
          {dateEl && <span className="ml-1">{dateEl}</span>}
        </>
      )}
    </div>
  );
}
