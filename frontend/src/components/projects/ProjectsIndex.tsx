"use client";

import { useState } from "react";
import Link from "next/link";
import { FolderKanban, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProjects } from "@/hooks/useProjects";
import { NewProjectDialog } from "./NewProjectDialog";

export function ProjectsIndex() {
  const { data: projects, isLoading } = useProjects();
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className="mx-auto max-w-4xl p-6 sm:p-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            A project keeps a set of chats together and shares custom
            instructions with all of them.
          </p>
        </div>
        <Button variant="brand" className="gap-2" onClick={() => setDialogOpen(true)}>
          <Plus className="h-4 w-4" />
          New project
        </Button>
      </div>

      <div className="mt-8">
        {isLoading ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-xl bg-muted" />
            ))}
          </div>
        ) : projects && projects.length > 0 ? (
          <div className="grid gap-4 sm:grid-cols-2">
            {projects.map((p) => (
              <Link
                key={p.id}
                href={`/projects/${p.id}`}
                className="group rounded-xl border border-border bg-card p-5 transition-colors hover:border-brand/40"
              >
                <div className="flex items-center gap-2">
                  <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand/10 text-brand">
                    <FolderKanban className="h-4 w-4" />
                  </span>
                  <span className="truncate font-medium">{p.name}</span>
                </div>
                {p.description && (
                  <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">
                    {p.description}
                  </p>
                )}
                <p className="mt-3 text-xs text-muted-foreground">
                  {p.conversation_count} chat
                  {p.conversation_count === 1 ? "" : "s"}
                </p>
              </Link>
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border p-10 text-center">
            <p className="text-sm text-muted-foreground">No projects yet.</p>
            <Button
              variant="brand"
              size="sm"
              className="mt-3 gap-2"
              onClick={() => setDialogOpen(true)}
            >
              <Plus className="h-4 w-4" />
              Create your first project
            </Button>
          </div>
        )}
      </div>

      <NewProjectDialog open={dialogOpen} onClose={() => setDialogOpen(false)} />
    </div>
  );
}
