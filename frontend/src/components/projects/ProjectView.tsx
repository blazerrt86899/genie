"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MessageSquarePlus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  useDeleteProject,
  useProject,
  useUpdateProject,
} from "@/hooks/useProjects";
import { KnowledgeBasePanel } from "./knowledge-base/KnowledgeBasePanel";

export function ProjectView({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { data: project, isLoading, isError } = useProject(projectId);
  const update = useUpdateProject(projectId);
  const del = useDeleteProject();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");

  useEffect(() => {
    if (project) {
      setName(project.name);
      setDescription(project.description ?? "");
      setInstructions(project.instructions ?? "");
    }
  }, [project]);

  if (isLoading) {
    return <div className="mx-auto max-w-3xl p-6 sm:p-10">Loading…</div>;
  }
  if (isError || !project) {
    return (
      <div className="mx-auto max-w-3xl p-6 sm:p-10 text-sm text-muted-foreground">
        Project not found.{" "}
        <Link href="/projects" className="text-brand hover:underline">
          Back to projects
        </Link>
      </div>
    );
  }

  const dirty =
    name.trim() !== project.name ||
    description !== (project.description ?? "") ||
    instructions !== (project.instructions ?? "");

  const save = () =>
    update.mutate({
      name: name.trim() || project.name,
      description: description || null,
      instructions: instructions || null,
    });

  const remove = () => {
    if (
      window.confirm(
        `Delete "${project.name}"? This also deletes its ${project.conversations.length} chat(s). This cannot be undone.`,
      )
    ) {
      del.mutate(projectId, { onSuccess: () => router.push("/projects") });
    }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-6 pb-16 sm:p-10 sm:pb-16">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-transparent text-2xl font-semibold tracking-tight outline-none"
          />
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Add a description…"
            className="mt-1 w-full bg-transparent text-sm text-muted-foreground outline-none"
          />
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={remove}
          className="shrink-0 text-muted-foreground hover:text-red-500"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>

      <section>
        <label className="text-sm font-medium" htmlFor="instructions">
          Instructions
        </label>
        <p className="text-xs text-muted-foreground">
          Genie follows these in every chat in this project.
        </p>
        <textarea
          id="instructions"
          value={instructions}
          onChange={(e) => setInstructions(e.target.value)}
          rows={6}
          placeholder="e.g. Always answer concisely. Assume the reader is a senior engineer. Prefer TypeScript examples."
          className="mt-2 w-full resize-y rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
        />
        <div className="mt-2 flex justify-end">
          <Button
            variant="brand"
            size="sm"
            onClick={save}
            disabled={!dirty || update.isPending}
          >
            {update.isPending ? "Saving…" : "Save"}
          </Button>
        </div>
      </section>

      <KnowledgeBasePanel project={project} />

      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium">
            Chats
            <span className="ml-2 text-muted-foreground">
              {project.conversations.length}
            </span>
          </h2>
          <Link
            href={`/chat?project=${project.id}`}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline"
          >
            <MessageSquarePlus className="h-4 w-4" />
            New chat in this project
          </Link>
        </div>
        <div className="mt-3 divide-y divide-border rounded-md border border-border">
          {project.conversations.length === 0 ? (
            <p className="p-4 text-sm text-muted-foreground">
              No chats in this project yet.
            </p>
          ) : (
            project.conversations.map((c) => (
              <Link
                key={c.id}
                href={`/chat/${c.id}`}
                className="block truncate px-4 py-3 text-sm hover:bg-accent"
              >
                {c.title || "New chat"}
              </Link>
            ))
          )}
        </div>
      </section>
    </div>
  );
}
