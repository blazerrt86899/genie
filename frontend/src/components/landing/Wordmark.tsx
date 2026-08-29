import { Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold", className)}>
      <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-brand to-brand-2 text-brand-foreground">
        <Sparkles className="h-4 w-4" />
      </span>
      <span className="text-lg tracking-tight">Genie</span>
    </span>
  );
}
