"""Stand-in for the LLM in the Week 9 MCP host (same convention as
llm_sim.py / judge.py: this repo has no live model call anywhere, and the
brief grades the MCP plumbing, not model quality).

It is deliberately GENERIC over whatever tools the host discovered: it never
contains a tool name. It picks a tool by lexical overlap between the question
and each discovered tool's name + description (so a richer docstring really
does route better), fills arguments from each tool's own inputSchema, and
reads `retry_with:` / `alternative_tool:` hints out of error text -- which
is exactly the behaviour a recoverable error message is written to enable.

One failure mode is MODELLED, not observed: when a tool fails with an
opaque "Error N" and no hint, this stand-in falls back on a stale prior (a
v2-era code sample) and presents it as an answer. That is the failure the
Week 9 brief names ("cheerfully emits a sample against the deprecated v2
API"); a real model would behave variably, so treat the before-transcript
as an illustration of the failure the rewrite prevents, not a measurement.
"""

import re

STOPWORDS = {
    "the", "a", "an", "of", "is", "to", "for", "in", "on", "and", "or", "me", "my", "what", "which", "when", "was",
    "how", "do", "does", "it", "i", "that", "this", "with", "be", "are", "show", "give", "tell", "about", "can",
}
MIN_SCORE = 2
OPAQUE_ERROR = re.compile(r"^(Error executing tool \w+:\s*)?Error \d+\s*$")
RETRY_HINT = re.compile(r"retry_with:\s*(\w+)=(\S+?)[.\s]*$", re.M)
ALT_TOOL_HINT = re.compile(r"alternative_tool:\s*(\w+)")


def _stem(word):
    return word[:5]


def _tokens(text):
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {_stem(w) for w in words if w not in STOPWORDS and len(w) > 1}


def extract_slots(question):
    """Entities a model would pull out of the question, keyed by the
    argument names tools tend to use. Pure text extraction -- no tool names."""
    slots = {"query": question}
    package = re.search(r"\b([a-z]+-[a-z]+)\b", question)
    if package:
        slots["package"] = package.group(1)
    semver = re.search(r"\b(\d+\.\d+\.\d+)\b", question)
    if semver:
        slots["version"] = semver.group(1)
    explicit_v = re.search(r"\bv(\d+)\b", question, re.I)
    if explicit_v:
        slots["sdk_version"] = slots["api_version"] = f"v{explicit_v.group(1)}"
    elif semver:
        slots["_derived_api_version"] = "v" + semver.group(1).split(".")[0]
    ident = re.search(r"\b([A-Z][A-Za-z]+\.[A-Za-z_]+|[A-Z][a-z]+[A-Z][A-Za-z]+)\b", question)
    if ident:
        slots["endpoint"] = slots["name"] = ident.group(1)
    return slots


def fill_args(tool, slots):
    """Fill `tool`'s inputSchema from slots. Returns None if a required
    argument can't be filled (the tool is not eligible)."""
    schema = tool.get("inputSchema") or {}
    required = set(schema.get("required", []))
    args = {}
    for prop, spec in (schema.get("properties") or {}).items():
        value = slots.get(prop)
        if value is None and prop in ("sdk_version", "api_version"):
            value = slots.get("_derived_api_version") if prop in required else None
        if value is None and prop in required:
            if "default" in spec:
                value = spec["default"]
            else:
                return None
        if value is not None:
            args[prop] = value
    return args


def schema_required(tool):
    return set((tool.get("inputSchema") or {}).get("required", []))


def select_tool(question, tools):
    """Best discovered tool for the question, or (None, None) below MIN_SCORE."""
    q = _tokens(question)
    slots = extract_slots(question)
    best = (0, None, None)
    for tool in tools:
        args = fill_args(tool, slots)
        if args is None:
            continue
        name_tokens = _tokens(tool["name"].replace("_", " "))
        desc_tokens = _tokens(tool.get("description") or "")
        # an argument the question fills with a specific entity (a package
        # name, a version number) is evidence the tool is the right shape
        entity_bonus = 3 * sum(1 for k in args if k in schema_required(tool) and k != "query")
        score = 3 * len(q & name_tokens) + len(q & desc_tokens) + entity_bonus
        if score > best[0]:
            best = (score, tool, args)
    if best[0] < MIN_SCORE:
        return None, None
    return best[1], best[2]


def _first_sentence(text):
    return re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]


def stale_prior_answer():
    return (
        "Here is a sample based on what I remember of the SDK:\n"
        "    client = Client(AuthConfig(token=TOKEN))\n"
        "    reply = client.sendMessage(prompt)\n"
        "(No source consulted.)"
    )


def decide_next(question, tools, history, resources_text=""):
    """One model turn. `history` is the list of tool results so far, each
    {"tool", "arguments", "is_error", "text"}. Returns {"type": "call", ...}
    or {"type": "answer", "answer": ...}."""
    by_name = {t["name"]: t for t in tools}

    if not history:
        tool, args = select_tool(question, tools)
        if tool is None:
            return {"type": "answer", "answer": "None of my available tools can answer that."}
        return {"type": "call", "tool": tool["name"], "arguments": args}

    last = history[-1]
    if not last["is_error"]:
        body = last["text"].strip()
        if len(history) > 1:
            first = history[0]
            if ALT_TOOL_HINT.search(first["text"]):
                body = f"Note: {first['tool']} was refused ({_first_sentence(first['text'])}) so this does NOT cover that part.\n{body}"
            else:
                changed = {k: v for k, v in last["arguments"].items() if first["arguments"].get(k) != v}
                body = (
                    f"Note: my first call failed ({_first_sentence(first['text'])}); I retried with "
                    f"{changed}, so this answer is for that, not for what was originally asked.\n{body}"
                )
        return {"type": "answer", "answer": body}

    text = last["text"]
    if len(history) >= 3:
        return {"type": "answer", "answer": f"I could not complete this: {_first_sentence(text)}"}

    alt = ALT_TOOL_HINT.search(text)
    if alt and alt.group(1) in by_name and alt.group(1) != last["tool"]:
        args = fill_args(by_name[alt.group(1)], extract_slots(question))
        if args is not None:
            return {"type": "call", "tool": alt.group(1), "arguments": args}

    hint = RETRY_HINT.search(text)
    if hint and not hint.group(2).startswith("<"):
        key, value = hint.group(1), hint.group(2)
        props = (by_name[last["tool"]].get("inputSchema") or {}).get("properties", {})
        if key in props and last["arguments"].get(key) != value:
            return {"type": "call", "tool": last["tool"], "arguments": {**last["arguments"], key: value}}

    if OPAQUE_ERROR.match(text.strip()):
        return {"type": "answer", "answer": stale_prior_answer()}
    return {"type": "answer", "answer": f"I could not complete this: {_first_sentence(text)}"}
