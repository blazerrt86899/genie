"use client";

import { Check, CircleDashed, Loader2, X } from "lucide-react";
import { useChatStore } from "@/store/chatStore";
import type { PlanStepView } from "@/lib/sse";

const AGENT_LABEL: Record<string, string> = {
  greeting: "Greeting",
  web_search: "Web search",
  task_creator: "Tasks",
  rag: "Your documents",
};

function label(agent: string) {
  return AGENT_LABEL[agent] ?? agent.replace(/_/g, " ");
}

function StatusIcon({ status }: { status: PlanStepView["status"] }) {
  if (status === "done") return <Check className="h-3 w-3 text-emerald-500" />;
  if (status === "failed") return <X className="h-3 w-3 text-red-500" />;
  if (status === "in_progress")
    return <Loader2 className="h-3 w-3 animate-spin text-brand" />;
  return <CircleDashed className="h-3 w-3 text-muted-foreground/60" />;
}

export function PlanStrip() {
  const plan = useChatStore((s) => s.plan);
  if (plan.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-4 py-2 text-[11px] sm:px-6">
      <span className="mr-1 font-semibold uppercase tracking-wider text-muted-foreground/70">
        Plan
      </span>
      {plan.map((step, i) => (
        <span
          key={step.id}
          className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-muted-foreground"
          title={step.description}
        >
          <span className="text-muted-foreground/50">{i + 1}</span>
          <StatusIcon status={step.status} />
          {label(step.agent)}
        </span>
      ))}
    </div>
  );
}
