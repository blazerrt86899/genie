"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUploadDocument } from "@/hooks/useDocuments";

const ACCEPT = ".pdf,.md,.txt";

export function DocumentUpload({ projectId }: { projectId: string }) {
  const upload = useUploadDocument(projectId);
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(files: FileList | File[]) {
    setError(null);
    const list = Array.from(files);
    const results = await Promise.allSettled(list.map((f) => upload.mutateAsync(f)));
    const failed = results.filter((r) => r.status === "rejected");
    if (failed.length) {
      setError(
        `${failed.length} file(s) rejected — ${(failed[0] as PromiseRejectedResult).reason?.message ?? "upload failed"}`,
      );
    }
  }

  return (
    <div>
      <p className="mb-2 text-sm font-medium">Add sources</p>
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void handle(e.dataTransfer.files);
        }}
        className={cn(
          "flex w-full flex-col items-center gap-2 rounded-xl border-2 border-dashed px-4 py-10 text-center transition-colors",
          dragging ? "border-brand bg-brand/5" : "border-border hover:border-brand/50",
        )}
      >
        <span className="grid h-11 w-11 place-items-center rounded-lg border border-border bg-background">
          <Upload className="h-4 w-4 text-muted-foreground" />
        </span>
        <span className="text-sm font-medium">Drop files or click to upload</span>
        <span className="text-xs text-muted-foreground">PDF, MD, TXT · Max 25 MB</span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files?.length) void handle(e.target.files);
          e.target.value = "";
        }}
      />
      {upload.isPending && (
        <p className="mt-2 text-xs text-muted-foreground">Uploading…</p>
      )}
      {error && <p className="mt-2 text-xs text-red-500">{error}</p>}
    </div>
  );
}
