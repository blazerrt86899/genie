"use client";

import { ClerkProvider } from "@clerk/nextjs";
import { CLERK_ENABLED } from "@/lib/clerk";

/**
 * Wraps the app in <ClerkProvider> only when Clerk is configured, so local
 * development works without Clerk keys (CLAUDE.md §7 dev bypass).
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  if (!CLERK_ENABLED) return <>{children}</>;
  return <ClerkProvider>{children}</ClerkProvider>;
}
