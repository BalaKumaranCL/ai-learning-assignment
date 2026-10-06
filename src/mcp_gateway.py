"""Week 9 bonus: ONE front-door MCP server in front of both downstream
servers. The agent connects only to this process; the gateway
  1. connects to every downstream server in --downstream (same config
     format the agent uses), discovers their tools via tools/list, and
     re-exports them -- so it also contains no tool names;
  2. writes one audit line per tools/call: caller, tool, package@version;
  3. enforces token scoping: the caller's token (MCP_GATEWAY_TOKEN env,
     looked up in gateway_tokens.json) may deny specific tools, and a denial
     goes back to the model as a normal isError tool result whose text says
     what is allowed instead -- a recoverable message, not a crash.

stdio has no HTTP headers, so the token travels in the environment of the
gateway process, set by the agent's config entry. Over remote MCP it would
be a bearer token; the scoping logic is the same.
"""

import argparse
import asyncio
import datetime
import json
import os
import sys
from contextlib import AsyncExitStack

import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server


def audit_line(caller, tool, arguments, decision, reason=""):
    pkg = arguments.get("package")
    requested = f"{pkg}@{arguments.get('version', '-')}" if pkg else "-"
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    line = f"{ts} caller={caller} tool={tool} package@version={requested} decision={decision}"
    return line + (f" reason={reason}" if reason else "")


def check_scope(token_entry, tool, available_tools):
    """Return None if allowed, else the recoverable denial text."""
    if token_entry is None:
        return "AUTH_REQUIRED: unknown or missing gateway token; no tools are available. This is a configuration problem, retrying will not help."
    if tool in token_entry.get("denied_tools", []):
        allowed = [t for t in available_tools if t not in token_entry["denied_tools"]]
        alt = token_entry.get("alternatives", {}).get(tool)
        text = (
            f"SCOPE_DENIED: this token ({token_entry['caller']}) is not allowed to call {tool}. "
            f"The tool exists and the servers are up; this is a permission limit, not an outage. "
            f"Allowed tools: {', '.join(allowed)}. Tell the user the {tool} information is unavailable to you."
        )
        if alt:
            text += f" alternative_tool: {alt}"
        return text
    return None


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--downstream", required=True)
    ap.add_argument("--tokens", required=True)
    ap.add_argument("--audit-log", required=True)
    args = ap.parse_args()

    base_dir = os.path.dirname(os.path.abspath(args.downstream))
    with open(args.downstream, "r", encoding="utf-8") as fh:
        downstream_cfg = json.load(fh)["mcpServers"]
    with open(args.tokens, "r", encoding="utf-8") as fh:
        token_table = json.load(fh)["tokens"]
    token_entry = token_table.get(os.environ.get("MCP_GATEWAY_TOKEN", ""))
    caller = token_entry["caller"] if token_entry else "unauthenticated"

    def audit(line):
        with open(args.audit_log, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    server = Server("mcp-gateway")
    route = {}   # tool name -> downstream ClientSession
    catalog = []  # downstream types.Tool objects

    @server.list_tools()
    async def list_tools():
        return catalog

    @server.call_tool(validate_input=False)
    async def call_tool(name, arguments):
        arguments = arguments or {}
        denial = check_scope(token_entry, name, list(route))
        if denial:
            audit(audit_line(caller, name, arguments, "DENY", denial.split(":")[0]))
            raise Exception(denial)
        session = route.get(name)
        if session is None:
            audit(audit_line(caller, name, arguments, "ERROR", "unknown_tool"))
            raise Exception(f"UNKNOWN_TOOL: no downstream server exposes {name}. Available: {', '.join(route)}.")
        result = await session.call_tool(name, arguments)
        text = "\n".join(c.text for c in result.content if getattr(c, "type", None) == "text")
        audit(audit_line(caller, name, arguments, "ALLOW", "downstream_error" if result.isError else ""))
        if result.isError:
            raise Exception(text.removeprefix(f"Error executing tool {name}: "))
        content = [types.TextContent(type="text", text=text)]
        # forward structuredContent too: downstream tools declare an outputSchema, so the host would reject a bare reply
        return (content, result.structuredContent) if result.structuredContent is not None else content

    async with AsyncExitStack() as stack:
        devnull = stack.enter_context(open(os.devnull, "w"))
        for dname, cfg in downstream_cfg.items():
            command = sys.executable if cfg["command"] in ("python", "python3") else cfg["command"]
            params = StdioServerParameters(command=command, args=cfg.get("args", []), env=cfg.get("env", {}), cwd=base_dir)
            read, write = await stack.enter_async_context(stdio_client(params, errlog=devnull))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            for tool in (await session.list_tools()).tools:
                route[tool.name] = session
                catalog.append(tool)
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
