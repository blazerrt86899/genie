"use client";

import { AnimatePresence, motion } from "framer-motion";

const LABELS: Record<string, string> = {
  prompt_enhancer: "Understanding your request",
  kb_search: "Searching your knowledge base",
  greeting: "Greeting you",
  web_search: "Searching the web",
  rag: "Reading your documents",
  calendar: "Checking your calendar",
  task_creator: "Updating your tasks",
  task_summary: "Summarising the task",
};

function label(agent: string) {
  return LABELS[agent] ?? agent.replace(/_/g, " ");
}

/** Live "…working" pills for agents whose message hasn't appeared yet. Rendered
 *  at the tail of the message list, right above where the next message lands. */
export function AgentActivity({ agents }: { agents: string[] }) {
  if (agents.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-2 px-1 text-xs">
      <AnimatePresence>
        {agents.map((agent) => (
          <motion.span
            key={agent}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            className="inline-flex items-center gap-1.5 font-medium text-brand"
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
