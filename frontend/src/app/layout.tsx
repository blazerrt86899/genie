import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { QueryProvider } from "@/providers/query-provider";
import { ThemeProvider } from "@/providers/theme-provider";

export const metadata: Metadata = {
  title: "Genie — your voice AI concierge",
  description:
    "Ask once. Genie routes your request to the right specialist agents and gets it done — web, calendar, tasks, documents. Voice coming soon.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen antialiased">
        <ThemeProvider>
          <ClerkProvider appearance={clerkAppearance}>
            <QueryProvider>{children}</QueryProvider>
          </ClerkProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
