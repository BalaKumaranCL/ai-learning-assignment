"""Week 9 MCP host/agent. Connects to every server listed in a config file,
discovers their tools (and resources) at runtime via the MCP handshake
(initialize -> tools/list), and routes the model's tool calls back to the
right server via tools/call.

THIS FILE KNOWS NO TOOL NAMES. The set of tools is whatever tools/list
returns for whatever servers the config names -- adding a server is a config
edit and nothing here changes (see agent_diff.txt). Tests grep this file and
mcp_llm_sim.py for tool names to keep it that way.

Roles (the brief's "host / client / server"): this process is the HOST; each
`ClientSession` below is one MCP CLIENT, 1:1 with one SERVER subprocess. The
model call (mcp_llm_sim.decide_next -- a documented stand-in, see its
docstring) happens HERE in the host, never in a server.
"""

import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from mcp_llm_sim import decide_next

MAX_LAPS = 4


def _text_of(call_result):
    return "\n".join(c.text for c in call_result.content if getattr(c, "type", None) == "text")


class McpHost:
    def __init__(self, config_path, extra_env=None):
        self.config_path = os.path.abspath(config_path)
        self.base_dir = os.path.dirname(self.config_path)
        with open(self.config_path, "r", encoding="utf-8") as fh:
            self.servers_cfg = json.load(fh)["mcpServers"]
        self.extra_env = extra_env or {}
        self._stack = AsyncExitStack()
        self.sessions = {}        # server name -> ClientSession
        self.tools = []           # discovered: dicts with name/description/inputSchema/server
        self.discovery = {}       # server name -> [tool names], straight from tools/list
        self.server_info = {}     # server name -> serverInfo from initialize
        self.resource_text = ""   # app-attached context (resources are attached, not model-invoked)

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def connect(self):
        devnull = self._stack.enter_context(open(os.devnull, "w"))
        resource_chunks = []
        for name, cfg in self.servers_cfg.items():
            command = sys.executable if cfg["command"] in ("python", "python3") else cfg["command"]
            params = StdioServerParameters(
                command=command,
                args=cfg.get("args", []),
                env={**cfg.get("env", {}), **self.extra_env},
                cwd=self.base_dir,
            )
            read, write = await self._stack.enter_async_context(stdio_client(params, errlog=devnull))
            session = await self._stack.enter_async_context(ClientSession(read, write))
            init = await session.initialize()
            self.sessions[name] = session
            self.server_info[name] = init.serverInfo.name

            tools, cursor = [], None
            while True:
                page = await session.list_tools(cursor=cursor)
                tools.extend(page.tools)
                cursor = page.nextCursor
                if not cursor:
                    break
            self.discovery[name] = [t.name for t in tools]
            for t in tools:
                self.tools.append({"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema, "server": name})

            if init.capabilities.resources is not None:
                for r in (await session.list_resources()).resources:
                    body = await session.read_resource(r.uri)
                    resource_chunks.append(f"[{name} resource {r.uri}]\n" + "\n".join(getattr(c, "text", "") for c in body.contents))
        self.resource_text = "\n\n".join(resource_chunks)

    def tool_count(self):
        return sum(len(v) for v in self.discovery.values())

    async def ask(self, question):
        """Run one question through the model/tool loop. Returns a trace
        with every tools/call (server + tool name + args + result) and the
        final answer."""
        history, steps = [], []
        for lap in range(1, MAX_LAPS + 1):
            decision = decide_next(question, self.tools, history, self.resource_text)
            if decision["type"] == "answer":
                return {"question": question, "steps": steps, "answer": decision["answer"]}
            tool = next(t for t in self.tools if t["name"] == decision["tool"])
            result = await self.sessions[tool["server"]].call_tool(decision["tool"], decision["arguments"])
            text = _text_of(result)
            step = {
                "lap": lap,
                "server": tool["server"],
                "tool": decision["tool"],
                "arguments": decision["arguments"],
                "is_error": bool(result.isError),
                "result_text": text,
            }
            steps.append(step)
            history.append({"tool": step["tool"], "arguments": step["arguments"], "is_error": step["is_error"], "text": text})
        return {"question": question, "steps": steps, "answer": "I could not finish within the lap limit."}


async def run_questions(config_path, questions, extra_env=None):
    async with McpHost(config_path, extra_env=extra_env) as host:
        traces = [await host.ask(q) for q in questions]
        return {
            "config": os.path.basename(config_path),
            "discovery": host.discovery,
            "tool_count": host.tool_count(),
            "tools": [{"server": t["server"], "name": t["name"], "description": t["description"]} for t in host.tools],
            "resource_text": host.resource_text,
            "traces": traces,
        }


def run_questions_sync(config_path, questions, extra_env=None):
    return asyncio.run(run_questions(config_path, questions, extra_env=extra_env))


if __name__ == "__main__":
    config = sys.argv[1] if len(sys.argv) > 1 else "mcp_config.json"
    out = run_questions_sync(config, sys.argv[2:] or ["Is acme-sdk 2.9.1 deprecated?"])
    print(json.dumps(out, indent=2))
