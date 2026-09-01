"use client";

import { Check, Loader2, X } from "lucide-react";
import { Modal } from "@/components/ui/modal";
import { cn } from "@/lib/utils";
import { useDocumentPipeline } from "@/hooks/useDocuments";
import type { DocumentDto } from "@/lib/api";
import { ChunkViewer } from "./ChunkViewer";

const STEPS: { key: DocumentDto["phase"]; label: string }[] = [
  { key: "upload", label: "Upload" },
  { key: "partition", label: "Partitioning" },
  { key: "chunk", label: "Chunking" },
  { key: "vectorize", label: "Vectorization" },
  { key: "store", label: "Storage" },
  { key: "done", label: "View Chunks" },
];

const ELEMENT_LABEL: Record<string, string> = {
  text: "Text sections",
  titles: "Titles / Headers",
  tables: "Tables",
  images: "Images",
  other: "Other elements",
};

export function PipelineModal({
  document: doc,
  onClose,
}: {
  document: DocumentDto;
  onClose: () => void;
}) {
  const live = useDocumentPipeline(
    doc.id,
    doc.status === "queued" || doc.status === "processing",
  );
  const phase = live?.phase ?? doc.phase;
  const status = live?.status ?? doc.status;
  const stats = live?.stats ?? doc.stats;
  const failed = status === "failed";
  const ready = status === "ready" || phase === "done";

  const activeIdx = STEPS.findIndex((s) => s.key === phase);
  const elements = stats.elements ?? {};

  return (
    <Modal open onClose={onClose} title={doc.filename} className="max-w-2xl">
      <ol className="mb-5 flex flex-wrap gap-x-4 gap-y-1 text-sm">
        {STEPS.map((s, i) => {
          const state =
            failed && i === activeIdx
              ? "failed"
              : i < activeIdx || ready
                ? "done"
                : i === activeIdx
                  ? "active"
                  : "todo";
          return (
            <li
              key={s.key}
              className={cn(
                "flex items-center gap-1.5",
                state === "active" && "font-medium text-brand",
                state === "done" && "text-foreground",
                state === "failed" && "text-red-500",
                state === "todo" && "text-muted-foreground/60",
              )}
            >
              {state === "done" && <Check className="h-3.5 w-3.5" />}
              {state === "active" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {state === "failed" && <X className="h-3.5 w-3.5" />}
              {s.label}
            </li>
          );
        })}
      </ol>

      {failed && (
        <p className="rounded-lg border border-red-400/40 bg-red-400/10 p-3 text-sm text-red-500">
          Processing failed{doc.error ? `: ${doc.error}` : ""}.
        </p>
      )}

      {!failed && Object.keys(elements).length > 0 && (
        <div>
          <p className="mb-2 text-sm font-medium">📊 Elements Discovered</p>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(elements).map(([k, v]) => (
              <div
                key={k}
                className="flex items-center justify-between rounded-lg border border-border bg-background px-3 py-2 text-sm"
              >
                <span className="text-muted-foreground">{ELEMENT_LABEL[k] ?? k}</span>
                <span className="font-mono">{v}</span>
              </div>
            ))}
          </div>
          {stats.chunk_count != null && (
            <p className="mt-2 text-xs text-muted-foreground">
              {stats.chunk_count} chunks
            </p>
          )}
        </div>
      )}

      {ready && !failed && (
        <div className="mt-5 max-h-80 overflow-y-auto">
          <ChunkViewer documentId={doc.id} />
        </div>
      )}
    </Modal>
  );
}
