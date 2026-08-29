"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MessagesSquare, ListTodo, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import { BackendStatus } from "@/components/BackendStatus";

const NAV = [
  { href: "/chat", label: "Chat", icon: MessagesSquare },
  { href: "/tasks", label: "Tasks", icon: ListTodo },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="flex w-56 flex-col border-r bg-card px-3 py-4">
      <div className="mb-6 flex items-center gap-2 px-2 text-lg font-semibold">
        <Sparkles className="h-5 w-5" />
        Genie
      </div>
      <nav className="flex flex-col gap-1">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              "flex items-center gap-2 rounded-md px-2 py-2 text-sm hover:bg-accent",
              pathname.startsWith(href) && "bg-accent font-medium",
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto px-2 pt-4">
        <BackendStatus />
      </div>
    </aside>
  );
}
