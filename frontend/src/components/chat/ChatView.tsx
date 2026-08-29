"use client";

import { useEffect, useRef, useState } from "react";
import { useUser } from "@clerk/nextjs";
import { SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChat } from "@/hooks/useChat";
import { Message } from "./Message";
import { AgentActivity } from "./AgentActivity";

export function ChatView({ conversationId }: { conversationId?: string }) {
  const { messages, send, isStreaming } = useChat(conversationId);
  const { user } = useUser();
  const userName =
    user?.firstName || user?.username || user?.fullName || "You";
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  function handleSend() {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    void send(text);
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-4 sm:px-6">
        {messages.length === 0 && (
          <div className="m-auto max-w-md text-center">
            <h1 className="text-xl font-semibold">What can Genie do for you?</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              Ask anything — Genie routes it to the right specialists and streams
              back one answer.
            </p>
          </div>
        )}
        {messages.map((m) => (
          <Message key={m.id} message={m} userName={userName} />
        ))}
        <div ref={endRef} />
      </div>

      <AgentActivity />

      <div className="border-t border-border">
        <div className="flex items-end gap-2 p-3 sm:px-6">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            rows={1}
            placeholder="Message Genie…"
            disabled={isStreaming}
            className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring disabled:opacity-60"
          />
          <Button
            variant="brand"
            size="icon"
            onClick={handleSend}
            disabled={isStreaming || !input.trim()}
            aria-label="Send"
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
