"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useChatStore } from "@/store/chatStore";

const LABELS: Record<string, string> = {
  greeting: "Greeting you",
  web_search: "Searching the web",
  rag: "Reading your documents",
  calendar: "Checking your calendar",
  task_creator: "Creating a task",
};

function label(agent: string) {
  return LABELS[agent] ?? agent.replace(/_/g, " ");
}

export function AgentActivity({ className = "" }: { className?: string }) {
  const activeAgents = useChatStore((s) => s.activeAgents);
  if (activeAgents.length === 0) return null;

  return (
    <div
      className={`flex flex-wrap gap-2 px-4 py-2 text-xs text-muted-foreground sm:px-6 ${className}`}
    >
      <AnimatePresence>
        {activeAgents.map((agent) => (
          <motion.span
            key={agent}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="inline-flex items-center gap-1.5 rounded-full border border-brand/20 bg-brand/10 px-2.5 py-1 font-medium text-brand"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-brand" />
            </span>
            {label(agent)}…
          </motion.span>
        ))}
      </AnimatePresence>
    </div>
  );
}
