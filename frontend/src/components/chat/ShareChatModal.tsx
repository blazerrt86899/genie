"use client";

import { useState } from "react";
import { Check, Globe, Lock } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  useConversationShare,
  useDisableShare,
  useEnableShare,
} from "@/hooks/useShareConversation";

export function ShareChatModal({
  conversationId,
  open,
  onClose,
}: {
  conversationId: string;
  open: boolean;
  onClose: () => void;
}) {
  const { data: share, isLoading } = useConversationShare(
    open ? conversationId : undefined,
  );
  const enable = useEnableShare(conversationId);
  const disable = useDisableShare(conversationId);
  const [copied, setCopied] = useState(false);

  const isPublic = !!share;
  const busy = enable.isPending || disable.isPending;
  const error = enable.error || disable.error;

  async function copy() {
    if (!share) return;
    try {
      await navigator.clipboard.writeText(share.url);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard blocked — the field is selectable as a fallback */
    }
  }

  return (
    <Modal open={open} onClose={onClose} title="Share chat">
      <p className="-mt-2 mb-4 text-sm text-muted-foreground">
        Future messages aren&apos;t included.
      </p>

      <div className="space-y-2">
        <OptionRow
          icon={Lock}
          label="Keep private"
          desc="Only you have access"
          active={!isPublic}
          disabled={busy || isLoading}
          onClick={() => {
            if (isPublic) disable.mutate();
          }}
        />
        <OptionRow
          icon={Globe}
          label="Create public link"
          desc="Anyone with the link can view"
          active={isPublic}
          disabled={busy || isLoading}
          onClick={() => {
            if (!isPublic) enable.mutate();
          }}
        />
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-500">
          {error instanceof Error ? error.message : "Something went wrong"}
        </p>
      )}

      {isPublic && share && (
        <div className="mt-4 flex items-center gap-2 rounded-xl border border-border bg-muted/50 p-2 pl-3">
          <input
            readOnly
            value={share.url}
            onFocus={(e) => e.currentTarget.select()}
            className="min-w-0 flex-1 bg-transparent text-sm text-muted-foreground outline-none"
          />
          <Button size="sm" onClick={copy} className="shrink-0">
            {copied ? "Copied" : "Copy link"}
          </Button>
        </div>
      )}
    </Modal>
  );
}

function OptionRow({
  icon: Icon,
  label,
  desc,
  active,
  disabled,
  onClick,
}: {
  icon: typeof Lock;
  label: string;
  desc: string;
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-3 rounded-xl border p-3 text-left transition-colors disabled:opacity-60",
        active
          ? "border-brand/40 bg-accent"
          : "border-border hover:bg-accent/60",
      )}
    >
      <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-medium text-foreground">{label}</span>
        <span className="block text-xs text-muted-foreground">{desc}</span>
      </span>
      {active && <Check className="h-4 w-4 shrink-0 text-brand" />}
    </button>
  );
}
