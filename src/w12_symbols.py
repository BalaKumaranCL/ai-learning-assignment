"""Week 12: the symbol table -- "does this method/argument exist in THIS version?"

Reads corpus/symbols.json (or the file named by the W12_MANIFEST environment
variable -- the "v3.1 drill" points it at an edited copy). Everything that
needs a lifecycle fact reads it from here: the symbol-exists tool, the
changelog/deprecation tool, the code checker, and the version resolver.

Status of a symbol AT a version:
  current     exists and is fine
  deprecated  exists, still works, scheduled for removal
  removed     existed before, no longer exists at this version
  not_yet     is introduced in a LATER version than this one
  unknown     no record in the manifest in any version  (never invent one)
"""

import json
import os
import re
from functools import lru_cache

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MANIFEST = os.path.join(BASE_DIR, "corpus", "symbols.json")


def parse_exact_version(text):
    if not text:
        return None
    m = re.fullmatch(r"(\d+)\.(\d+)", str(text).strip())
    return (int(m.group(1)), int(m.group(2))) if m else None


def _ver(v):
    """Accept '2.4', '2.4.1', (2,4) -> (2,4)."""
    if isinstance(v, tuple):
        return v
    m = re.match(r"\s*v?(\d+)(?:\.(\d+))?", str(v))
    return (int(m.group(1)), int(m.group(2) or 0))


@lru_cache(maxsize=4)
def _load(path):
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    index = {}
    for m in raw["members"]:
        index[m["id"]] = {k: v for k, v in m.items() if k != "params"} | {"kind": m.get("kind", "method")}
        for p in m.get("params", []):
            pid = f"{m['id']}.{p['name']}"
            index[pid] = dict(p) | {"kind": "param", "parent": m["id"]}
    for e in raw["exports"]:
        index.setdefault(e["id"], dict(e) | {"kind": "export"})
    for tname, attrs in raw["types"].items():
        for a in attrs:
            index[f"{tname}.{a['name']}"] = dict(a) | {"kind": "attr", "parent": tname}
    return raw, index


def manifest():
    path = os.environ.get("W12_MANIFEST", DEFAULT_MANIFEST)
    return _load(path)


def lifecycle(symbol_id):
    return manifest()[1].get(symbol_id)


def member(symbol_id):
    """The callable record (with its params list) for a method/class id."""
    for m in manifest()[0]["members"]:
        if m["id"] == symbol_id:
            return m
    return None


def type_attrs(type_name):
    return manifest()[0]["types"].get(type_name)


def exports():
    return {e["id"]: e for e in manifest()[0]["exports"]}


def latest(major):
    return manifest()[0]["latest"][str(major)]


def status(symbol_id, version):
    rec = lifecycle(symbol_id)
    if rec is None:
        return "unknown"
    v = _ver(version)
    intro = parse_exact_version(rec.get("introduced")) or (0, 0)
    removed = parse_exact_version(rec.get("removed"))
    dep = parse_exact_version(rec.get("deprecated"))
    if v < intro:
        return "not_yet"
    if removed and v >= removed:
        return "removed"
    if dep and v >= dep:
        return "deprecated"
    return "current"


def exists(symbol_id, version):
    return status(symbol_id, version) in ("current", "deprecated")


def record(symbol_id, version=None):
    """The lookup the changelog/deprecation tool returns. Plain dict, JSON-safe."""
    rec = lifecycle(symbol_id)
    if rec is None:
        return {"symbol": symbol_id, "status": "unknown", "known": False, "version": version,
                "note": "No record of this name in the symbol table for any 2.x or 3.0 release."}
    out = {
        "symbol": symbol_id, "known": True,
        "status": status(symbol_id, version) if version else None,
        "version": version,
        "introduced": rec.get("introduced"), "deprecated": rec.get("deprecated"), "removed": rec.get("removed"),
        "replacement": rec.get("replacement"),
        "replacement_available_since": rec.get("replacement_available_since"),
        "note": rec.get("note"),
    }
    # the reverse lookup: names this one REPLACED (old tutorials and Stack Overflow still use them)
    out["replaces"] = []
    for oid, orec in manifest()[1].items():
        repl = orec.get("replacement")
        if not repl:
            continue
        full = f"{orec['parent']}.{repl}" if orec.get("kind") == "param" and "." not in repl else repl
        if full == symbol_id:
            out["replaces"].append({"symbol": oid, "deprecated": orec.get("deprecated"), "removed": orec.get("removed")})
    # a parameter's replacement is a sibling parameter: spell out the full id
    if rec.get("replacement") and rec.get("kind") == "param" and "." not in rec["replacement"]:
        out["replacement"] = f"{rec['parent']}.{rec['replacement']}"
        sib = lifecycle(out["replacement"])
        out["replacement_available_since"] = sib.get("introduced") if sib else None
    return out


