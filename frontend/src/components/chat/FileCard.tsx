"use client";

import { useState } from "react";
import { useAuth } from "@clerk/nextjs";
import {
  Download,
  File as FileIcon,
  FileCode,
  FileSpreadsheet,
  FileText,
  Loader2,
} from "lucide-react";
import type { MessageFileView } from "@/lib/sse";
import { downloadFile } from "@/lib/api";

function iconFor(mime: string) {
  if (mime.includes("spreadsheet") || mime === "text/csv") return FileSpreadsheet;
  if (mime.includes("wordprocessing") || mime === "application/pdf" || mime === "text/markdown")
    return FileText;
  if (mime.includes("json") || mime.startsWith("text/x-") || mime === "text/plain")
    return FileCode;
  return FileIcon;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  const units = ["KB", "MB", "GB"];
  let v = n / 1024;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 10 ? 0 : 1)} ${units[i]}`;
}

function FileCardRow({ file }: { file: MessageFileView }) {
  const { getToken } = useAuth();
  const [downloading, setDownloading] = useState(false);
  const Icon = iconFor(file.mime_type);

  async function handleDownload() {
    if (downloading) return;
    setDownloading(true);
    try {
      await downloadFile(file.id, await getToken());
    } catch {
      /* the button just stops spinning — no toast system to hook into yet */
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-border bg-card px-3 py-2.5 text-sm">
      <span className="mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-md bg-muted text-muted-foreground">
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium text-foreground">{file.filename}</span>
        <span className="block truncate text-xs text-muted-foreground">
          {formatBytes(file.byte_size)}
          {file.summary ? ` · ${file.summary}` : ""}
        </span>
      </span>
      <button
        type="button"
        onClick={handleDownload}
        disabled={downloading}
        aria-label={`Download ${file.filename}`}
        className="mt-0.5 inline-flex shrink-0 items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-medium text-foreground transition-colors hover:border-brand/40 hover:bg-accent disabled:opacity-60"
      >
        {downloading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Download className="h-3.5 w-3.5" />
        )}
        Download
      </button>
    </div>
  );
}

export function FileCards({ files }: { files: MessageFileView[] }) {
  if (files.length === 0) return null;

  return (
    <div className="mt-3 flex max-w-[85%] flex-col gap-1.5">
      {files.map((f) => (
        <FileCardRow key={f.id} file={f} />
      ))}
    </div>
  );
}
