"""/api/agent/* — the bridge used by mcp_server.py (Bearer token from <DATA_DIR>/mcp-token)."""

from __future__ import annotations

from typing import Any

from fastapi import Request

from ..agent_tools import AGENT_INSTRUCTIONS, TOOLS, call_tool, tool_catalog
from ..hoard_link.agentkit import make_agent_router
from .deps import services


def _call(name: str, arguments: dict[str, Any], request: Request) -> Any:
    return call_tool(services(request), name, arguments, cap=True)


# CiceroError / Refused / NotFound are AppErrors: the router answers them with their own status (400 / 403 / 404) and code
router = make_agent_router(
    tools_fn=tool_catalog,
    call_fn=_call,
    token_fn=lambda request: services(request).token,
    instructions=AGENT_INSTRUCTIONS,
    app_name="cicero",
    reasons=True,                                          # an agent says why for every write; the web UI is not an agent and is exempt
    data_dir=lambda request: services(request).config.data_dir,
    tools=TOOLS,
    ctx_fn=lambda request: services(request),
)
