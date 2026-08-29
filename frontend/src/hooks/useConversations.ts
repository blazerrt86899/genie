"use client";

import { useAuth } from "@clerk/nextjs";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  deleteConversation,
  listConversations,
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

export function useDeleteConversation() {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (id: string) => deleteConversation(id, await getToken()),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  });
}
