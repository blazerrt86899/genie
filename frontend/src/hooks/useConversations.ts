"use client";

import { useAuth } from "@clerk/nextjs";
import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  deleteConversation,
  listConversations,
  patchConversation,
  searchConversations,
  type ConversationSearchResult,
  type ConversationSummary,
} from "@/lib/api";

const KEY = ["conversations"] as const;

export function useConversations() {
  const { getToken } = useAuth();
  return useQuery<ConversationSummary[]>({
    queryKey: KEY,
    queryFn: async () => listConversations(await getToken()),
    staleTime: 10_000,
  });
}

export function useSearchConversations(q: string) {
  const { getToken } = useAuth();
  const query = q.trim();
  return useQuery<ConversationSearchResult[]>({
    queryKey: [...KEY, "search", query],
    queryFn: async () => searchConversations(query, await getToken()),
    enabled: query.length >= 2,
    staleTime: 30_000,
    placeholderData: keepPreviousData,
  });
}

export function useDeleteConversation() {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => deleteConversation(id, await getToken()),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function usePatchConversation() {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      id,
      body,
    }: {
      id: string;
      body: {
        title?: string;
        project_id?: string | null;
        pinned?: boolean;
        unread?: boolean;
      };
    }) => patchConversation(id, body, await getToken()),
    onSuccess: (_data, { body }) => {
      qc.invalidateQueries({ queryKey: KEY });
      qc.invalidateQueries({ queryKey: ["projects"] });
      if (body.project_id)
        qc.invalidateQueries({ queryKey: ["project", body.project_id] });
    },
  });
}
