"use client";

import { useQuery } from "@tanstack/react-query";
import { getHealth } from "@/lib/api";
import { cn } from "@/lib/utils";

export function BackendStatus({ compact = false }: { compact?: boolean }) {
  const { data, isError, isLoading } = useQuery({
    queryKey: ["health"],
    queryFn: getHealth,
    refetchInterval: 15_000,
  });

  const ok = data?.status === "ok" && !isError;
  const label = isLoading ? "connecting…" : ok ? "connected" : "offline";

  const dot = (
    <span
      className={cn(
        "h-2 w-2 shrink-0 rounded-full",
        isLoading ? "bg-yellow-400" : ok ? "bg-green-500" : "bg-red-500",
      )}
    />
  );

  if (compact) {
    return (
      <span title={`backend ${label}`} aria-label={`backend ${label}`}>
        {dot}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      {dot}
      backend {label}
    </div>
  );
}
