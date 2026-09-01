"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  deleteDocument,
  documentStreamUrl,
  getDocument,
  listDocuments,
  uploadDocument,
  type DocumentDto,
} from "@/lib/api";

const key = (projectId: string) => ["documents", projectId] as const;

const IN_FLIGHT = (d: DocumentDto) => d.status === "queued" || d.status === "processing";

export function useDocuments(projectId: string) {
  const { getToken } = useAuth();
  return useQuery<DocumentDto[]>({
    queryKey: key(projectId),
    queryFn: async () => listDocuments(projectId, await getToken()),
    // poll while anything is still ingesting
    refetchInterval: (q) =>
      (q.state.data ?? []).some(IN_FLIGHT) ? 2000 : false,
  });
}

export function useUploadDocument(projectId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => uploadDocument(projectId, file, await getToken()),
    onSuccess: () => qc.invalidateQueries({ queryKey: key(projectId) }),
  });
}

export function useDeleteDocument(projectId: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => deleteDocument(id, await getToken()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: key(projectId) });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
    },
  });
}

export interface PipelineState {
  phase: DocumentDto["phase"];
  status: string;
  stats: DocumentDto["stats"];
  done: boolean;
}

/** Live pipeline progress for one document (SSE, with a polling fallback). */
export function useDocumentPipeline(id: string, active: boolean) {
  const { getToken } = useAuth();
  const [state, setState] = useState<PipelineState | null>(null);

  useEffect(() => {
    if (!active) return;
    let es: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let cancelled = false;

    (async () => {
      const token = await getToken();
      // EventSource can't send Authorization headers; fall back to polling when
      // the token is required. With the dev-user bypass the SSE path works.
      try {
        es = new EventSource(documentStreamUrl(id));
        es.onmessage = (e) => {
          const d = JSON.parse(e.data);
          if (d.type === "phase")
            setState({ phase: d.phase, status: d.status, stats: d.stats ?? {}, done: false });
          if (d.type === "done") setState((s) => (s ? { ...s, done: true } : s));
        };
        es.onerror = () => {
          es?.close();
          startPolling(token);
        };
      } catch {
        startPolling(token);
      }
    })();

    function startPolling(token: string | null) {
      if (poll || cancelled) return;
      poll = setInterval(async () => {
        try {
          const d = await getDocument(id, token);
          setState({
            phase: d.phase,
            status: d.status,
            stats: d.stats ?? {},
            done: d.status === "ready" || d.status === "failed",
          });
          if (d.status === "ready" || d.status === "failed") {
            clearInterval(poll!);
            poll = null;
          }
        } catch {
          /* keep trying */
        }
      }, 1500);
    }

    return () => {
      cancelled = true;
      es?.close();
      if (poll) clearInterval(poll);
    };
  }, [id, active, getToken]);

  return state;
}
