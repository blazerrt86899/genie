"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";
import { useCreateProject } from "@/hooks/useProjects";

export function NewProjectDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const router = useRouter();
  const create = useCreateProject();
  const [name, setName] = useState("");

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) return;
    const project = await create.mutateAsync({ name: trimmed });
    setName("");
    onClose();
    router.push(`/projects/${project.id}`);
  }

  return (
    <Modal open={open} onClose={onClose} title="New project">
      <label className="text-sm font-medium" htmlFor="project-name">
        Project name
      </label>
      <input
        id="project-name"
        autoFocus
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && submit()}
        placeholder="e.g. Q3 Marketing"
        className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
      />
      <p className="mt-2 text-xs text-muted-foreground">
        You&apos;ll add a description and instructions on the next screen.
      </p>
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onClose}>
          Cancel
        </Button>
        <Button
          variant="brand"
          size="sm"
          onClick={submit}
          disabled={!name.trim() || create.isPending}
        >
          Create
        </Button>
      </div>
    </Modal>
  );
}
