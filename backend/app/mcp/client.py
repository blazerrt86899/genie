"""In-process MCP client helpers (CLAUDE.md §22).

Agents call MCP tools through here. ``Client(<server object>)`` uses FastMCP's
in-memory transport — same process, no socket, no subprocess.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastmcp import Client

from app.mcp.tasks_server import mcp as tasks_mcp

logger = structlog.get_logger(__name__)


async def call_tasks_tool(name: str, args: dict[str, Any]) -> Any:
    """Invoke one tool on the in-process ``genie-tasks`` MCP server."""
    logger.info("mcp_tool_call", server="genie-tasks", tool=name, args=sorted(args.keys()))
    try:
        async with Client(tasks_mcp) as client:
            result = await client.call_tool(name, args)
    except Exception:
        logger.exception("mcp_tool_call_failed", server="genie-tasks", tool=name)
        raise
    # FastMCP returns a CallToolResult — `.data` is the deserialised return value.
    data = getattr(result, "data", None)
    if data is None:
        data = getattr(result, "structured_content", None) or getattr(result, "content", None)
    logger.info("mcp_tool_result", tool=name, result_type=type(data).__name__)
    return data
