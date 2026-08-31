"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MessageSquare, Trash2 } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { Button } from "@/components/ui/button";
import { useDeleteTask, usePatchTask } from "@/hooks/useTasks";
import type { TaskDto } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = {
  todo: "To Do",
  in_progress: "In Progress",
  done: "Done",
  archived: "Archived",
};

export function TaskModal({
  task,
  onClose,
}: {
  task: TaskDto;
  onClose: () => void;
}) {
  const [description, setDescription] = useState(task.description ?? "");
  const patch = usePatchTask();
  const del = useDeleteTask();

  useEffect(() => setDescription(task.description ?? ""), [task]);

  const dirty = description !== (task.description ?? "");

  return (
    <Modal open onClose={onClose} title={task.title} className="max-w-lg">
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium">
            {STATUS_LABEL[task.status] ?? task.status}
          </span>
          {task.source_agent && (
            <span className="text-xs text-muted-foreground">
              added by {task.source_agent}
            </span>
          )}
        </div>

        {task.conversation_id && (
          <Link
            href={`/chat/${task.conversation_id}`}
            className="inline-flex items-center gap-1.5 rounded-md border border-brand/30 bg-brand/10 px-2.5 py-1 text-xs font-medium text-brand hover:bg-brand/20"
          >
            <MessageSquare className="h-3 w-3" />
            Open the chat this was discussed in
          </Link>
        )}

        <div>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={4}
            placeholder="Add details…"
            className="w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <p className="text-xs text-muted-foreground">
          Created {new Date(task.created_at).toLocaleString()}
        </p>

        <div className="flex items-center justify-between pt-1">
          <button
            type="button"
            onClick={() => {
              if (window.confirm(`Delete "${task.title}"?`)) {
                del.mutate(task.id, { onSuccess: onClose });
              }
            }}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-red-500"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Delete
          </button>
          <Button
            variant="brand"
            size="sm"
            disabled={!dirty || patch.isPending}
            onClick={() =>
              patch.mutate(
                { id: task.id, description: description.trim() || null },
                { onSuccess: onClose },
              )
            }
          >
            {patch.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
