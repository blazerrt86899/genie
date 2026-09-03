import Link from "next/link";
import { ArrowRight, Phone } from "lucide-react";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { CallOrb } from "./CallOrb";
import { Container } from "./Container";

export function Hero() {
  return (
    <section className="relative overflow-hidden">
      {/* backdrop — violet core with a cyan companion (the "nebula" identity) */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -top-40 -z-10 h-[600px] bg-[radial-gradient(ellipse_55%_50%_at_45%_0%,hsl(var(--glow)/0.16),transparent),radial-gradient(ellipse_38%_38%_at_78%_8%,hsl(var(--glow-2)/0.13),transparent)]"
      />
      <Container className="grid items-center gap-14 py-16 sm:py-24 lg:grid-cols-[1.05fr_0.95fr] lg:gap-10">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-border bg-muted/50 px-3 py-1 text-xs font-medium text-muted-foreground">
            <span className="h-1.5 w-1.5 rounded-full bg-brand" />
            Early access · chat today, voice next
          </span>

          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
            Genie, your{" "}
            <span className="bg-gradient-to-r from-brand to-brand-2 bg-clip-text text-transparent">
              voice AI concierge
            </span>
          </h1>

          <p className="mt-5 max-w-xl text-lg text-muted-foreground text-balance">
            Ask once. Genie understands what you want, routes it to the right
            specialist agents — web, calendar, tasks, your documents — and hands
            back one clear answer with the work already done.
          </p>

          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Link
              href="/sign-up"
              className={cn(buttonVariants({ variant: "brand", size: "lg" }))}
            >
              Get started <ArrowRight className="h-4 w-4" />
            </Link>
            <a
              href="#how"
              className={cn(buttonVariants({ variant: "outline", size: "lg" }))}
            >
              See how it works
            </a>
          </div>

          <p className="mt-5 inline-flex items-center gap-2 text-sm text-muted-foreground">
            <Phone className="h-4 w-4" />
            Voice calling launches soon — start with chat now.
          </p>
        </div>

        <CallOrb />
      </Container>
    </section>
  );
}