def params_named(name):
    """Every parameter record called `name`, whatever method it belongs to."""
    return [(sid, rec) for sid, rec in manifest()[1].items() if rec.get("kind") == "param" and sid.endswith("." + name)]


def lifecycle_notes(version, symbol_ids):
    """Unasked notices for the symbols an answer touched.
    -> list of dicts {symbol, kind: 'deprecated'|'removal_ahead', ...} for symbols that are
    deprecated at `version`, or are still current but have a scheduled removal."""
    notes = []
    for sid in dict.fromkeys(symbol_ids):
        rec = record(sid, version)
        if not rec["known"]:
            continue
        st = rec["status"]
        if st == "deprecated":
            notes.append(rec | {"kind": "deprecated"})
        elif st == "current" and rec.get("removed"):
            notes.append(rec | {"kind": "removal_ahead"})
    return notes


# --------------------------------------------------------------------------
# finding symbols in free text / code
# --------------------------------------------------------------------------

# bare identifiers that are unambiguous even outside code
_BARE = {
    "sendMessage": "Client.sendMessage",
    "pollStream": "Client.pollStream",
    "list_messages": "Client.list_messages",
    "custom_headers": "RequestOptions.custom_headers",
    "per_page": "Client.list_messages.per_page",
    "api_key": "AuthConfig.api_key",
    "max_retries": "Client.send.max_retries",
    "retry_backoff_ms": "Client.send.retry_backoff_ms",
    "next_cursor": "ListResult.next_cursor",
    "total_pages": "ListResult.total_pages",
    "token_refresh_ms": "AuthConfig.token_refresh_ms",
    "body_encoding": "RequestOptions.body_encoding",
}
# `client.name(` -- must be a real call (no space after the dot, an opening paren), so
# ordinary English like "use the client. It works" is never read as a method.
_METHOD_CALL = re.compile(r"\b(?:[Cc]lient|cli|c)\.([A-Za-z_]\w*)\s*\(")
_CLASS_METHOD = re.compile(r"\bClient\.([A-Za-z_]\w*)")
_KWARGS = {
    "AuthConfig.token": re.compile(r"AuthConfig\s*\([^)]*\btoken\s*="),
    "Client.list_messages.page": re.compile(r"list_messages\s*\([^)]*\bpage\s*="),
    "Client.list_messages.limit": re.compile(r"list_messages\s*\([^)]*\blimit\s*="),
    "Client.list_messages.cursor": re.compile(r"list_messages\s*\([^)]*\bcursor\s*="),
    "RequestOptions.headers": re.compile(r"RequestOptions\s*\([^)]*\bheaders\s*="),
}
_PLAIN_METHODS = ("send", "stream", "close")


def extract_symbols(text, usage_only=False):
    """Symbols mentioned in `text` (a question or a code snippet).
    -> list of {id, text, status_kind}; status_kind 'unknown' for a `client.<name>(` that is in no version.

    usage_only=True keeps only symbols that are USED like code (a call `x(`, a keyword `x=`):
    "does pollStream still work in 3.0?" MENTIONS a symbol, `client.pollStream("hi")` USES it, and
    only a use says anything about which version the caller is on."""
    found, seen = [], set()

    def add(sid, kind, matched):
        if sid not in seen:
            seen.add(sid)
            found.append({"id": sid, "text": matched, "status_kind": kind})

    t = text or ""
    for ident, sid in _BARE.items():
        rx = rf"\b{re.escape(ident)}\s*[(=]" if usage_only else rf"\b{re.escape(ident)}\b"
        if re.search(rx, t):
            add(sid, "known", ident)
    for sid, rx in _KWARGS.items():
        m = rx.search(t)
        if m:
            add(sid, "known", m.group(0))
    for rx in (_METHOD_CALL,) if usage_only else (_METHOD_CALL, _CLASS_METHOD):
        for m in rx.finditer(t):
            name = m.group(1)
            sid = f"Client.{name}"
            if lifecycle(sid) is not None:
                add(sid, "known", m.group(0))
            elif name not in ("__init__",) and not name.startswith("_"):
                # an attribute on a client that no release of the SDK has
                add(sid, "unknown", m.group(0))
    if not usage_only:
        for name in _PLAIN_METHODS:
            if re.search(rf"\b{name}\s*\(\s*\)|`{name}\(\)`|`{name}`", t) and f"Client.{name}" not in seen:
                add(f"Client.{name}", "known", name)
        for cls in ("AuthConfig", "RequestOptions"):
            if re.search(rf"\b{cls}\b", t):
                add(cls, "known", cls)
    return found
