"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ComponentType,
} from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";
import {
  FolderKanban,
  ListTodo,
  LogIn,
  PanelLeftClose,
  PanelLeftOpen,
  Pin,
  Plus,
  Sparkles,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { BackendStatus } from "@/components/BackendStatus";
import { useChatStore } from "@/store/chatStore";
import { useConversations, usePatchConversation } from "@/hooks/useConversations";
import type { ConversationSummary } from "@/lib/api";
import {
  ConversationMenu,
  type ConversationMenuTarget,
} from "@/components/chat/ConversationMenu";
import { Wordmark } from "@/components/landing/Wordmark";

function ConversationRow({
  conversation,
  active,
  onDeleted,
}: {
  conversation: ConversationSummary;
  active: boolean;
  onDeleted: () => void;
}) {
  const patch = usePatchConversation();
  const [renaming, setRenaming] = useState(false);
  const [draft, setDraft] = useState("");

  const target: ConversationMenuTarget = {
    id: conversation.id,
    title: conversation.title,
    pinned: conversation.pinned,
    unread: conversation.unread,
    projectId: conversation.project_id,
  };

  function commitRename() {
    const next = draft.trim();
    setRenaming(false);
    if (next && next !== conversation.title) {
      patch.mutate({ id: conversation.id, body: { title: next } });
    }
  }

  if (renaming) {
    return (
      <input
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commitRename}
        onKeyDown={(e) => {
          if (e.key === "Enter") commitRename();
          if (e.key === "Escape") setRenaming(false);
        }}
        className="w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring"
      />
    );
  }

  return (
    <div
      className={cn(
        "group relative flex items-center rounded-md transition-colors hover:bg-accent",
        active && "bg-accent",
      )}
    >
      <Link
        href={`/chat/${conversation.id}`}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-1.5 truncate py-2 pl-2 pr-8 text-sm text-muted-foreground transition-colors group-hover:text-foreground",
          active && "font-medium text-foreground",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "h-1.5 w-1.5 shrink-0 rounded-full",
            conversation.unread
              ? "bg-brand"
              : "border border-muted-foreground/40",
          )}
        />
        {conversation.project_id !== null && (
          <FolderKanban className="h-3 w-3 shrink-0 text-muted-foreground/60" />
        )}
        <span className={cn("truncate", conversation.unread && "text-foreground")}>
          {conversation.title || "New chat"}
        </span>
      </Link>
      <div className="absolute right-1 top-1/2 z-30 -translate-y-1/2 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
        <ConversationMenu
          conversation={target}
          align="right"
          onRename={() => {
            setDraft(conversation.title || "");
            setRenaming(true);
          }}
          onDeleted={onDeleted}
        />
      </div>
    </div>
  );
}

const MIN_W = 220;
const MAX_W = 460;
const DEFAULT_W = 256;
const COLLAPSED_W = 64;

