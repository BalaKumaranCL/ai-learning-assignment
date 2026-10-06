"""Capture the RAW JSON-RPC exchange with the package-registry server --
initialize -> notifications/initialized -> tools/list -> tools/call -- by
talking to the server subprocess over plain stdin/stdout pipes, no SDK in
between, so what lands in wire.json is exactly the bytes on the wire (MCP's
stdio transport is one JSON object per line).

The messages are captured live; the ANNOTATIONS below are written by hand
(not generated from the messages). missing_annotations() lists any top-level
field of any captured message that has no hand annotation, and a test fails
if that list is non-empty.
"""

import json
import os
import queue
import subprocess
import sys
import threading

from mcp.types import LATEST_PROTOCOL_VERSION

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MODEL_CALL_STATEMENT = (
    "The model call happens in the HOST (src/mcp_agent.py -> mcp_llm_sim.decide_next), which decides to send the "
    "tools/call below; everything in this file is local JSON-RPC between host and server subprocess, and the server "
    "contains no model call -- it only exposes capabilities."
)

# Hand-written, per captured message (index = order on the wire). Keys are
# top-level fields, plus "<field>.<sub>" for the sub-fields that carry meaning.
ANNOTATIONS = [
    {  # 1 initialize request  (client -> server)
        "jsonrpc": "Protocol tag. Always the string \"2.0\"; MCP is JSON-RPC 2.0 on every message.",
        "id": "Request id chosen by the client (1). The server must echo it in its response so replies can be matched to requests.",
        "method": "\"initialize\": the mandatory first call; opens the session and negotiates versions and capabilities.",
        "params": "Arguments for initialize (sub-fields below).",
        "params.protocolVersion": "Newest MCP spec revision the client speaks; the server answers with the one it will actually use.",
        "params.capabilities": "Optional client features offered to the server (sampling, roots...). Empty = this host offers none, so the server cannot ask the host to run a model.",
        "params.clientInfo": "Name/version of the client, for logs. A third-party server sees this, so it is part of what that server can log.",
    },
    {  # 2 initialize response  (server -> client)
        "jsonrpc": "Protocol tag, \"2.0\".",
        "id": "Echo of the request id (1): this is the answer to the initialize above.",
        "result": "Success payload (a failure would carry \"error\" here instead of \"result\"; never both).",
        "result.protocolVersion": "The spec revision the server picked; both sides use it from now on.",
        "result.capabilities": "What the server offers. \"tools\" present => tools/list and tools/call are available. This SDK also advertises \"resources\" and \"prompts\" keys (with listChanged:false) even though this server registers none -- advertising a capability is not the same as having content.",
        "result.serverInfo": "Server's self-declared name and version. Self-declared: nothing here is verified.",
    },
    {  # 3 initialized notification  (client -> server)
        "jsonrpc": "Protocol tag, \"2.0\".",
        "method": "\"notifications/initialized\": client tells the server the handshake is finished. A notification has no \"id\" and gets no reply.",
    },
    {  # 4 tools/list request
        "jsonrpc": "Protocol tag, \"2.0\".",
        "id": "Request id 2.",
        "method": "\"tools/list\": ask the server what tools it has. This is discovery: the host learns tool names and schemas at runtime, nothing is hard-coded.",
    },
    {  # 5 tools/list response
        "jsonrpc": "Protocol tag, \"2.0\".",
        "id": "Echo of id 2.",
        "result": "Success payload.",
        "result.tools": "The tool catalogue. Each entry: name (what the host passes to tools/call), description (the docstring -- this IS the prompt text the model reads to choose the tool), inputSchema (JSON Schema for arguments), outputSchema.",
    },
    {  # 6 tools/call request
        "jsonrpc": "Protocol tag, \"2.0\".",
        "id": "Request id 3.",
        "method": "\"tools/call\": run one tool. Sent by the host AFTER the model chose this tool -- the choice is made in the host, not here.",
        "params": "Arguments for tools/call (sub-fields below).",
        "params.name": "Which tool to run; must be a name returned by tools/list.",
        "params.arguments": "Argument object, validated by the server against that tool's inputSchema. This is what a third-party server gets to see and log.",
    },
    {  # 7 tools/call response
        "jsonrpc": "Protocol tag, \"2.0\".",
        "id": "Echo of id 3.",
        "result": "Success payload for the call. Note a tool FAILURE also arrives here (see isError), not as a JSON-RPC \"error\".",
        "result.content": "List of content blocks (here one text block) -- what the host feeds back to the model as the observation.",
        "result.structuredContent": "Same value as machine-readable JSON, matching outputSchema.",
        "result.isError": "false = tool ran fine. true would mean the tool failed but the protocol worked; the text in content is then what the model reads to recover.",
    },
]


class _Wire:
    def __init__(self, cmd, env, cwd):
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", env=env, cwd=cwd,
        )
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        self.captured = []

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.put(line)

    def send(self, message):
        self.captured.append(("client->server", message))
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()

    def recv_response(self, want_id, timeout=30):
        while True:
            message = json.loads(self.lines.get(timeout=timeout))
            if message.get("id") == want_id:
                self.captured.append(("server->client", message))
                return message

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


PHASES = ["initialize", "initialize", "initialize (handshake complete)", "tools/list", "tools/list", "tools/call", "tools/call"]


def capture(package="acme-sdk", version="2.9.1", tool="get_deprecation_notice", log_path=None):
    env = {**os.environ, "REGISTRY_API_TOKEN": "demo-registry-token-0001"}
    if log_path:
        env["REGISTRY_LOG_PATH"] = log_path
    wire = _Wire([sys.executable, os.path.join(BASE, "third_party", "package_registry", "server.py")], env, BASE)
    try:
        wire.send({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": LATEST_PROTOCOL_VERSION, "capabilities": {}, "clientInfo": {"name": "wire-capture", "version": "0.1"}},
        })
        wire.recv_response(1)
        wire.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        wire.send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        wire.recv_response(2)
        wire.send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": tool, "arguments": {"package": package, "version": version}}})
        wire.recv_response(3)
    finally:
        wire.close()

    messages = []
    for i, (direction, raw) in enumerate(wire.captured):
        messages.append({"n": i + 1, "phase": PHASES[i], "direction": direction, "raw": raw, "annotations": ANNOTATIONS[i]})
    return {
        "transport": "stdio, newline-delimited JSON-RPC 2.0 (captured from raw pipes, no SDK)",
        "server_under_capture": "package-registry (third_party/package_registry/server.py)",
        "where_the_model_call_happens": MODEL_CALL_STATEMENT,
        "messages": messages,
    }


def missing_annotations(wire):
    """Top-level fields (and params./result. sub-fields) with no hand annotation."""
    missing = []
    for m in wire["messages"]:
        raw, notes = m["raw"], m["annotations"]
        for key, value in raw.items():
            if key not in notes:
                missing.append((m["n"], key))
            if key in ("params", "result") and isinstance(value, dict):
                missing.extend((m["n"], f"{key}.{sub}") for sub in value if f"{key}.{sub}" not in notes)
    return missing


if __name__ == "__main__":
    print(json.dumps(capture(), indent=2))
