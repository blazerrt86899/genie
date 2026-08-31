"use client";

import { MessageSquare } from "lucide-react";
import type { TaskDto } from "@/lib/api";

export function TaskCard({
  task,
  onOpen,
  draggable = true,
}: {
  task: TaskDto;
  onOpen?: () => void;
  draggable?: boolean;
}) {
  return (
    <div
      draggable={draggable}
      onDragStart={(e) => e.dataTransfer.setData("text/task-id", task.id)}
      onClick={onOpen}
      className="cursor-pointer rounded-md border border-border bg-background p-3 text-sm shadow-sm transition-colors hover:border-brand/40"
    >
      <p className="font-medium">{task.title}</p>
      {task.description && (
        <p className="mt-1 line-clamp-2 text-xs text-muted-foreground">
          {task.description}
        </p>
      )}
      {task.conversation_id && (
        <span className="mt-2 inline-flex items-center gap-1 text-[11px] text-muted-foreground/70">
          <MessageSquare className="h-3 w-3" />
          from a chat
        </span>
      )}
    </div>
  );
}
