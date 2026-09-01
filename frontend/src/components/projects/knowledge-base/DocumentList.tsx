"use client";

import { useState } from "react";
import { FileText, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useDeleteDocument, useDocuments } from "@/hooks/useDocuments";
import type { DocumentDto } from "@/lib/api";
import { PipelineModal } from "./PipelineModal";

const PHASE_LABEL: Record<DocumentDto["phase"], string> = {
  upload: "queued",
  partition: "partitioning…",
  chunk: "chunking…",
  vectorize: "vectorizing…",
  store: "storing…",
  done: "ready",
};

function pill(d: DocumentDto): { text: string; cls: string } {
  if (d.status === "failed") return { text: "failed", cls: "text-red-500 bg-red-400/10" };
  if (d.status === "ready")
    return {
      text: `ready · ${d.chunk_count} chunks`,
      cls: "text-emerald-500 bg-emerald-400/10",
    };
  return { text: PHASE_LABEL[d.phase], cls: "text-brand bg-brand/10" };
}

export function DocumentList({ projectId }: { projectId: string }) {
  const { data: docs, isLoading } = useDocuments(projectId);
  const del = useDeleteDocument(projectId);
  const [open, setOpen] = useState<DocumentDto | null>(null);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-medium">Sources</p>
        <span className="rounded bg-muted px-1.5 text-xs text-muted-foreground">
          {docs?.length ?? 0}
        </span>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : !docs?.length ? (
        <div className="rounded-lg border border-dashed border-border py-10 text-center">
          <FileText className="mx-auto h-6 w-6 text-muted-foreground/60" />
          <p className="mt-2 text-sm text-muted-foreground">No sources added yet</p>
          <p className="text-xs text-muted-foreground/70">
            Upload files to get started
          </p>
        </div>
      ) : (
        <ul className="divide-y divide-border rounded-lg border border-border">
          {docs.map((d) => {
            const p = pill(d);
            return (
              <li key={d.id} className="flex items-center gap-3 px-3 py-2.5 text-sm">
                <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
                <button
                  type="button"
                  onClick={() => setOpen(d)}
                  className="min-w-0 flex-1 truncate text-left hover:underline"
                >
                  {d.filename}
                </button>
                <span className={cn("rounded px-1.5 py-0.5 text-xs", p.cls)}>{p.text}</span>
                <button
                  type="button"
                  aria-label="Delete"
                  onClick={() => {
                    if (window.confirm(`Delete "${d.filename}" from the knowledge base?`))
                      del.mutate(d.id);
                  }}
                  className="shrink-0 text-muted-foreground hover:text-red-500"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {open && <PipelineModal document={open} onClose={() => setOpen(null)} />}
    </div>
  );
}
