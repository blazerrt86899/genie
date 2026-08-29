"use client";

import { motion, useReducedMotion } from "framer-motion";
import { Container } from "./Container";

export function VoiceComingSoon() {
  const reduce = useReducedMotion();
  const bars = Array.from({ length: 28 });

  return (
    <section className="py-20 sm:py-28">
      <Container>
        <div className="relative overflow-hidden rounded-3xl border border-border bg-card p-8 sm:p-12">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 -z-10 bg-[radial-gradient(ellipse_50%_60%_at_100%_50%,hsl(var(--glow)/0.14),transparent)]"
          />
          <div className="grid items-center gap-8 lg:grid-cols-[1fr_auto]">
            <div className="max-w-xl">
              <span className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/10 px-3 py-1 text-xs font-medium text-brand">
                Coming soon
              </span>
              <h2 className="mt-4 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
                Then, just say it out loud
              </h2>
              <p className="mt-3 text-muted-foreground">
                Genie is becoming a voice concierge — call a number, speak
                naturally, and the same agent orchestration runs the whole
                errand while you stay on the line.
              </p>
              <a
                href="#"
                className="mt-6 inline-flex text-sm font-medium text-brand hover:underline"
              >
                Join the voice waitlist →
              </a>
            </div>

            <div
              className="flex h-24 items-center gap-1 sm:h-28"
              aria-hidden
            >
              {bars.map((_, i) => (
                <motion.span
                  key={i}
                  className="w-1 rounded-full bg-gradient-to-b from-brand to-brand-2"
                  initial={{ height: 8 }}
                  animate={
                    reduce
                      ? { height: 10 + ((i * 11) % 40) }
                      : { height: [8, 12 + ((i * 13) % 56), 8] }
                  }
                  transition={
                    reduce
                      ? { duration: 0 }
                      : {
                          duration: 1 + (i % 5) * 0.15,
                          repeat: Infinity,
                          ease: "easeInOut",
                          delay: i * 0.04,
                        }
                  }
                />
              ))}
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
