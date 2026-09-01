"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@clerk/nextjs";
import { getMe } from "@/lib/api";

/**
 * Post-sign-up landing (CLAUDE.md §7.8). The Clerk `user.created` webhook that
 * inserts the `users` row can lag the redirect, so we poll `GET /users/me` until
 * it's a 200 before letting the user into `/chat`.
 */
export default function WelcomePage() {
  const router = useRouter();
  const { getToken, isLoaded, isSignedIn } = useAuth();
  const [slow, setSlow] = useState(false);

  useEffect(() => {
    if (!isLoaded) return;
    if (!isSignedIn) {
      router.replace("/sign-in");
      return;
    }
    let cancelled = false;
    const deadline = Date.now() + 12_000;
    (async () => {
      while (!cancelled) {
        try {
          await getMe(await getToken());
          if (!cancelled) router.replace("/chat");
          return;
        } catch {
          if (Date.now() > deadline) {
            if (!cancelled) setSlow(true);
            return;
          }
          await new Promise((r) => setTimeout(r, 800));
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isLoaded, isSignedIn, getToken, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center">
      {slow ? (
        <>
          <p className="text-sm text-muted-foreground">
            Almost there — this is taking longer than usual.
          </p>
          <button
            type="button"
            onClick={() => router.replace("/chat")}
            className="text-sm font-medium text-brand hover:underline"
          >
            Continue to Genie →
          </button>
        </>
      ) : (
        <>
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-brand border-t-transparent" />
          <p className="text-sm text-muted-foreground">Setting up your account…</p>
        </>
      )}
    </div>
  );
}
