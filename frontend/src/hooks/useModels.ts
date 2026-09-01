"use client";

import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { listModels, type ModelsResponse } from "@/lib/api";

const KEY = ["models"] as const;

/** The chat-model catalog for the composer picker. Static per session. */
export function useModels() {
  const { getToken } = useAuth();
  return useQuery<ModelsResponse>({
    queryKey: KEY,
    queryFn: async () => listModels(await getToken()),
    staleTime: Infinity,
  });
}
