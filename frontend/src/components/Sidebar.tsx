"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import { FolderKanban, ListTodo, Plus, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { BackendStatus } from "@/components/BackendStatus";
import { useChatStore } from "@/store/chatStore";
import {
  useConversations,
  useDeleteConversation,
} from "@/hooks/useConversations";
import { Wordmark } from "@/components/landing/Wordmark";

function ConversationRow({
  id,
  title,
  inProject,
  active,
  onDelete,
}: {
  id: string;
  title: string | null;
  inProject: boolean;
  active: boolean;
  onDelete: () => void;
}) {
  return (
    <div className="group relative">
      <Link
        href={`/chat/${id}`}
        className={cn(
          "flex items-center gap-1.5 truncate rounded-md py-2 pl-2 pr-8 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
          active && "bg-accent font-medium text-foreground",
        )}
      >
        {inProject && (
          <FolderKanban className="h-3 w-3 shrink-0 text-muted-foreground/60" />
        )}
        <span className="truncate">{title || "New chat"}</span>
      </Link>
      <button
        type="button"
        aria-label="Delete conversation"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          if (window.confirm("Delete this conversation?")) onDelete();
        }}
        className="absolute right-1.5 top-1/2 hidden -translate-y-1/2 rounded p-1 text-muted-foreground hover:bg-background hover:text-red-500 group-hover:block"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const reset = useChatStore((s) => s.reset);
  const { data: conversations, isLoading } = useConversations();
  const del = useDeleteConversation();

  const startNew = () => {
    reset();
    router.push("/chat");
  };

  const handleDelete = (id: string) => {
    del.mutate(id, {
      onSuccess: () => {
        if (pathname === `/chat/${id}`) {
          reset();
          router.push("/chat");
        }
      },
    });
  };

  return (
    <aside className="flex w-64 shrink-0 flex-col overflow-hidden border-r border-border bg-card">
      <div className="space-y-2 p-3">
        <Link href="/" className="flex px-1">
          <Wordmark />
        </Link>
        <Button variant="brand" className="w-full justify-start gap-2" onClick={startNew}>
          <Plus className="h-4 w-4" />
          New chat
        </Button>
        <Link
          href="/projects"
          className={cn(
            "flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground",
            pathname.startsWith("/projects") && "bg-accent font-medium text-foreground",
          )}
        >
          <FolderKanban className="h-4 w-4" />
          Projects
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto px-3 pb-3">
        <p className="px-2 pb-1 pt-2 text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
          Chats
        </p>
        {isLoading ? (
          <div className="space-y-1">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-8 animate-pulse rounded-md bg-muted" />
            ))}
          </div>
        ) : conversations && conversations.length > 0 ? (
          <div className="space-y-0.5">
            {conversations.map((c) => (
              <ConversationRow
                key={c.id}
                id={c.id}
                title={c.title}
                inProject={c.project_id !== null}
                active={pathname === `/chat/${c.id}`}
                onDelete={() => handleDelete(c.id)}
              />
            ))}
          </div>
        ) : (
          <p className="px-2 py-2 text-xs text-muted-foreground">
            No conversations yet.
          </p>
        )}
      </div>

      <div className="space-y-3 border-t border-border p-3">
        <Link
          href="/tasks"
          className={cn(
            "flex items-center gap-2 rounded-md px-2 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground",
            pathname.startsWith("/tasks") && "bg-accent font-medium text-foreground",
          )}
        >
          <ListTodo className="h-4 w-4" />
          Tasks
        </Link>
        <BackendStatus />
        <Show when="signed-out">
          <div className="flex flex-col gap-2">
            <SignInButton mode="modal" fallbackRedirectUrl="/chat">
              <Button variant="outline" size="sm" className="w-full">
                Sign in
              </Button>
            </SignInButton>
            <SignUpButton mode="modal" fallbackRedirectUrl="/chat">
              <Button variant="brand" size="sm" className="w-full">
                Sign up
              </Button>
            </SignUpButton>
          </div>
        </Show>
        <Show when="signed-in">
          <div className="flex items-center gap-2 px-1">
            <UserButton />
            <span className="text-xs text-muted-foreground">Account</span>
          </div>
        </Show>
      </div>
    </aside>
  );
}
