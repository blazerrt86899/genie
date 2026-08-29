import { MessagesSquare, Sparkles, CircleCheck } from "lucide-react";
import { Container } from "./Container";

const STEPS = [
  {
    icon: MessagesSquare,
    title: "Ask Genie",
    body: "Call or message in plain language — “move my 3pm and find me a flight to Lisbon”.",
  },
  {
    icon: Sparkles,
    title: "Genie orchestrates",
    body: "A supervisor picks the right specialist agents and runs them in parallel, within a strict token budget.",
  },
  {
    icon: CircleCheck,
    title: "One answer, done",
    body: "You get a single synthesised reply — sources cited, calendar updated, tasks created.",
  },
];

export function HowItWorks() {
  return (
    <section id="how" className="scroll-mt-16 py-20 sm:py-28">
      <Container>
        <div className="max-w-2xl">
          <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
            One request in. One result out.
          </h2>
          <p className="mt-3 text-muted-foreground">
            Genie is not a single chatbot — it is a team of specialists behind
            one conversation.
          </p>
        </div>

        <ol className="mt-12 grid gap-6 md:grid-cols-3">
          {STEPS.map((step, i) => (
            <li
              key={step.title}
              className="relative rounded-2xl border border-border bg-card p-6"
            >
              <span className="text-sm font-mono text-brand">0{i + 1}</span>
              <step.icon className="mt-3 h-6 w-6 text-brand" />
              <h3 className="mt-3 font-semibold">{step.title}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">{step.body}</p>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
