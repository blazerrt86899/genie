"use client";

import { useTaskStore, type TaskStatus } from "@/store/taskStore";
import { TaskCard } from "./TaskCard";

const COLUMNS: { status: TaskStatus; label: string }[] = [
  { status: "todo", label: "To Do" },
  { status: "in_progress", label: "In Progress" },
  { status: "done", label: "Done" },
];

export function TaskBoard() {
  const tasks = useTaskStore((s) => s.tasks);

  return (
    <div className="grid h-full grid-cols-3 gap-4 p-4">
      {COLUMNS.map((col) => {
        const colTasks = tasks.filter((t) => t.status === col.status);
        return (
          <div key={col.status} className="flex flex-col rounded-lg bg-muted p-3">
            <h2 className="mb-3 text-sm font-semibold">
              {col.label}
              <span className="ml-2 text-muted-foreground">
                {colTasks.length}
              </span>
            </h2>
            <div className="flex-1 space-y-2 overflow-y-auto">
              {colTasks.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No tasks. Task Creator agent lands in Phase 2.
                </p>
              ) : (
                colTasks.map((t) => <TaskCard key={t.id} task={t} />)
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
