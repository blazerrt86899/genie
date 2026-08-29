import {
  Globe,
  FileText,
  CalendarClock,
  ListChecks,
  BrainCircuit,
  Radio,
} from "lucide-react";
import { Container } from "./Container";

const FEATURES = [
  {
    icon: Globe,
    title: "Web Search",
    body: "Live answers from the open web with sources, not stale training data.",
  },
  {
    icon: FileText,
    title: "Document Q&A",
    body: "Upload your files — Genie answers from them with hybrid vector + keyword search.",
  },
  {
    icon: CalendarClock,
    title: "Calendar",
    body: "Read your schedule and create events. Every write asks you to confirm first.",
  },
  {
    icon: ListChecks,
    title: "Tasks",
    body: "Actionable items are captured automatically and land on your board.",
  },
  {
    icon: BrainCircuit,
    title: "Long-term memory",
    body: "Genie remembers what matters about you across conversations.",
  },
  {
    icon: Radio,
    title: "Streaming",
    body: "Watch each specialist think and respond token-by-token in real time.",
  },
];

export function Features() {
  return (
    <section
      id="features"
      className="scroll-mt-16 border-t border-border bg-muted/20 py-20 sm:py-28"
    >
      <Container>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
            A specialist for every kind of ask
          </h2>
          <p className="mt-3 text-muted-foreground">
            Add capabilities without adding apps. Genie decides which ones a
            request needs.
          </p>
        </div>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((f) => (
            <div
              key={f.title}
              className="group rounded-2xl border border-border bg-card p-6 transition-colors hover:border-brand/40"
            >
              <div className="grid h-10 w-10 place-items-center rounded-xl bg-brand/10 text-brand">
                <f.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 font-semibold">{f.title}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">{f.body}</p>
            </div>
          ))}
        </div>
      </Container>
    </section>
  );
}
