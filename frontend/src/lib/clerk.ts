/** Whether Clerk is configured. When false, the app runs in a public dev mode. */
export const CLERK_ENABLED = Boolean(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY,
);
