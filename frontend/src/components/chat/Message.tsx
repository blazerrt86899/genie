import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/store/chatStore";
import { StreamingDot } from "./StreamingDot";

export function Message({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[75%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted",
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
