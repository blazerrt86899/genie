import Link from "next/link";
import { Wordmark } from "@/components/landing/Wordmark";

export default function SharedChatNotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-background px-6 text-center text-foreground">
      <Wordmark />
      <h1 className="text-lg font-semibold">This shared chat is unavailable</h1>
      <p className="max-w-sm text-sm text-muted-foreground">
        The link may have been turned off by its owner, or it never existed.
      </p>
      <Link
        href="/"
        className="mt-2 text-sm font-medium text-brand hover:underline"
      >
        Go to Genie →
      </Link>
    </div>
  );
}
