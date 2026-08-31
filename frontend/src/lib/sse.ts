/**
 * SSE event parsing + dispatch (CLAUDE.md §11).
 * Keep the event union in sync with backend `app/core/streaming.py`.
 */

export interface PlanStepView {
  id: string;
  description: string;
  agent: string;
  status: "pending" | "in_progress" | "done" | "failed";
  depends_on: string[];
  result: string | null;
  error: string | null;
}

export type SseEvent =
  | { type: "agent_start"; agent: string; run_id: string }
  | { type: "token"; content: string }
  | { type: "agent_end"; agent: string; status: string }
  | { type: "plan"; steps: PlanStepView[] }
  | { type: "task_created"; task: Record<string, unknown> }
  | { type: "title"; conversation_id: string; title: string }
  | { type: "interrupt"; reason: string; details: Record<string, unknown> }
  | { type: "error"; message: string; code: string }
  | {
      type: "done";
      total_tokens: number;
      run_id: string;
      langsmith_run_id?: string;
      title?: string;
    };

export type SseHandler = (event: SseEvent) => void;

/**
 * Consume a `fetch` streaming body as SSE frames. Returns when the stream ends
 * or a `done` / `error` event is received.
 */
export async function parseSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: SseHandler,
): Promise<void> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";

    for (const frame of frames) {
      const line = frame.split("\n").find((l) => l.startsWith("data:"));
      if (!line) continue;
      try {
        const event = JSON.parse(line.slice(5).trim()) as SseEvent;
        onEvent(event);
        if (event.type === "done" || event.type === "error") return;
      } catch {
        // ignore malformed frame
      }
    }
  }
}
