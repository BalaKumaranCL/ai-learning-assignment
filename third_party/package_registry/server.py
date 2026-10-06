"""Stand-in package-registry MCP server (see README.md in this folder).

Three tools: list_package_versions, get_package_version,
get_deprecation_notice. Like any MCP server it exposes capabilities only --
no model call lives here.

Behaviors an auditor should know about (see ../../risk_note.md):
- needs REGISTRY_API_TOKEN in its environment, else refuses every call
- appends EVERY call to an access log (REGISTRY_LOG_PATH) with the full
  arguments and the last 4 chars of the token
- reads only packages.json next to it; no network, no filesystem writes
  other than that log
"""

import datetime
import json
import os

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "packages.json"), "r", encoding="utf-8") as fh:
    PACKAGES = {k: v for k, v in json.load(fh).items() if not k.startswith("_")}

LOG_PATH = os.environ.get("REGISTRY_LOG_PATH", os.path.join(HERE, "access.log"))

mcp = FastMCP("package-registry")


def _log(tool, arguments):
    token = os.environ.get("REGISTRY_API_TOKEN", "")
    line = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "tool": tool,
        "arguments": arguments,
        "token_tail": token[-4:] if token else None,
    }
    with open(LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def _require_token():
    if not os.environ.get("REGISTRY_API_TOKEN"):
        raise ToolError(
            "AUTH_REQUIRED: REGISTRY_API_TOKEN is not set for this server process; "
            "this is a configuration problem, retrying will not help."
        )


def _package(name):
    pkg = PACKAGES.get(name)
    if pkg is None:
        raise ToolError(
            f"NOT_FOUND: no package named {name!r} in the registry. Known packages: {', '.join(sorted(PACKAGES))}. "
            "The registry itself is up; the name is wrong. retry_with: package=<one of the known packages>"
        )
    return pkg


def _version(pkg, name, version):
    for v in pkg["versions"]:
        if v["version"] == version:
            return v
    published = ", ".join(v["version"] for v in pkg["versions"])
    raise ToolError(
        f"NOT_FOUND: {name} has no version {version!r}. Published versions: {published}; latest is {pkg['latest']}. "
        f"The registry itself is up; that version was never published. retry_with: version={pkg['latest']}"
    )


@mcp.tool()
def list_package_versions(package: str) -> str:
    """List every published version of a package and say which one is the latest published release.

    Use for questions like "what is the latest version of X" or "which versions of X exist".
    `package` is the exact registry name, e.g. "acme-sdk".
    """
    _require_token()
    _log("list_package_versions", {"package": package})
    pkg = _package(package)
    return (
        f"{package}: latest published is {pkg['latest']}. All versions: "
        + ", ".join(v["version"] for v in pkg["versions"])
        + "."
    )


@mcp.tool()
def get_package_version(package: str, version: str) -> str:
    """Look up one exact version of a package: its release date and whether it is the latest.

    Use for "when was X 3.1.0 released". Does NOT say whether the version is deprecated; use the deprecation tool for that.
    `version` is an exact version string such as "3.1.0".
    """
    _require_token()
    _log("get_package_version", {"package": package, "version": version})
    pkg = _package(package)
    v = _version(pkg, package, version)
    tail = " (this is it)." if version == pkg["latest"] else "."
    return f"{package} {version} was released on {v['released']}. Latest published is {pkg['latest']}{tail}"


@mcp.tool()
def get_deprecation_notice(package: str, version: str) -> str:
    """Return the deprecation notice for one exact version of a package, if it has one.

    Use for "is X 2.9.1 deprecated" or "should I upgrade from X 2.9.1". `version` is an exact version string.
    """
    _require_token()
    _log("get_deprecation_notice", {"package": package, "version": version})
    pkg = _package(package)
    v = _version(pkg, package, version)
    dep = v["deprecation"]
    if dep is None:
        return f"{package} {version} is not deprecated."
    return f"{package} {version} is DEPRECATED since {dep['since']}: {dep['notice']} Upgrade to {dep['replacement']}."


if __name__ == "__main__":
    mcp.run()
