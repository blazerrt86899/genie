"use client";

import { useAuth } from "@clerk/nextjs";
import { useQuery } from "@tanstack/react-query";
import { getUsage, type UsageInfo } from "@/lib/api";

export function useUsage(enabled = true) {
  const { getToken } = useAuth();
  return useQuery<UsageInfo>({
    queryKey: ["usage"],
    queryFn: async () => getUsage(await getToken()),
    staleTime: 60_000,
    enabled,
  });
}
