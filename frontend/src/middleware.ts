import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

/**
 * Clerk route protection (CLAUDE.md §7.6). When Clerk keys are absent the
 * middleware is a pass-through so local dev works without a Clerk app.
 * The env var is inlined at build time, so the unused branch is dropped.
 */
const isProtected = createRouteMatcher([
  "/(app)(.*)",
  "/chat(.*)",
  "/tasks(.*)",
]);

export default process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY
  ? clerkMiddleware((auth, req) => {
      if (isProtected(req)) auth().protect();
    })
  : () => NextResponse.next();

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
