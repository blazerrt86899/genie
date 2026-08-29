import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";
import { clerkAppearance } from "@/lib/clerk-appearance";
import { QueryProvider } from "@/providers/query-provider";

export const metadata: Metadata = {
  title: "Genie",
  description: "Your wish, fulfilled — a multi-agent AI orchestration platform",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <ClerkProvider appearance={clerkAppearance}>
          <QueryProvider>{children}</QueryProvider>
        </ClerkProvider>
      </body>
    </html>
  );
}
