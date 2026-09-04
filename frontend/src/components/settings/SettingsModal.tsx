"use client";

import { useEffect, useState } from "react";
import { UserProfile } from "@clerk/nextjs";
import { useTheme } from "next-themes";
import {
  BarChart3,
  CircleUser,
  Monitor,
  Moon,
  Settings2,
  Sun,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { useUsage } from "@/hooks/useUsage";

type Section = "general" | "account" | "usage";

const NAV: { id: Section; label: string; icon: typeof Settings2 }[] = [
  { id: "general", label: "General", icon: Settings2 },
  { id: "account", label: "Account", icon: CircleUser },
  { id: "usage", label: "Usage", icon: BarChart3 },
];

export function SettingsModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [section, setSection] = useState<Section>("general");

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Settings"
        onClick={(e) => e.stopPropagation()}
        className="flex h-[85vh] max-h-[680px] min-h-[440px] w-full max-w-4xl overflow-hidden rounded-3xl border border-border bg-card shadow-2xl"
      >
        {/* ── left rail ─────────────────────────────────────────── */}
        <div className="flex w-52 shrink-0 flex-col gap-1 border-r border-border bg-sidebar p-3">
          <p className="px-3.5 pb-1 pt-2 text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
            Settings
          </p>
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setSection(id)}
              className={cn(
                "flex w-full items-center gap-3 rounded-full px-3.5 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
                section === id && "bg-accent text-foreground",
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {label}
            </button>
          ))}
        </div>

        {/* ── content ───────────────────────────────────────────── */}
        <div className="relative flex-1 overflow-y-auto">
          <button
            type="button"
            aria-label="Close settings"
            onClick={onClose}
            className="absolute right-4 top-4 z-10 grid h-9 w-9 place-items-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>

          <div className="p-6 pr-16">
            {section === "general" && <GeneralPanel />}
            {section === "account" && <AccountPanel />}
            {section === "usage" && <UsagePanel />}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── General ───────────────────────────────────────────────────── */

const APPEARANCE = [
  { value: "system", label: "System", icon: Monitor },
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
] as const;

function GeneralPanel() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const current = mounted ? (theme ?? "system") : "system";

  return (
    <section>
      <h2 className="text-base font-semibold">Preferences</h2>
      <div className="mt-4 flex items-center justify-between border-t border-border py-4">
        <div>
          <p className="text-sm font-medium">Appearance</p>
          <p className="text-xs text-muted-foreground">
            How Genie looks on this device.
          </p>
        </div>
        <div className="flex items-center gap-1 rounded-full border border-border bg-muted p-1">
          {APPEARANCE.map(({ value, label, icon: Icon }) => (
            <button
              key={value}
              type="button"
              aria-label={label}
              title={label}
              onClick={() => setTheme(value)}
              className={cn(
                "grid h-8 w-9 place-items-center rounded-full text-muted-foreground transition-colors hover:text-foreground",
                current === value && "bg-card text-foreground shadow-sm",
              )}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Account ───────────────────────────────────────────────────── */

function AccountPanel() {
  return (
    <section>
      <h2 className="mb-4 text-base font-semibold">Account</h2>
      <UserProfile
        routing="hash"
        appearance={{
          ...clerkAppearance,
          elements: {
            ...(clerkAppearance as { elements?: Record<string, string> })
              .elements,
            rootBox: "w-full",
            cardBox: "w-full shadow-none border-0 bg-transparent",
            navbar: "hidden",
            navbarMobileMenuRow: "hidden",
            scrollBox: "bg-transparent",
          },
        }}
      />
    </section>
  );
}

/* ── Usage ─────────────────────────────────────────────────────── */

function UsagePanel() {
  const { data, isPending, isError } = useUsage();

  const pct =
    data && data.token_budget > 0
      ? Math.min(100, Math.round((data.tokens_used_30d / data.token_budget) * 100))
      : 0;

  return (
    <section>
      <h2 className="text-base font-semibold">Usage</h2>
      <p className="mt-1 text-xs text-muted-foreground">Last 30 days.</p>

      {isError ? (
        <p className="mt-6 text-sm text-muted-foreground">
          Couldn&apos;t load usage right now.
        </p>
      ) : isPending ? (
        <div className="mt-6 space-y-4">
          <div className="h-16 animate-pulse rounded-2xl bg-muted" />
          <div className="grid grid-cols-3 gap-3">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-20 animate-pulse rounded-2xl bg-muted" />
            ))}
          </div>
        </div>
      ) : (
        <>
          <div className="mt-6 rounded-2xl border border-border p-4">
            <div className="flex items-baseline justify-between text-sm">
              <span className="font-medium">Tokens used</span>
              <span className="text-muted-foreground">
                {data.tokens_used_30d.toLocaleString()} /{" "}
                {data.token_budget.toLocaleString()}
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-gradient-to-r from-brand to-brand-2"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <Stat label="Conversations" value={data.conversations} />
            <Stat label="Messages" value={data.messages_30d} />
            <Stat label="Tokens" value={data.tokens_used_30d} />
          </div>
        </>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-border p-4">
      <p className="text-xl font-semibold tabular-nums">
        {value.toLocaleString()}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
