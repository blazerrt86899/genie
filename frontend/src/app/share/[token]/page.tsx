import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { getSharedConversation, ApiError } from "@/lib/api";
import { Wordmark } from "@/components/landing/Wordmark";
import { Message } from "@/components/chat/Message";
import type { ChatMessage } from "@/store/chatStore";

// Reachable only via the unguessable token — keep it out of search indexes.
export const metadata: Metadata = {
  robots: { index: false, follow: false },
};

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

export default async function SharedChatPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  const data = await getSharedConversation(token).catch((err) => {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  });
  if (!data) notFound();

  const messages: ChatMessage[] = data.messages.map((m) => ({
    id: m.id,
    role: m.role,
    content: m.content,
    agents: m.agents ?? [],
    attachments: (m.attachments ?? []).map((a) => ({
      filename: a.filename,
      kind: a.kind,
    })),
    sources: m.sources ?? [],
  }));

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b border-border bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-3 sm:px-6">
          <Link href="/">
            <Wordmark />
          </Link>
          <span className="text-xs text-muted-foreground">
            Shared conversation · {fmtDate(data.shared_at)}
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        {data.title && (
          <h1 className="mb-6 text-xl font-semibold tracking-tight">
            {data.title}
          </h1>
        )}

        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            This shared conversation has no messages yet.
          </p>
        ) : (
          <div className="flex flex-col gap-8">
            {messages.map((m) => (
              <Message key={m.id} message={m} userName="User" />
            ))}
          </div>
        )}
      </main>

      <footer className="mx-auto max-w-3xl px-4 pb-12 pt-4 sm:px-6">
        <div className="rounded-xl border border-border bg-card p-4 text-sm text-muted-foreground">
          This is a read-only snapshot shared from Genie. Messages added after it
          was shared aren&apos;t included.{" "}
          <Link href="/" className="font-medium text-brand hover:underline">
            Start your own →
          </Link>
        </div>
      </footer>
    </div>
  );
}
