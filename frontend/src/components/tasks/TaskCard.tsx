import type { Task } from "@/store/taskStore";

export function TaskCard({ task }: { task: Task }) {
  return (
    <div className="rounded-md border bg-background p-3 text-sm shadow-sm">
      <p className="font-medium">{task.title}</p>
      {task.description && (
        <p className="mt-1 text-xs text-muted-foreground">{task.description}</p>
      )}
    </div>
  );
}
