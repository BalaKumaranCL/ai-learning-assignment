"""A standalone MCP client for the Week 12 SDK-docs server -- for a reviewer from another squad.

It imports NOTHING from this repo: only the official `mcp` package. That is the point: the server is a real MCP server,
not something only our own agent can talk to. Copy this file anywhere, point SERVER at mcp_servers/w12_sdk_docs_server.py
(or at a running copy of it) and run it.

    python reviewer_client.py                # prints a markdown transcript
    python reviewer_client.py "your question" 2.4

What it does: connects over stdio, asks the server what tools it has (it does not assume any), then calls them -- including
one call that is MEANT to be refused (no version), to show the server will not guess.
"""

import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "mcp_servers", "w12_sdk_docs_server.py")
TRACE = "reviewer-trace-0001"


def text(result):
    return "\n".join(c.text for c in result.content if getattr(c, "type", None) == "text")


async def call(session, name, args, out):
    res = await session.call_tool(name, args)
    body = text(res)
    out.append(f"**call** `{name}({json.dumps(args)})` -> {'ERROR' if res.isError else 'ok'}")
    return res, body


async def main(question, version):
    env = {"W12_SPAN_LOG": os.path.join(HERE, "output", "w12", "reviewer_server_spans.jsonl")}
    params = StdioServerParameters(command=sys.executable, args=[SERVER], env=env)
    out = ["# Foreign-client transcript (reviewer_client.py)", ""]
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            out.append(f"Connected to server **{init.serverInfo.name}**.")
            tools = (await session.list_tools()).tools
            out += ["", "## 1. tools/list (nothing assumed)", ""]
            for t in tools:
                props = ", ".join((t.inputSchema or {}).get("properties", {}))
                out.append(f"- `{t.name}({props})` - {(t.description or '').splitlines()[0]}")

            out += ["", f"## 2. search_docs for a {version} caller", ""]
            res, body = await call(session, "search_docs", {"query": question, "sdk_version": version, "trace_id": TRACE}, out)
            data = json.loads(body)
            out.append(f"scope: `{data['scope']}`; version applied: `{data['version_applied']}`")
            for r in data["results"]:
                out.append(f"- {r['chunk_id']}  (v{r['sdk_version'][1:]}, valid {r['valid_from']}-{r['valid_to']}, {r['page_type']})  <{r['url']}>")
            server_span = data["_server_span"]
            out.append(f"server span: trace_id=`{server_span['trace_id']}` latency={server_span['latency_ms']} ms (the trace id we sent came back)")

            other = "3.0" if version.startswith("2") else "2.4"
            out += ["", f"## 3. the same question for a {other} caller (must return different pages)", ""]
            res, body = await call(session, "search_docs", {"query": question, "sdk_version": other, "trace_id": TRACE}, out)
            for r in json.loads(body)["results"]:
                out.append(f"- {r['chunk_id']}  (v{r['sdk_version'][1:]}, valid {r['valid_from']}-{r['valid_to']})")

            out += ["", "## 4. no version at all (the server must refuse, not guess)", ""]
            res, body = await call(session, "search_docs", {"query": question}, out)
            out.append(f"isError={res.isError}: {body[:260]}")

            out += ["", "## 5. a method that never existed, and one that was removed", ""]
            for sym, v in (("Client.query", "3.0"), ("Client.pollStream", "3.0")):
                res, body = await call(session, "symbol_exists", {"symbol": sym, "sdk_version": v}, out)
                d = json.loads(body)
                out.append(f"`{sym}` in {v}: **{d['status']}**; nearest real names: {d['nearest']}")

            out += ["", "## 6. lifecycle of a deprecated method", ""]
            res, body = await call(session, "lookup_deprecation", {"symbol": "Client.sendMessage", "sdk_version": "2.4"}, out)
            d = json.loads(body)
            out.append(f"`Client.sendMessage` on 2.4: **{d['status']}**, deprecated {d['deprecated']}, removed {d['removed']}, replacement `{d['replacement']}` (since {d['replacement_available_since']})")
    print("\n".join(out))


if __name__ == "__main__":
    q = sys.argv[1] if len(sys.argv) > 1 else "how do I paginate through my messages"
    v = sys.argv[2] if len(sys.argv) > 2 else "2.4"
    asyncio.run(main(q, v))
