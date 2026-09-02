"use client";

import { Children, isValidElement, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";

const LABELS: Record<string, string> = {
  js: "JavaScript",
  jsx: "JavaScript",
  ts: "TypeScript",
  tsx: "TypeScript",
  py: "Python",
  python: "Python",
  sh: "Shell",
  bash: "Bash",
  zsh: "Shell",
  shell: "Shell",
  json: "JSON",
  yaml: "YAML",
  yml: "YAML",
  sql: "SQL",
  html: "HTML",
  xml: "XML",
  css: "CSS",
  md: "Markdown",
  markdown: "Markdown",
  dockerfile: "Dockerfile",
  hcl: "HCL",
  tf: "Terraform",
  go: "Go",
  rust: "Rust",
  rs: "Rust",
  java: "Java",
  kotlin: "Kotlin",
  rb: "Ruby",
  ruby: "Ruby",
  php: "PHP",
  c: "C",
  cpp: "C++",
  csharp: "C#",
  cs: "C#",
  diff: "Diff",
  ini: "INI",
  toml: "TOML",
  graphql: "GraphQL",
  text: "Text",
  plaintext: "Text",
};

/** Concatenate the text of an arbitrarily nested React children tree. */
function nodeText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (isValidElement(node)) {
    return nodeText((node.props as { children?: ReactNode }).children);
  }
  return "";
}

/**
 * Renders a fenced code block: a header bar (language label + copy button) above
 * the `<pre><code>` that `rehype-highlight` has already tokenised into
 * `hljs-*` spans.
 */
export function CodeBlock({ children }: { children: ReactNode }) {
  const [copied, setCopied] = useState(false);

  // react-markdown hands us the single <code> child of the <pre>.
  const code = Children.toArray(children).find(isValidElement) as
    | React.ReactElement<{ className?: string; children?: ReactNode }>
    | undefined;

  const className = code?.props.className ?? "";
  const lang = /language-(\w[\w+-]*)/.exec(className)?.[1]?.toLowerCase() ?? "";
  const label = LABELS[lang] ?? (lang ? lang.toUpperCase() : "Text");
  const raw = nodeText(code?.props.children ?? children);

  async function copy() {
    try {
      await navigator.clipboard.writeText(raw);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* clipboard unavailable */
    }
  }

  return (
    <div className="my-4 overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between border-b border-border bg-muted px-3 py-1.5">
        <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
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
      <pre className="overflow-x-auto bg-[var(--code-bg)] p-3 text-[13px] leading-relaxed text-[var(--code-fg)]">
        {code ?? <code>{children}</code>}
      </pre>
    </div>
  );
}
