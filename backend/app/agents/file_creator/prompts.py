"""File Creator agent prompts (CLAUDE.md §12)."""

from __future__ import annotations

FILE_SPEC_PROMPT = """\
Decide the filename and format for a file the user asked Genie to create.
Base it on their request below — the words they used ("PDF", "Word doc",
"spreadsheet", "CSV", "a Python script", …) — and default to 'md' when no
format is implied.

Request: {request}
"""

FILE_CONTENT_PROMPT = """\
You are Genie's document writer. Write the full body of a file the user asked
for, using the context below (their request, and any research findings from
other steps this turn).

- Write in Markdown (headings, paragraphs, bullet lists, a pipe table where
  tabular data fits) — it will be converted to the requested format
  automatically. EXCEPTION: if the target format is 'csv' or 'json', write
  ONLY the raw CSV or JSON content — no Markdown, no code fence, no commentary.
- Be complete and self-contained — this is the whole file, not a preview.
- No preamble like "Here's your document" — start directly with the content.

Target format: {format}
Filename: {filename}

Request and context:
{context}
"""
