"use client";

import { useEffect, useState } from "react";
import {
  AnimatePresence,
  motion,
  useReducedMotion,
  type Variants,
} from "framer-motion";
import { Check, Sparkles } from "lucide-react";

const REQUEST =
  "Book me a dentist for Thursday morning and text Priya the time.";

const AGENTS = ["prompt enhancer", "calendar", "task creator", "messaging"];

const RESULTS = [
  { icon: "📅", text: "Dentist · Thu 10:30 with Dr. Okafor" },
  { icon: "✅", text: "Reminder: leave by 10:00" },
  { icon: "✉️", text: "Text sent to Priya — “10:30 Thursday”" },
];

// phase: 0 idle · 1 caller · 2-5 agents · 6-8 results · 9 hold
const PHASES = 10;
const STEP_MS = 1150;
const HOLD_MS = 2400;

function Waveform({ animate }: { animate: boolean }) {
  const bars = Array.from({ length: 13 });
  return (
    <div className="flex h-6 items-center gap-[3px]" aria-hidden>
      {bars.map((_, i) => (
        <motion.span
          key={i}
          className="h-5 w-[3px] origin-center rounded-full bg-gradient-to-b from-brand to-brand-2"
          initial={{ scaleY: 0.3 }}
          animate={
            animate
              ? { scaleY: [0.25, 0.4 + ((i * 7) % 16) / 20, 0.25] }
              : { scaleY: 0.35 + ((i * 5) % 12) / 24 }
          }
          transition={
            animate
              ? {
                  duration: 0.9 + (i % 4) * 0.12,
                  repeat: Infinity,
                  ease: "easeInOut",
                  delay: i * 0.06,
                }
              : { duration: 0 }
          }
        />
      ))}
    </div>
  );
}

const pop: Variants = {
  hidden: { opacity: 0, y: 8, scale: 0.96 },
  show: { opacity: 1, y: 0, scale: 1 },
};

export function CallOrb() {
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    if (reduce) {
      setPhase(PHASES - 1);
      return;
    }
    const id = setTimeout(
      () => setPhase((p) => (p + 1) % PHASES),
      phase >= PHASES - 1 ? HOLD_MS : STEP_MS,
    );
    return () => clearTimeout(id);
  }, [phase, reduce]);

  const showCaller = phase >= 1;
  const agentsDone = Math.max(0, Math.min(AGENTS.length, phase - 1));
  const resultsShown = Math.max(0, Math.min(RESULTS.length, phase - 5));
  const timer = `00:${String(Math.min(12, 2 + phase)).padStart(2, "0")}`;

  return (
    <div className="relative mx-auto w-full max-w-md">
      {/* glow */}
      <div
        aria-hidden
        className="pointer-events-none absolute -inset-16 -z-10 rounded-full bg-glow/25 blur-3xl dark:bg-glow/20"
      />
      {/* drifting orbs */}
      {!reduce && (
        <>
          <motion.div
            aria-hidden
            className="pointer-events-none absolute -left-10 -top-8 -z-10 h-24 w-24 rounded-full bg-brand/30 blur-2xl"
            animate={{ y: [0, 14, 0], x: [0, 8, 0] }}
            transition={{ duration: 9, repeat: Infinity, ease: "easeInOut" }}
          />
          <motion.div
            aria-hidden
            className="pointer-events-none absolute -bottom-10 -right-8 -z-10 h-28 w-28 rounded-full bg-brand-2/25 blur-2xl"
            animate={{ y: [0, -16, 0], x: [0, -6, 0] }}
            transition={{ duration: 11, repeat: Infinity, ease: "easeInOut" }}
          />
        </>
      )}

      <div className="rounded-2xl border border-border bg-card/80 p-4 shadow-2xl shadow-brand/10 backdrop-blur-xl sm:p-5">
        {/* header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500/70" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
            Live call · {timer}
          </div>
          <Waveform animate={!reduce} />
        </div>

        <div className="mt-4 space-y-3">
          {/* caller */}
          <AnimatePresence>
            {showCaller && (
              <motion.div
                variants={pop}
                initial="hidden"
                animate="show"
                exit={{ opacity: 0 }}
                className="flex items-start gap-2"
              >
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-semibold text-muted-foreground">
                  P
                </span>
                <p className="rounded-2xl rounded-tl-sm bg-muted px-3 py-2 text-sm text-foreground">
                  {REQUEST.split(" ").map((w, i) => (
                    <motion.span
                      key={i}
                      initial={reduce ? false : { opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: reduce ? 0 : i * 0.03 }}
                    >
                      {w}{" "}
                    </motion.span>
                  ))}
                </p>
              </motion.div>
            )}
          </AnimatePresence>

          {/* genie routing */}
          <AnimatePresence>
            {phase >= 2 && (
              <motion.div
                variants={pop}
                initial="hidden"
                animate="show"
                className="flex items-start gap-2"
              >
                <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-gradient-to-br from-brand to-brand-2 text-brand-foreground">
                  <Sparkles className="h-3 w-3" />
                </span>
                <div className="min-w-0">
                  <p className="text-xs text-muted-foreground">
                    Genie is routing to specialists
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {AGENTS.map((a, i) => {
                      const done = i < agentsDone;
                      const active = i === agentsDone && phase < PHASES - 1;
                      return (
                        <span
                          key={a}
                          className={[
                            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors",
                            done
                              ? "border-brand/30 bg-brand/10 text-foreground"
                              : active
                                ? "border-brand/40 bg-brand/5 text-foreground"
                                : "border-border text-muted-foreground/60",
                          ].join(" ")}
                        >
                          {done ? (
                            <Check className="h-3 w-3 text-brand" />
                          ) : active ? (
                            <motion.span
                              className="h-1.5 w-1.5 rounded-full bg-brand"
                              animate={{ opacity: [1, 0.3, 1] }}
                              transition={{ duration: 0.8, repeat: Infinity }}
                            />
                          ) : (
                            <span className="h-1.5 w-1.5 rounded-full bg-current opacity-40" />
                          )}
                          {a}
                        </span>
                      );
                    })}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {/* results */}
          <AnimatePresence>
            {resultsShown > 0 && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="space-y-1.5 border-t border-border pt-3"
              >
                {RESULTS.slice(0, resultsShown).map((r) => (
                  <motion.div
                    key={r.text}
                    variants={pop}
                    initial="hidden"
                    animate="show"
                    className="flex items-center gap-2 rounded-lg bg-emerald-500/10 px-2.5 py-1.5 text-[13px] text-foreground"
                  >
                    <span aria-hidden>{r.icon}</span>
                    <span className="min-w-0 flex-1 truncate">{r.text}</span>
                    <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" />
                  </motion.div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
