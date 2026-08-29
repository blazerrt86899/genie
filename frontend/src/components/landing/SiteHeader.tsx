"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Show } from "@clerk/nextjs";
import { Menu, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { buttonVariants } from "@/components/ui/button";
import { Container } from "./Container";
import { ThemeToggle } from "./ThemeToggle";
import { Wordmark } from "./Wordmark";

const NAV = [
  { label: "Product", href: "#features" },
  { label: "How it works", href: "#how" },
  { label: "Solutions", href: "#" },
  { label: "Docs", href: "#" },
  { label: "Pricing", href: "#" },
];

export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-50 transition-colors",
        scrolled
          ? "border-b border-border bg-background/80 backdrop-blur-md"
          : "border-b border-transparent",
      )}
    >
      <Container className="flex h-16 items-center justify-between gap-4">
        <Link href="/" className="shrink-0">
          <Wordmark />
        </Link>

        <nav className="hidden items-center gap-7 text-sm text-muted-foreground md:flex">
          {NAV.map((item) => (
            <a
              key={item.label}
              href={item.href}
              className="transition-colors hover:text-foreground"
            >
              {item.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-2 md:flex">
          <ThemeToggle />
          <Show when="signed-out">
            <Link
              href="/sign-in"
              className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}
            >
              Sign in
            </Link>
            <Link
              href="/sign-up"
              className={cn(buttonVariants({ variant: "brand", size: "sm" }))}
            >
              Get started
            </Link>
          </Show>
          <Show when="signed-in">
            <Link
              href="/chat"
              className={cn(buttonVariants({ variant: "brand", size: "sm" }))}
            >
              Open Genie
            </Link>
          </Show>
        </div>

        <div className="flex items-center gap-2 md:hidden">
          <ThemeToggle />
          <button
            type="button"
            aria-label="Menu"
            onClick={() => setOpen((v) => !v)}
            className="grid h-9 w-9 place-items-center rounded-md border border-border text-muted-foreground"
          >
            {open ? <X className="h-4 w-4" /> : <Menu className="h-4 w-4" />}
          </button>
        </div>
      </Container>

      {open && (
        <div className="border-t border-border bg-background md:hidden">
          <Container className="flex flex-col gap-1 py-3">
            {NAV.map((item) => (
              <a
                key={item.label}
                href={item.href}
                onClick={() => setOpen(false)}
                className="rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                {item.label}
              </a>
            ))}
            <div className="mt-2 flex flex-col gap-2">
              <Show when="signed-out">
                <Link
                  href="/sign-in"
                  className={cn(buttonVariants({ variant: "outline", size: "sm" }))}
                >
                  Sign in
                </Link>
                <Link
                  href="/sign-up"
                  className={cn(buttonVariants({ variant: "brand", size: "sm" }))}
                >
                  Get started
                </Link>
              </Show>
              <Show when="signed-in">
                <Link
                  href="/chat"
                  className={cn(buttonVariants({ variant: "brand", size: "sm" }))}
                >
                  Open Genie
                </Link>
              </Show>
            </div>
          </Container>
        </div>
      )}
    </header>
  );
}
