"use client";

import { AnimatePresence, motion } from "framer-motion";
import { useChatStore } from "@/store/chatStore";

export function AgentActivity() {
  const activeAgents = useChatStore((s) => s.activeAgents);
  if (activeAgents.length === 0) return null;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-wrap gap-2 px-4 py-2 text-xs text-muted-foreground">
      <AnimatePresence>
        {activeAgents.map((agent) => (
          <motion.span
            key={agent}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="rounded-full bg-accent px-2 py-1"
          >
            {agent} is thinking…
          </motion.span>
        ))}
      </AnimatePresence>
    </div>
  );
}
