"use client";

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createProject,
  deleteProject,
  getProject,
  listProjects,
  updateProject,
  type ProjectDetail,
  type ProjectInput,
  type ProjectSummary,
} from "@/lib/api";

const LIST = ["projects"] as const;
const one = (id: string) => ["project", id] as const;

export function useProjects() {
  const { getToken } = useAuth();
  return useQuery<ProjectSummary[]>({
    queryKey: LIST,
    queryFn: async () => listProjects(await getToken()),
    staleTime: 10_000,
  });
}

export function useProject(id: string) {
  const { getToken } = useAuth();
  return useQuery<ProjectDetail>({
    queryKey: one(id),
    queryFn: async () => getProject(id, await getToken()),
  });
}

export function useCreateProject() {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ProjectInput) => createProject(body, await getToken()),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST }),
  });
}

export function useUpdateProject(id: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (body: ProjectInput) =>
      updateProject(id, body, await getToken()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: LIST });
      qc.invalidateQueries({ queryKey: one(id) });
    },
  });
}

export function useDeleteProject() {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => deleteProject(id, await getToken()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: LIST });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}
