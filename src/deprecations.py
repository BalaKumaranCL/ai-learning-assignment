"""One shared definition of "this text uses a method we deprecated".

Used by four different places so they can never disagree: the Week-6
assertion (`no_deprecated_symbol_unflagged`), the Week-11 prompt-v2 lint
step, the log-time output index (`output_flags`), and the incident hunt.
The list itself comes from data/changelog.json (the same file the Week-7
`check_deprecation` tool reads) -- nothing is hard-coded twice.
"""

import json
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# How each changelog name actually shows up inside code. A dotted name like
# "Client.sendMessage" is called as `client.sendMessage(`, so matching the
# literal dotted name would miss every real sample.
_CODE_PATTERNS = {
    "Client.sendMessage": r"\.sendMessage\s*\(",
    "Client.pollStream": r"\.pollStream\s*\(",
    "AuthConfig.token": r"AuthConfig\s*\([^)]*\btoken\s*=",
    "RequestOptions.custom_headers": r"\bcustom_headers\b",
}

# An answer that mentions a deprecated name AND says so is a migration note,
# not a stale sample (Client.sendMessage "is deprecated ... use Client.send").
MIGRATION_NOTE_RE = re.compile(r"\b(deprecated|superseded|renamed|use\s+`?[\w.]+`?\s+instead)\b", re.IGNORECASE)


def _load_entries():
    with open(os.path.join(BASE_DIR, "data", "changelog.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["deprecations"]


ENTRIES = _load_entries()
BY_NAME = {e["name"]: e for e in ENTRIES}
_COMPILED = {e["name"]: re.compile(_CODE_PATTERNS[e["name"]]) for e in ENTRIES}


def find_deprecated_symbols(text):
    """Names (from the changelog) whose call pattern appears in `text`."""
    return [name for name, rx in _COMPILED.items() if rx.search(text or "")]


def has_migration_note(text):
    return bool(MIGRATION_NOTE_RE.search(text or ""))


def unflagged_deprecated_symbols(answer, sdk_version_filter, answered=True):
    """Deprecated symbols in an answer that nobody asked for and nothing
    explained. Empty list = fine. A caller who explicitly asked for v2 is
    allowed v2 code (the v2-legacy-support case); a migration note excuses
    the mention. A refusal that merely echoes the question is not an answer."""
    if not answered or sdk_version_filter == "v2":
        return []
    found = find_deprecated_symbols(answer)
    if found and has_migration_note(answer):
        return []
    return found
