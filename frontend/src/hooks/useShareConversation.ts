"use client";

import { useAuth } from "@clerk/nextjs";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getConversationShare,
  shareConversation,
  unshareConversation,
  type ShareInfo,
} from "@/lib/api";

const key = (id: string) => ["share", id] as const;

/** Current public-link state for a conversation (null = private). */
export function useConversationShare(id: string | undefined) {
  const { getToken } = useAuth();
  return useQuery<ShareInfo | null>({
    queryKey: key(id ?? "none"),
    queryFn: async () => getConversationShare(id as string, await getToken()),
    enabled: !!id,
    staleTime: 30_000,
  });
}

export function useEnableShare(id: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => shareConversation(id, await getToken()),
    onSuccess: (info) => qc.setQueryData(key(id), info),
  });
}

export function useDisableShare(id: string) {
  const { getToken } = useAuth();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async () => unshareConversation(id, await getToken()),
    onSuccess: () => qc.setQueryData(key(id), null),
  });
}
