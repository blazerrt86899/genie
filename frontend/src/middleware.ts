import { clerkMiddleware } from "@clerk/nextjs/server";

/**
 * Clerk v7 recommends resource-based auth checks, not middleware path-matching.
 * This runs `clerkMiddleware` so `auth()` is available everywhere and Clerk's
 * auto-proxy (`/__clerk/*`) works; the actual gate lives in
 * `src/app/(app)/layout.tsx`.
 */
export default clerkMiddleware();

export const config = {
  matcher: [
    // Skip Next.js internals and static files, unless found in search params
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    // Always run for API routes and Clerk's auto-proxy path
    "/(api|trpc)(.*)",
    "/__clerk/:path*",
  ],
};
