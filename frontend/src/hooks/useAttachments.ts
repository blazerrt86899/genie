"use client";

import { useAuth } from "@clerk/nextjs";
import { deleteAttachment, uploadAttachment } from "@/lib/api";
import { useChatStore } from "@/store/chatStore";

const KIND_FROM_NAME = (name: string): string =>
  name.toLowerCase().endsWith(".pdf")
    ? "pdf"
    : name.toLowerCase().endsWith(".md")
      ? "md"
      : "txt";

/** Upload a file, tracking it as a chip in `chatStore.pendingAttachments`. */
export function useUploadAttachment() {
  const { getToken } = useAuth();
  const store = useChatStore;

  return async (file: File) => {
    const tempId = crypto.randomUUID();
    store.getState().addPendingAttachment({
      id: tempId,
      filename: file.name,
      kind: KIND_FROM_NAME(file.name),
      status: "uploading",
    });
    try {
      const dto = await uploadAttachment(file, await getToken());
      // swap temp id → real id
      store.getState().removePendingAttachment(tempId);
      store.getState().addPendingAttachment({
        id: dto.id,
        filename: dto.filename,
        kind: dto.kind,
        status: "ready",
      });
    } catch {
      store.getState().updatePendingAttachment(tempId, { status: "error" });
    }
  };
}

export function useDeleteAttachment() {
  const { getToken } = useAuth();
  return async (id: string) => {
    useChatStore.getState().removePendingAttachment(id);
    try {
      await deleteAttachment(id, await getToken());
    } catch {
      /* orphaned rows are harmless */
    }
  };
}
