"use client";

import {
  Children,
  isValidElement,
  memo,
  type ComponentPropsWithoutRef,
  type ReactNode,
} from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import type { PluggableList } from "unified";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { CodeBlock } from "./CodeBlock";
import { DocumentCard } from "./DocumentCard";

const REMARK_PLUGINS: PluggableList = [remarkGfm];
const REHYPE_PLUGINS: PluggableList = [
  // `document` blocks are our own card format — never syntax-highlight them.
  [rehypeHighlight, { detect: true, ignoreMissing: true, plainText: ["document"] }],
];

function nodeText(node: ReactNode): string {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join("");
  if (typeof node === "object" && "props" in node) {
    return nodeText((node.props as { children?: ReactNode }).children);
  }
  return "";
}

const isHttp = (href = "") => /^https?:\/\//i.test(href);

// react-markdown v9 passes a `node` prop to every component — strip it before
// spreading onto a DOM element (React warns on unknown DOM props).
function strip<T extends { node?: unknown }>(p: T): Omit<T, "node"> {
  const rest: Record<string, unknown> = { ...p };
  delete rest.node;
  return rest as Omit<T, "node">;
}

const COMPONENTS: Components = {
  h1: (p) => <h2 className="mt-6 mb-2 text-lg font-semibold tracking-tight first:mt-0" {...strip(p)} />,
  h2: (p) => <h2 className="mt-6 mb-2 text-lg font-semibold tracking-tight first:mt-0" {...strip(p)} />,
  h3: (p) => <h3 className="mt-5 mb-2 text-base font-semibold tracking-tight first:mt-0" {...strip(p)} />,
  h4: (p) => <h4 className="mt-4 mb-1.5 text-sm font-semibold tracking-tight first:mt-0" {...strip(p)} />,
  p: (p) => <p className="my-3 leading-relaxed first:mt-0 last:mb-0" {...strip(p)} />,
  ul: (p) => <ul className="my-3 ml-5 list-disc space-y-1 first:mt-0 last:mb-0" {...strip(p)} />,
  ol: (p) => <ol className="my-3 ml-5 list-decimal space-y-1 first:mt-0 last:mb-0" {...strip(p)} />,
  li: (p) => <li className="leading-relaxed" {...strip(p)} />,
  hr: () => <hr className="my-6 border-border" />,
  strong: (p) => <strong className="font-semibold text-foreground" {...strip(p)} />,
  blockquote: (p) => (
    <blockquote
      className="my-3 border-l-2 border-brand/40 pl-3 text-muted-foreground [&>p]:my-1"
      {...strip(p)}
    />
  ),
  a: ({ href, children }: ComponentPropsWithoutRef<"a">) =>
    isHttp(href) ? (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="font-medium text-brand underline-offset-2 hover:underline"
      >
        {children}
      </a>
    ) : (
      <span>{children}</span>
    ),
  table: (p) => (
    <div className="my-4 overflow-x-auto">
      <table className="w-full border-collapse text-sm" {...strip(p)} />
    </div>
  ),
  th: (p) => (
    <th
      className="border border-border bg-muted px-3 py-1.5 text-left font-medium"
      {...strip(p)}
    />
  ),
  td: (p) => <td className="border border-border px-3 py-1.5 align-top" {...strip(p)} />,
  pre: ({ children }) => {
    const code = Children.toArray(children).find(isValidElement) as
      | React.ReactElement<{ className?: string; children?: ReactNode }>
      | undefined;
    const cls = code?.props.className ?? "";
    const text = nodeText(code?.props.children ?? children);
    // our own draft-card format — `document` fence, or a mangled class that
    // still starts with `kind:` metadata
    if (/language-document/.test(cls) || /^\s*kind:\s*\S/.test(text)) {
      return <DocumentCard raw={text} />;
    }
    return <CodeBlock>{children}</CodeBlock>;
  },
  code: ({ className, children }: ComponentPropsWithoutRef<"code">) => {
    const block = /language-/.test(className ?? "") || nodeText(children).includes("\n");
    if (block) {
      return <code className={className}>{children}</code>;
    }
    return (
      <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.85em] text-foreground">
        {children}
      </code>
    );
  },
};

/** Renders a Genie reply as rich Markdown (GFM tables, fenced code + copy). */
export const Markdown = memo(function Markdown({ children }: { children: string }) {
  return (
    <div className="text-[15px] text-foreground">
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        rehypePlugins={REHYPE_PLUGINS}
        components={COMPONENTS}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
});
