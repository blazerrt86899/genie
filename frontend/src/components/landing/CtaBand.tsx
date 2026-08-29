import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Container } from "./Container";

export function CtaBand() {
  return (
    <section className="pb-24">
      <Container>
        <div className="relative overflow-hidden rounded-3xl bg-gradient-to-r from-brand to-brand-2 px-8 py-14 text-center text-brand-foreground sm:px-12">
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_40%_60%_at_20%_20%,rgba(255,255,255,0.18),transparent)]"
          />
          <h2 className="text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
            Ready to make a wish?
          </h2>
          <p className="mx-auto mt-3 max-w-md text-brand-foreground/85">
            Create an account and put Genie to work in under a minute.
          </p>
          <Link
            href="/sign-up"
            className={cn(
              buttonVariants({ size: "lg" }),
              "mt-7 bg-background text-foreground hover:bg-background/90",
            )}
          >
            Get started free <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </Container>
    </section>
  );
}
