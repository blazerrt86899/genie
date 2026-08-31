"use client";

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  archiveDoneTasks,
  deleteTask,
  listTasks,
  patchTask,
  type TaskDto,
} from "@/lib/api";

const KEY = (includeArchived: boolean) => ["tasks", includeArchived] as const;

export function useTasks(includeArchived = false) {
  const { getToken } = useAuth();
  return useQuery<TaskDto[]>({
    queryKey: KEY(includeArchived),
    queryFn: async () => listTasks(await getToken(), includeArchived),
    staleTime: 5_000,
    refetchOnWindowFocus: true,
  });
}

function useInvalidateTasks() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["tasks"] });
}

export function usePatchTask() {
  const { getToken } = useAuth();
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: async (vars: {
      id: string;
      title?: string;
      description?: string | null;
      status?: string;
    }) => {
      const { id, ...body } = vars;
      return patchTask(id, body, await getToken());
    },
    onSuccess: invalidate,
  });
}

export function useArchiveDone() {
  const { getToken } = useAuth();
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: async () => archiveDoneTasks(await getToken()),
    onSuccess: invalidate,
  });
}

export function useDeleteTask() {
  const { getToken } = useAuth();
  const invalidate = useInvalidateTasks();
  return useMutation({
    mutationFn: async (id: string) => deleteTask(id, await getToken()),
    onSuccess: invalidate,
  });
}
