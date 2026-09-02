import { ArrowUpRight } from "lucide-react";

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

// These render on the public shared-chat page — only follow real web links.
const safe = (url: string) => /^https?:\/\//i.test(url);

export function SourceCards({
  sources,
}: {
  sources: { title: string; url: string }[];
}) {
  if (sources.length === 0) return null;

  return (
    <div className="mt-3 max-w-[85%]">
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/70">
        Sources
      </p>
      <div className="flex flex-col gap-1.5">
        {sources.map((s, i) => {
          const clickable = safe(s.url);
          const inner = (
            <>
              <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded bg-muted text-[10px] font-medium text-muted-foreground">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium text-foreground">
                  {s.title}
                </span>
                <span className="block truncate text-xs text-muted-foreground">
                  {host(s.url)}
                </span>
              </span>
              {clickable && (
                <ArrowUpRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground/50 group-hover:text-brand" />
              )}
            </>
          );
          const className =
            "group flex items-start gap-2 rounded-lg border border-border bg-card px-3 py-2 text-sm transition-colors hover:border-brand/40 hover:bg-accent";
          return clickable ? (
            <a
              key={i}
              href={s.url}
              target="_blank"
              rel="noopener noreferrer"
              className={className}
            >
              {inner}
            </a>
          ) : (
            <div key={i} className={className}>
              {inner}
            </div>
          );
        })}
      </div>
    </div>
  );
}
