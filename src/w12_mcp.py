"""Week 12: the MCP CLIENT side of the integrated app -- Week 9's McpHost plus
one thing it never needed: calling a tool directly (the Week 9 host ran its own
model loop; here the Week 12 agent owns the loop and just needs `call`).

Discovery is unchanged: initialize -> tools/list at connect time. The agent
never sees a tool name until the server lists it.
"""

import json
import time

from mcp_agent import McpHost, _text_of


class W12Host(McpHost):
    async def call(self, tool_name, arguments):
        """-> (text, is_error, round_trip_ms). Never raises on a tool error: an MCP tool error is DATA the agent can recover from."""
        tool = next(t for t in self.tools if t["name"] == tool_name)
        t0 = time.perf_counter()
        result = await self.sessions[tool["server"]].call_tool(tool_name, arguments)
        ms = (time.perf_counter() - t0) * 1000
        return _text_of(result), bool(result.isError), ms


def parse_result(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None
