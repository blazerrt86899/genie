/**
 * Task list hook — STUB (Phase 2). TanStack Query against GET /api/v1/tasks
 * (currently 501). Optimistic updates + SSE `task_created` sync land in Phase 2.
 */

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Task } from "@/store/taskStore";

export function useTasks() {
  return useQuery<Task[]>({
    queryKey: ["tasks"],
    queryFn: () => apiFetch<Task[]>("/api/v1/tasks"),
    enabled: false, // flip on in Phase 2 once the endpoint exists
  });
}
