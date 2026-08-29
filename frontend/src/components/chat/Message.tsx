import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/store/chatStore";
import { StreamingDot } from "./StreamingDot";

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  const letters = parts.slice(0, 2).map((w) => w[0]?.toUpperCase() ?? "");
  return letters.join("") || "Y";
}

export function Message({
  message,
  userName = "You",
}: {
  message: ChatMessage;
  userName?: string;
}) {
  const isUser = message.role === "user";
  const name = isUser ? userName : "Genie";

  return (
    <div className={cn("flex flex-col gap-1.5", isUser ? "items-end" : "items-start")}>
      {/* sender label */}
      <div
        className={cn(
          "flex select-none items-center gap-2 px-1",
          isUser && "flex-row-reverse",
        )}
      >
        {isUser ? (
          <span className="grid h-5 w-5 place-items-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">
            {initials(userName)}
          </span>
        ) : (
          <span className="grid h-5 w-5 place-items-center rounded-md bg-gradient-to-br from-brand to-brand-2 text-brand-foreground shadow-sm shadow-brand/30">
            <Sparkles className="h-3 w-3" />
          </span>
        )}
        <span
          className={cn(
            "text-[11px] font-semibold uppercase tracking-[0.18em]",
            isUser
              ? "text-muted-foreground"
              : "bg-gradient-to-r from-brand to-brand-2 bg-clip-text text-transparent",
          )}
        >
          {name}
        </span>
      </div>

      {/* bubble */}
      <div
        className={cn(
          "max-w-[78%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-tr-sm bg-primary text-primary-foreground"
            : "rounded-tl-sm border border-border bg-muted",
        )}
      >
        {message.content}
        {message.pending && (
          <span className="ml-1 align-middle">
            <StreamingDot />
          </span>
        )}
      </div>
    </div>
  );
}
