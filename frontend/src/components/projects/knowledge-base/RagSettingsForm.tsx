"use client";

import { useEffect, useState } from "react";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useUpdateProject } from "@/hooks/useProjects";
import type { ProjectDetail, RagSettings, SearchStrategy } from "@/lib/api";

const STRATEGIES: { key: SearchStrategy; label: string; hint: string }[] = [
  { key: "vector", label: "Vector Search", hint: "Semantic similarity matching" },
  { key: "hybrid", label: "Hybrid Search", hint: "Semantic + keyword matching" },
  { key: "multi_query_vector", label: "Multi-Query Vector", hint: "Multiple semantic queries" },
  { key: "multi_query_hybrid", label: "Multi-Query Hybrid", hint: "Multiple hybrid queries" },
];

function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <label className="text-sm">{label}</label>
        <span className="rounded bg-muted px-2 py-0.5 font-mono text-xs">{value}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-1 w-full accent-brand"
      />
      <div className="flex justify-between text-xs text-muted-foreground">
        <span>{min}</span>
        <span>{max}</span>
      </div>
    </div>
  );
}

export function RagSettingsForm({ project }: { project: ProjectDetail }) {
  const update = useUpdateProject(project.id);
  const [s, setS] = useState<RagSettings>(project.rag_settings);

  useEffect(() => setS(project.rag_settings), [project.rag_settings]);

  const dirty = JSON.stringify(s) !== JSON.stringify(project.rag_settings);
  const set = <K extends keyof RagSettings>(k: K, v: RagSettings[K]) =>
    setS((prev) => ({ ...prev, [k]: v }));
  const multi = s.search_strategy.startsWith("multi_query");

  return (
    <div className="space-y-6">
      <section>
        <div className="flex items-center gap-1.5">
          <label className="text-sm font-medium">Embedding Model</label>
          <Info className="h-3.5 w-3.5 text-muted-foreground" />
        </div>
        <select
          value={s.embedding_model}
          disabled={project.rag_locked}
          onChange={(e) => set("embedding_model", e.target.value)}
          className="mt-1 w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:opacity-60"
        >
          <option value="text-embedding-3-small">text-embedding-3-small</option>
        </select>
        {project.rag_locked && (
          <p className="mt-1 text-xs text-amber-500">Locked after first document upload</p>
        )}
      </section>

      <section>
        <p className="mb-2 text-sm font-medium">Search Strategy</p>
        <div className="space-y-2">
          {STRATEGIES.map((st) => (
            <button
              key={st.key}
              type="button"
              onClick={() => set("search_strategy", st.key)}
              className={cn(
                "flex w-full items-start gap-3 rounded-lg border px-3 py-2.5 text-left",
                s.search_strategy === st.key
                  ? "border-brand bg-brand/5"
                  : "border-border hover:bg-accent",
              )}
            >
              <span
                className={cn(
                  "mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded-full border",
                  s.search_strategy === st.key ? "border-brand" : "border-muted-foreground",
                )}
              >
                {s.search_strategy === st.key && (
                  <span className="h-2 w-2 rounded-full bg-brand" />
                )}
              </span>
              <span>
                <span className="block text-sm font-medium">{st.label}</span>
                <span className="block text-xs text-muted-foreground">{st.hint}</span>
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-4">
        <p className="text-sm font-medium">Search Parameters</p>
        <Slider
          label="Chunks per Search"
          value={s.chunks_per_search}
          min={5}
          max={30}
          onChange={(v) => set("chunks_per_search", v)}
        />
        <Slider
          label="Final Context Size"
          value={s.final_context_size}
          min={3}
          max={10}
          onChange={(v) => set("final_context_size", v)}
        />
        <Slider
          label="Similarity Threshold"
          value={s.similarity_threshold}
          min={0.1}
          max={0.9}
          step={0.05}
          onChange={(v) => set("similarity_threshold", v)}
        />
        {multi && (
          <Slider
            label="Number of Queries"
            value={s.num_queries}
            min={2}
            max={10}
            onChange={(v) => set("num_queries", v)}
          />
        )}
        <Slider
          label="Chunk Size (chars)"
          value={s.chunk_size}
          min={400}
          max={4000}
          step={100}
          onChange={(v) => set("chunk_size", v)}
        />
        <Slider
          label="Chunk Overlap (chars)"
          value={s.chunk_overlap}
          min={0}
          max={600}
          step={25}
          onChange={(v) => set("chunk_overlap", v)}
        />
      </section>

      <div className="flex justify-end">
        <Button
          variant="brand"
          size="sm"
          disabled={!dirty || update.isPending}
          onClick={() => update.mutate({ rag_settings: s })}
        >
          {update.isPending ? "Saving…" : "Save settings"}
        </Button>
      </div>
    </div>
  );
}
