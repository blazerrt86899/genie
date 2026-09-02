"use client";

import { useMemo, useState } from "react";
import {
  CalendarDays,
  Check,
  Copy,
  FileSignature,
  FileText,
  Mail,
  MessageSquare,
  StickyNote,
} from "lucide-react";
import { Markdown } from "./Markdown";

type Kind =
  | "email"
  | "letter"
  | "application"
  | "cover-letter"
  | "memo"
  | "proposal"
  | "message"
  | "agenda"
  | "note";

const META: Record<Kind, { label: string; icon: typeof Mail }> = {
  email: { label: "Email", icon: Mail },
  letter: { label: "Letter", icon: FileText },
  application: { label: "Application", icon: FileSignature },
  "cover-letter": { label: "Cover letter", icon: FileSignature },
  memo: { label: "Memo", icon: StickyNote },
  proposal: { label: "Proposal", icon: FileText },
  message: { label: "Message", icon: MessageSquare },
  agenda: { label: "Agenda", icon: CalendarDays },
  note: { label: "Note", icon: StickyNote },
};

interface Parsed {
  meta: Record<string, string>;
  body: string;
}

/** Split `key: value` lines before a lone `---` from the Markdown body. */
function parse(raw: string): Parsed {
  const lines = raw.replace(/\r\n/g, "\n").split("\n");
  const sep = lines.findIndex((l) => l.trim() === "---");
  if (sep === -1) {
    // still streaming (no `---` yet) — show everything as the body
    return { meta: {}, body: raw.trimStart() };
  }
  const meta: Record<string, string> = {};
  for (const line of lines.slice(0, sep)) {
    const m = /^([A-Za-z][\w-]*)\s*:\s*(.*)$/.exec(line.trim());
    if (m) meta[m[1].toLowerCase()] = m[2].trim();
  }
  return { meta, body: lines.slice(sep + 1).join("\n").replace(/^\n+/, "") };
}

export function DocumentCard({ raw }: { raw: string }) {
  const { meta, body } = useMemo(() => parse(raw), [raw]);
  const [copied, setCopied] = useState(false);

  const kind = (META[meta.kind as Kind] ? (meta.kind as Kind) : "note") as Kind;
  const { label, icon: Icon } = META[kind];
  const subject = meta.subject?.trim();
  const to = meta.to?.trim();

  const copyText =
    (kind === "email" || kind === "letter") && subject
      ? `Subject: ${subject}\n\n${body}`
      : body;

  async function copy() {
    try {
      await navigator.clipboard.writeText(copyText);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="my-4 overflow-hidden rounded-xl border border-border">
      <div className="flex items-center justify-between gap-3 border-b border-border bg-muted/50 px-4 py-2">
        <span className="inline-flex items-center gap-2 text-sm font-medium text-foreground">
          <Icon className="h-4 w-4 text-muted-foreground" />
          {label}
        </span>
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3" /> Copied
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" /> Copy
            </>
          )}
        </button>
      </div>

      {subject ? (
        <div className="flex gap-2 border-b border-border px-4 py-2 text-sm">
          <span className="shrink-0 text-muted-foreground">Subject:</span>
          <span className="font-medium text-foreground">{subject}</span>
        </div>
      ) : to ? (
        <div className="flex gap-2 border-b border-border px-4 py-2 text-sm">
          <span className="shrink-0 text-muted-foreground">To:</span>
          <span className="font-medium text-foreground">{to}</span>
        </div>
      ) : null}

      <div className="px-4 py-3">
        <Markdown>{body}</Markdown>
      </div>
    </div>
  );
}
