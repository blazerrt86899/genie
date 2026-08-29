/**
 * Theme Clerk's prebuilt components via the CSS-free `appearance` API so they
 * match the app shell. (The `@clerk/ui` shadcn theme needs Tailwind v4; this
 * project is on v3.)
 *
 * Typed structurally by `<ClerkProvider appearance={...}>` at the call site.
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: "#0f172a", // slate-900 — matches --primary in globals.css
    colorText: "#0f172a",
    colorBackground: "#ffffff",
    colorInputBackground: "#ffffff",
    borderRadius: "0.5rem",
    fontFamily: "inherit",
  },
  elements: {
    card: "shadow-sm border border-border",
    headerTitle: "text-lg",
    formButtonPrimary:
      "bg-primary text-primary-foreground hover:bg-primary/90 normal-case",
    footerActionLink: "text-primary hover:text-primary/80",
  },
} as const;
