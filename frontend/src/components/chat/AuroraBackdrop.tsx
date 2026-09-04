import { cn } from "@/lib/utils";

/**
 * The "nebula" moving backdrop — three slow-drifting violet/cyan blobs behind
 * the chat window. `subtle` dials it right down for an active conversation so
 * long answers stay readable; full intensity is the empty-chat showcase.
 * Pure CSS (see `globals.css` `.aurora-*`); freezes under `prefers-reduced-motion`.
 */
export function AuroraBackdrop({ subtle = false }: { subtle?: boolean }) {
  return (
    <div aria-hidden className={cn("aurora", subtle && "aurora--subtle")}>
      <div className="aurora-blob aurora-1" />
      <div className="aurora-blob aurora-2" />
      <div className="aurora-blob aurora-3" />
      {!subtle && <div className="aurora-center" />}
      <div className="aurora-veil" />
    </div>
  );
}
