"use client";

import { ChevronRight } from "lucide-react";
import { Markdown } from "./Markdown";

/** A collapsible disclosure for a thinking-capable model's reasoning trace —
 * "Thought for 22s ⌄" (Claude-style). Live while streaming (label "Thinking…",
 * an animated dot), settles once `thinkingMs` arrives; the same finished state
 * renders identically for a message reloaded from history. Collapsed by
 * default in both cases — the reader opts in to read the reasoning. */
export function ThinkingBlock({
  thinking,
  thinkingMs,
  active,
}: {
  thinking?: string;
  thinkingMs?: number | null;
  active?: boolean;
}) {
  if (!thinking && !active) return null;

  const seconds = thinkingMs != null ? Math.max(1, Math.round(thinkingMs / 1000)) : null;
  const label = active && seconds == null ? "Thinking" : `Thought for ${seconds}s`;

  return (
    <details className="group mb-1.5 w-full max-w-full">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-1 rounded-md px-1 py-0.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-90" />
        <span>{label}</span>
        {active && seconds == null && (
          <span className="inline-flex gap-0.5">
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="h-1 w-1 animate-pulse rounded-full bg-muted-foreground"
                style={{ animationDelay: `${i * 150}ms` }}
              />
            ))}
          </span>
        )}
      </summary>
      {thinking && (
        <div className="mt-1.5 max-h-64 overflow-y-auto rounded-lg border border-border bg-muted/40 px-3.5 py-2.5 text-[13px] leading-relaxed text-muted-foreground">
          <Markdown>{thinking}</Markdown>
        </div>
      )}
    </details>
  );
}
