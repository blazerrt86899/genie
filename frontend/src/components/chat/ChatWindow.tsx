"use client";

import { useRef, useState } from "react";
import { SendHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChatStore } from "@/store/chatStore";
import { Message } from "./Message";
import { AgentActivity } from "./AgentActivity";

export function ChatWindow() {
  const { messages, addMessage } = useChatStore();
  const [input, setInput] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  function handleSend() {
    const text = input.trim();
    if (!text) return;
    addMessage({ id: crypto.randomUUID(), role: "user", content: text });
    // Phase 1: POST /chat -> SSE stream (see hooks/useChat.ts). Placeholder reply:
    addMessage({
      id: crypto.randomUUID(),
      role: "assistant",
      content:
        "The orchestration graph isn't wired yet — this is the Phase 1 chat shell.",
    });
    setInput("");
    requestAnimationFrame(() =>
      endRef.current?.scrollIntoView({ behavior: "smooth" }),
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <p className="mt-10 text-center text-sm text-muted-foreground">
            Ask Genie anything to get started.
          </p>
        )}
        {messages.map((m) => (
          <Message key={m.id} message={m} />
        ))}
        <div ref={endRef} />
      </div>

      <AgentActivity />

      <div className="flex items-end gap-2 border-t p-3">
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
          className="flex-1 resize-none rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <Button size="icon" onClick={handleSend} aria-label="Send">
          <SendHorizontal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
