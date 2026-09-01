"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { useModels } from "@/hooks/useModels";
import { useChatStore } from "@/store/chatStore";

/**
 * Chat-model picker for the composer (ChatGPT-style). The choice is stored per
 * conversation server-side and remembered for new chats in `localStorage`.
 * Controls the chat model only — the internal utility calls are fixed.
 */
export function ModelPicker({ disabled }: { disabled?: boolean }) {
  const { data } = useModels();
  const model = useChatStore((s) => s.model);
  const setModel = useChatStore((s) => s.setModel);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const models = data?.models ?? [];
  if (models.length < 2) return null;

  const activeId = model ?? data?.default ?? models[0].id;
  const active = models.find((m) => m.id === activeId) ?? models[0];

  function pick(id: string) {
    setModel(id);
    try {
      localStorage.setItem("genie.chat_model", id);
    } catch {
      /* private mode / storage disabled */
    }
    setOpen(false);
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-50"
      >
        <Sparkles className="h-3.5 w-3.5 text-brand" />
        {active.label}
        <ChevronDown className="h-3 w-3 opacity-60" />
      </button>

      {open && (
        <ul
          role="listbox"
          className="absolute bottom-full left-0 z-20 mb-1.5 max-h-72 w-60 overflow-y-auto rounded-lg border border-border bg-card p-1 shadow-lg"
        >
          {models.map((m) => (
            <li key={m.id}>
              <button
                type="button"
                role="option"
                aria-selected={m.id === active.id}
                onClick={() => pick(m.id)}
                className={cn(
                  "flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent",
                  m.id === active.id && "bg-accent/60",
                )}
              >
                <Check
                  className={cn(
                    "mt-0.5 h-3.5 w-3.5 shrink-0",
                    m.id === active.id ? "opacity-100 text-brand" : "opacity-0",
                  )}
                />
                <span className="min-w-0">
                  <span className="block truncate font-medium">{m.label}</span>
                  <span className="block truncate text-xs text-muted-foreground">
                    {m.provider} · {m.hint}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
