/**
 * Theme Clerk's prebuilt components via the CSS-free `appearance` API.
 *
 * Every colour is bound to the app's HSL design tokens (`globals.css`), so
 * Clerk follows light/dark automatically — the CSS custom properties re-resolve
 * when `next-themes` toggles the `dark` class, no re-render needed. (The
 * `@clerk/ui` / `@clerk/themes` packages need Tailwind v4 or Core 2; we're on
 * Tailwind v3 + Clerk Core 3.)
 *
 * Both the pre-Core-3 and Core-3 variable names are set — Clerk ignores the
 * ones it doesn't recognise.
 */
export const clerkAppearance = {
  variables: {
    colorPrimary: "hsl(var(--brand))",
    colorPrimaryForeground: "hsl(var(--brand-foreground))",

    colorBackground: "hsl(var(--card))",

    colorText: "hsl(var(--foreground))",
    colorForeground: "hsl(var(--foreground))",
    colorTextSecondary: "hsl(var(--muted-foreground))",
    colorMutedForeground: "hsl(var(--muted-foreground))",
    colorMuted: "hsl(var(--muted))",
    colorNeutral: "hsl(var(--foreground))",

    colorInputBackground: "hsl(var(--background))",
    colorInput: "hsl(var(--background))",
    colorInputText: "hsl(var(--foreground))",
    colorInputForeground: "hsl(var(--foreground))",

    colorShimmer: "hsl(var(--muted))",
    borderRadius: "0.6rem",
    fontFamily: "inherit",
  },
  elements: {
    card: "border border-border shadow-xl",
    headerTitle: "text-lg",
    socialButtonsBlockButton: "border border-border",
    formFieldInput: "border border-input",
    formButtonPrimary:
      "bg-gradient-to-r from-brand to-brand-2 text-brand-foreground shadow-sm hover:opacity-90 normal-case",
    footerActionLink: "text-brand hover:text-brand/80",
  },
} as const;
