"use client";

import { useQuery } from "@tanstack/react-query";
import { useAuth } from "@clerk/nextjs";
import { listChunks, type ChunkDto } from "@/lib/api";

export function ChunkViewer({ documentId }: { documentId: string }) {
  const { getToken } = useAuth();
  const { data, isLoading } = useQuery<ChunkDto[]>({
    queryKey: ["chunks", documentId],
    queryFn: async () => listChunks(documentId, await getToken(), { limit: 200 }),
  });

  if (isLoading) return <p className="text-sm text-muted-foreground">Loading chunks…</p>;
  if (!data?.length)
    return <p className="text-sm text-muted-foreground">No chunks.</p>;

  return (
    <div className="space-y-2">
      <p className="text-xs text-muted-foreground">{data.length} chunks</p>
      {data.map((c) => (
        <details
          key={c.chunk_index}
          className="rounded-lg border border-border bg-background p-3 text-sm"
        >
          <summary className="cursor-pointer list-none">
            <span className="mr-2 font-mono text-xs text-muted-foreground">
              #{c.chunk_index}
            </span>
            <span className="text-xs text-muted-foreground">
              {c.token_count} tok
              {c.metadata.page != null && ` · p.${c.metadata.page}`}
              {c.metadata.element_types?.length
                ? ` · ${c.metadata.element_types.join(", ")}`
                : ""}
              {c.metadata.heading ? ` · ${c.metadata.heading}` : ""}
            </span>
            <span className="mt-1 line-clamp-2 text-foreground/80">{c.content}</span>
          </summary>
          <p className="mt-2 whitespace-pre-wrap border-t border-border pt-2 text-foreground/90">
            {c.content}
          </p>
        </details>
      ))}
    </div>
  );
}
