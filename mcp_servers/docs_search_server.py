"""docs-search MCP server -- OUR OWN server (Week 9). Exposes two tools
(search_docs, get_openapi_spec) over the same data Weeks 3-8 already use,
plus one RESOURCE (docs://version-support-matrix): a table the app attaches
to the prompt rather than a tool the model must spend a turn fetching.
No model call lives in this file -- a server exposes capabilities, the host
runs the model.

DOCS_SERVER_STYLE picks the wording of one tool's docstring + error path so
the Week 9 before/after transcript can run the SAME failing call twice:
  legacy  -- terse docstring, opaque "Error 3" (the "before")
  prompt  -- docstring written as a prompt, recoverable diagnostic (default)
"""

import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402

import agent_tools  # noqa: E402

STYLE = os.environ.get("DOCS_SERVER_STYLE", "prompt")
SUPPORTED = agent_tools.API_VERSIONS  # ("v2", "v3")
LATEST = SUPPORTED[-1]

mcp = FastMCP("docs-search")

SEARCH_DOCS_PROMPT = f"""Search the Acme SDK prose documentation (guides, reference pages, usage examples) and return the best-matching passages.

WHEN TO USE: the user wants to know how a feature works or wants an example. Phrase `query` as a natural-language search.
WHEN NOT TO USE: for the exact parameter list of a named endpoint use get_openapi_spec; for package release dates or deprecation of a package version use the package/registry tools if you have them.
`sdk_version` is optional and must be one of {', '.join(SUPPORTED)}; omit it to search everything. The latest published docs are {LATEST}.
IF YOU GET AN ERROR: it starts with a KIND. UNSUPPORTED_VERSION means that version has no docs -- read the message, it names the latest published version and a retry_with value; retry once with that value and tell the user which version the answer is actually for. Never answer from memory of an older SDK version.
"""


@mcp.tool(description="Search docs." if STYLE == "legacy" else SEARCH_DOCS_PROMPT)
def search_docs(query: str, sdk_version: str | None = None) -> str:
    if sdk_version is not None and sdk_version not in SUPPORTED:
        if STYLE == "legacy":
            raise ToolError("Error 3")
        raise ToolError(
            f"UNSUPPORTED_VERSION: no docs for {sdk_version} -- latest published is {LATEST} (also available: "
            f"{', '.join(SUPPORTED[:-1])}, deprecated). Renamed/deprecated v2 methods and their {LATEST} replacements are "
            f"listed in resource docs://version-support-matrix. The docs service itself is up; {sdk_version} does not exist yet. "
            f"retry_with: sdk_version={LATEST}"
        )
    result = agent_tools.search_docs(query, sdk_version)
    if not result["results"]:
        return f"No documentation passages matched {query!r}."
    return "\n\n".join(f"[{r['source_file']} > {r['anchor']}]\n{r['text'].strip()}" for r in result["results"])


@mcp.tool(
    description=(
        "Get spec."
        if STYLE == "legacy"
        else "Look up the exact parameter schema (names, types, defaults, required) for ONE named endpoint or config "
        "object, e.g. 'Client.send' or 'AuthConfig', for one api_version (v2 or v3). Use for 'what does X take'; "
        "use search_docs for prose or examples."
    )
)
def get_openapi_spec(endpoint: str, api_version: str = "v3") -> str:
    result = agent_tools.get_openapi_spec(endpoint, api_version)
    if not result["found"]:
        return f"No OpenAPI schema on file for {endpoint!r} in {api_version}."
    bits = [
        f"{p['name']} ({p['type']}, required)" if p["required"] else f"{p['name']} ({p['type']}, default={p['default']!r})"
        for p in result["parameters"]
    ]
    return f"{endpoint} in {api_version} takes: " + ", ".join(bits) + "."


@mcp.resource("docs://version-support-matrix")
def version_support_matrix() -> str:
    """Which Acme SDK doc versions are published, and which v2 names were renamed in v3. Attach to the prompt; do not fetch via a tool."""
    rows = [f"- {d['name']} (deprecated in {d['deprecated_in']}) -> {d['replacement']}" for d in agent_tools._CHANGELOG]
    return (
        f"Published doc versions: {', '.join(SUPPORTED)}. Latest: {LATEST}. v2 is deprecated.\n"
        "Renames:\n" + "\n".join(rows)
    )


if __name__ == "__main__":
    mcp.run()
