"use client";

import { useMemo, useState } from "react";
import { Archive, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useArchiveDone, usePatchTask, useTasks } from "@/hooks/useTasks";
import type { TaskDto } from "@/lib/api";
import { TaskCard } from "./TaskCard";
import { TaskModal } from "./TaskModal";

const COLUMNS: { status: TaskDto["status"]; label: string }[] = [
  { status: "todo", label: "To Do" },
  { status: "in_progress", label: "In Progress" },
  { status: "done", label: "Done" },
];

export function TaskBoard() {
  const { data: tasks = [], isLoading } = useTasks(true); // include archived; split below
  const patch = usePatchTask();
  const archiveDone = useArchiveDone();
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [open, setOpen] = useState<TaskDto | null>(null);
  const [showArchived, setShowArchived] = useState(false);

  const board = useMemo(
    () => tasks.filter((t) => t.status !== "archived"),
    [tasks],
  );
  const archived = useMemo(
    () => tasks.filter((t) => t.status === "archived"),
    [tasks],
  );
  const doneCount = board.filter((t) => t.status === "done").length;

  function drop(status: TaskDto["status"], e: React.DragEvent) {
    e.preventDefault();
    setDragOver(null);
    const id = e.dataTransfer.getData("text/task-id");
    const task = tasks.find((t) => t.id === id);
    if (task && task.status !== status) patch.mutate({ id, status });
  }

  return (
    <div className="flex h-full flex-col p-4">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-lg font-semibold">Tasks</h1>
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          disabled={doneCount === 0 || archiveDone.isPending}
          onClick={() => archiveDone.mutate()}
        >
          <Archive className="h-3.5 w-3.5" />
          Archive done{doneCount > 0 ? ` (${doneCount})` : ""}
        </Button>
      </div>

      <div className="grid flex-1 grid-cols-3 gap-4">
        {COLUMNS.map((col) => {
          const colTasks = board.filter((t) => t.status === col.status);
          return (
            <div
              key={col.status}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(col.status);
              }}
              onDragLeave={() => setDragOver(null)}
              onDrop={(e) => drop(col.status, e)}
              className={`flex flex-col rounded-lg border p-3 transition-colors ${
                dragOver === col.status
                  ? "border-brand/50 bg-brand/5"
                  : "border-transparent bg-muted"
              }`}
            >
              <h2 className="mb-3 text-sm font-semibold">
                {col.label}
                <span className="ml-2 text-muted-foreground">
                  {colTasks.length}
                </span>
              </h2>
              <div className="flex-1 space-y-2 overflow-y-auto">
                {isLoading ? (
                  <div className="h-16 animate-pulse rounded-md bg-background/60" />
                ) : colTasks.length === 0 ? (
                  <p className="text-xs text-muted-foreground">
                    Nothing here. Ask Genie to “add … to my todo”.
                  </p>
                ) : (
                  colTasks.map((t) => (
                    <TaskCard key={t.id} task={t} onOpen={() => setOpen(t)} />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>

      {archived.length > 0 && (
        <div className="mt-3 rounded-lg border border-border">
          <button
            type="button"
            onClick={() => setShowArchived((v) => !v)}
            className="flex w-full items-center gap-1.5 px-3 py-2 text-xs font-medium text-muted-foreground hover:text-foreground"
          >
            <ChevronDown
              className={`h-3.5 w-3.5 transition-transform ${
                showArchived ? "" : "-rotate-90"
              }`}
            />
            Archived ({archived.length})
          </button>
          {showArchived && (
            <div className="space-y-1 border-t border-border p-2">
              {archived.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setOpen(t)}
                  className="block w-full truncate rounded px-2 py-1 text-left text-xs text-muted-foreground hover:bg-accent"
                >
                  {t.title}
                  {t.archived_at && (
                    <span className="ml-2 text-muted-foreground/60">
                      {new Date(t.archived_at).toLocaleDateString()}
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {open && <TaskModal task={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