function useSidebarWidth() {
  const [width, setWidth] = useState(DEFAULT_W);
  const [collapsed, setCollapsed] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragging = useRef(false);
  const widthRef = useRef(width);
  widthRef.current = width;

  useEffect(() => {
    try {
      const saved = Number(localStorage.getItem("genie.sidebar_w"));
      if (saved >= MIN_W && saved <= MAX_W) setWidth(saved);
      setCollapsed(localStorage.getItem("genie.sidebar_collapsed") === "1");
    } catch {
      /* ignore */
    }
  }, []);

  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => {
      const next = !c;
      try {
        localStorage.setItem("genie.sidebar_collapsed", next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  // Cmd/Ctrl + \  toggles the sidebar (VS Code-style).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "\\") {
        e.preventDefault();
        toggleCollapsed();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleCollapsed]);

  const onMouseDown = useCallback(() => {
    dragging.current = true;
    setIsDragging(true);
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    const onMove = (e: MouseEvent) => {
      if (!dragging.current) return;
      const w = Math.min(MAX_W, Math.max(MIN_W, e.clientX));
      setWidth(w);
    };
    const onUp = () => {
      dragging.current = false;
      setIsDragging(false);
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      try {
        localStorage.setItem("genie.sidebar_w", String(Math.round(widthRef.current)));
      } catch {
        /* ignore */
      }
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, []);

  return {
    width: collapsed ? COLLAPSED_W : width,
    collapsed,
    toggleCollapsed,
    onMouseDown,
    isDragging,
  };
}

function NavItem({
  href,
  icon: Icon,
  label,
  active,
  collapsed,
}: {
  href: string;
  icon: ComponentType<{ className?: string }>;
  label: string;
  active: boolean;
  collapsed: boolean;
}) {
  return (
    <Link
      href={href}
      title={collapsed ? label : undefined}
      aria-label={label}
      className={cn(
        "flex items-center gap-2 rounded-md py-2 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground",
        collapsed ? "justify-center px-0" : "px-2",
        active && "bg-accent font-medium text-foreground",
      )}
    >
      <Icon className="h-4 w-4 shrink-0" />
      {!collapsed && label}
    </Link>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const reset = useChatStore((s) => s.reset);
  const { data: conversations, isLoading } = useConversations();
  const { width, collapsed, toggleCollapsed, onMouseDown, isDragging } =
    useSidebarWidth();

  const startNew = () => {
    reset();
    router.push("/chat");
  };

  const onDeleted = (id: string) => () => {
    if (pathname === `/chat/${id}`) {
      reset();
      router.push("/chat");
    }
  };

  const pinned = (conversations ?? []).filter((c) => c.pinned);
  const rest = (conversations ?? []).filter((c) => !c.pinned);

  return (
    <>
      {/* dims + blurs the app behind the sidebar while it's being resized */}
      {isDragging && (
        <div
          className="fixed inset-0 z-20 bg-background/60 backdrop-blur-[2px]"
          aria-hidden
        />
      )}
      <aside
        style={{ width }}
        className={cn(
          "relative z-30 flex shrink-0 flex-col overflow-hidden border-r border-border bg-card",
          // animate the collapse/expand, but not while the user is drag-resizing
          isDragging ? "shadow-2xl" : "transition-[width] duration-200 ease-out",
        )}
      >
        {/* drag handle to resize — disabled while collapsed */}
        {!collapsed && (
          <div
            onMouseDown={onMouseDown}
            className="group absolute right-0 top-0 z-30 h-full w-1.5 cursor-col-resize"
            aria-label="Resize sidebar"
            role="separator"
          >
            <div
              className={cn(
                "ml-auto h-full w-px transition-colors group-hover:bg-brand/50",
                isDragging ? "bg-brand" : "bg-transparent",
              )}
            />
          </div>
        )}

        {/* ── Header: wordmark + collapse toggle ───────────────────────────── */}
        <div
          className={cn(
            "flex items-center p-3",
            collapsed ? "flex-col gap-2" : "justify-between",
          )}
        >
          <Link
            href="/"
            aria-label="Genie home"
            className={cn("flex", collapsed ? "" : "px-1")}
          >
            {collapsed ? (
              <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-brand to-brand-2 text-brand-foreground">
                <Sparkles className="h-4 w-4" />
              </span>
            ) : (
              <Wordmark />
            )}
          </Link>
          <button
            type="button"
            onClick={toggleCollapsed}
            title={collapsed ? "Expand sidebar (⌘\\)" : "Collapse sidebar (⌘\\)"}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="grid h-8 w-8 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            {collapsed ? (
              <PanelLeftOpen className="h-4 w-4" />
            ) : (
              <PanelLeftClose className="h-4 w-4" />
            )}
          </button>
        </div>

        {/* ── Nav block ───────────────────────────────────────────────────── */}
        <div className="space-y-1 px-3">
          {collapsed ? (
            <Button
              variant="brand"
              size="icon"
              className="w-full"
              onClick={startNew}
              title="New chat"
              aria-label="New chat"
            >
              <Plus className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              variant="brand"
              className="w-full justify-start gap-2"
              onClick={startNew}
            >
              <Plus className="h-4 w-4" />
              New chat
            </Button>
          )}
          <NavItem
            href="/projects"
            icon={FolderKanban}
            label="Projects"
            active={pathname.startsWith("/projects")}
            collapsed={collapsed}
          />
          <NavItem
            href="/tasks"
            icon={ListTodo}
            label="Tasks"
            active={pathname.startsWith("/tasks")}
            collapsed={collapsed}
          />
        </div>

        {/* ── Chat list (hidden when collapsed) ───────────────────────────── */}
        {collapsed ? (
          <div className="flex-1" />
        ) : (
          <div className="mt-2 flex-1 overflow-y-auto px-3 pb-3">
            {isLoading ? (
              <div className="space-y-1 pt-2">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-8 animate-pulse rounded-md bg-muted" />
                ))}
              </div>
            ) : conversations && conversations.length > 0 ? (
              <>
                {pinned.length > 0 && (
                  <>
                    <p className="flex items-center gap-1 px-2 pb-1 pt-2 text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
                      <Pin className="h-3 w-3" />
                      Pinned
                    </p>
                    <div className="space-y-0.5">
                      {pinned.map((c) => (
                        <ConversationRow
                          key={c.id}
                          conversation={c}
                          active={pathname === `/chat/${c.id}`}
                          onDeleted={onDeleted(c.id)}
                        />
                      ))}
                    </div>
                  </>
                )}
                <p className="px-2 pb-1 pt-3 text-xs font-medium uppercase tracking-wider text-muted-foreground/70">
                  Chats
                </p>
                {rest.length > 0 ? (
                  <div className="space-y-0.5">
                    {rest.map((c) => (
                      <ConversationRow
                        key={c.id}
                        conversation={c}
                        active={pathname === `/chat/${c.id}`}
                        onDeleted={onDeleted(c.id)}
                      />
                    ))}
                  </div>
                ) : (
                  <p className="px-2 py-2 text-xs text-muted-foreground">
                    {pinned.length > 0 ? "No other chats." : "No conversations yet."}
                  </p>
                )}
              </>
            ) : (
              <p className="px-2 py-2 text-xs text-muted-foreground">
                No conversations yet.
              </p>
            )}
          </div>
        )}

        {/* ── Footer ──────────────────────────────────────────────────────── */}
        <div
          className={cn(
            "border-t border-border p-3",
            collapsed ? "flex flex-col items-center gap-3" : "space-y-3",
          )}
        >
          <BackendStatus compact={collapsed} />
          <Show when="signed-out">
            {collapsed ? (
              <SignInButton mode="modal" fallbackRedirectUrl="/chat">
                <button
                  type="button"
                  title="Sign in"
                  aria-label="Sign in"
                  className="grid h-8 w-8 place-items-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
                >
                  <LogIn className="h-4 w-4" />
                </button>
              </SignInButton>
            ) : (
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
            )}
          </Show>
          <Show when="signed-in">
            {collapsed ? (
              <UserButton />
            ) : (
              <div className="flex items-center gap-2 px-1">
                <UserButton />
                <span className="text-xs text-muted-foreground">Account</span>
              </div>
            )}
          </Show>
        </div>
      </aside>
    </>
  );
}
