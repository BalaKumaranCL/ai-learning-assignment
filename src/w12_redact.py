"""Week 12: redact secrets and PII on WRITE (the Week-11 PII line, held across every hop).

Integrator questions routinely contain pasted API keys and connection
strings. This module is the ONE implementation; the engine, the request
logger, and the MCP server's own span log all call it, so the rule cannot
differ between processes.

`redact(text)` -> (clean_text, findings). Findings name the KIND only, never
the value, so even the finding list is safe to log.
"""

import re

_PATTERNS = [
    ("connection_string", re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?|mssql)://[^\s'\"<>]+", re.IGNORECASE)),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{4,}\b")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)),
    ("acme_api_key", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{6,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("assigned_secret", re.compile(
        r"(?i)\b(api[_-]?key|secret|passw(?:or)?d|token|auth)\b(\s*[=:]\s*)(['\"]?)([^\s'\"<>,;)]{8,})\3")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
]

# values that are obviously documentation placeholders, not secrets
_PLACEHOLDERS = {"sk_live_example", "sk_test_example", "YOUR_TOKEN", "YOUR_API_KEY", "TOKEN"}


def redact(text):
    if not isinstance(text, str) or not text:
        return text, []
    findings = []
    out = text
    for kind, rx in _PATTERNS:
        def repl(m, kind=kind):
            if kind == "assigned_secret":
                if m.group(4) in _PLACEHOLDERS or m.group(4).startswith("[REDACTED"):
                    return m.group(0)
                findings.append(kind)
                return f"{m.group(1)}{m.group(2)}{m.group(3)}[REDACTED:secret]{m.group(3)}"
            if m.group(0) in _PLACEHOLDERS:
                return m.group(0)
            findings.append(kind)
            return f"[REDACTED:{kind}]"
        out = rx.sub(repl, out)
    return out, findings


def redact_deep(obj):
    """Redact every string inside a nested dict/list structure (a whole log record)."""
    if isinstance(obj, str):
        return redact(obj)[0]
    if isinstance(obj, list):
        return [redact_deep(x) for x in obj]
    if isinstance(obj, dict):
        return {k: redact_deep(v) for k, v in obj.items()}
    return obj


def has_secret(text):
    return bool(redact(text)[1])


def strip_markers(text):
    """Remove the [REDACTED:kind] placeholders before a question is SEARCHED: to a retriever they are words the docs
    never use, and the Stack Overflow bridge reads them as a vocabulary gap (found by case C31)."""
    return re.sub(r"\s*\[REDACTED:[a-z_]+\]\s*", " ", text).strip()
