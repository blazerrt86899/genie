"use client";

import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";

/** Two-word phrases that swap in on a timer, Genie-flavoured. */
const PHRASES = [
  "conjure today",
  "dig up",
  "plan next",
  "automate now",
  "figure out",
  "get done",
  "pull together",
  "look into",
] as const;

const INTERVAL_MS = 3200;

export function GreetingHeadline() {
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = setInterval(
      () => setIdx((i) => (i + 1) % PHRASES.length),
      INTERVAL_MS,
    );
    return () => clearInterval(t);
  }, []);

  return (
    <h1 className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 text-center text-3xl font-semibold tracking-tight sm:text-4xl">
      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-brand to-brand-2 text-brand-foreground shadow-sm shadow-brand/30 sm:h-10 sm:w-10">
        <Sparkles className="h-5 w-5" />
      </span>
      <span className="text-foreground">What can Genie</span>
      {/* keyed so the animation restarts on every swap */}
      <span
        key={idx}
        className="animate-greeting-swap inline-block bg-gradient-to-r from-brand to-brand-2 bg-clip-text text-transparent"
      >
        {PHRASES[idx]}
      </span>
      <span className="-ml-2 text-foreground">?</span>
    </h1>
  );
}
