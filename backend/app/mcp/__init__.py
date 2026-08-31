"""Genie's MCP layer (CLAUDE.md §22).

Centralized FastMCP servers that expose Genie capabilities as MCP tools. Agents
call them in-process via ``app.mcp.client``; each server also has a
``python -m app.mcp.<server>`` entrypoint so it can be served over
streamable-HTTP for external MCP clients later.
"""
