"use client";

import { useState } from "react";
import { FileText, Settings } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ProjectDetail } from "@/lib/api";
import { DocumentUpload } from "./DocumentUpload";
import { DocumentList } from "./DocumentList";
import { RagSettingsForm } from "./RagSettingsForm";

export function KnowledgeBasePanel({ project }: { project: ProjectDetail }) {
  const [tab, setTab] = useState<"documents" | "settings">("documents");

  return (
    <section className="rounded-xl border border-border">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="grid h-6 w-6 place-items-center rounded-md bg-brand/10 text-brand">
            <FileText className="h-3.5 w-3.5" />
          </span>
          <h2 className="text-sm font-semibold">Knowledge Base</h2>
        </div>
        <span className="text-xs text-muted-foreground">
          {project.document_count} source{project.document_count === 1 ? "" : "s"}
        </span>
      </div>

      <div className="flex border-b border-border text-sm">
        {(["documents", "settings"] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={cn(
              "flex items-center gap-1.5 px-4 py-2.5 capitalize",
              tab === t
                ? "border-b-2 border-brand font-medium text-brand"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t === "documents" ? (
              <FileText className="h-3.5 w-3.5" />
            ) : (
              <Settings className="h-3.5 w-3.5" />
            )}
            {t}
          </button>
        ))}
      </div>

      <div className="space-y-6 p-4">
        {tab === "documents" ? (
          <>
            <DocumentUpload projectId={project.id} />
            <DocumentList projectId={project.id} />
          </>
        ) : (
          <RagSettingsForm project={project} />
        )}
      </div>
    </section>
  );
}
