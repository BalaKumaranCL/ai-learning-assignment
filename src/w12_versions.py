"""Week 12: SDK version arithmetic and the version RESOLVER.

The brief's whole point is "answer against the caller's ACTUAL version", so
the version is decided here, before any retrieval, from the best evidence
available -- and if there is no evidence we say so instead of guessing.

A version is a (major, minor) tuple: patch levels never change this SDK's API,
so "2.4.1" and "2.4" are the same version for every check in this project.

Resolution order (first hit wins):
  1. request_metadata   -- the IDE/CLI sent `sdk_version` (most trustworthy)
  2. pinned_in_text     -- `acme-sdk==2.4.1` pasted from requirements/pip freeze
  3. stated_in_text     -- "I'm on 2.4", "we run v2.4.1"
  4. inferred_from_code -- pasted code that only works in one range of versions
                           (e.g. `AuthConfig(api_key=...)` => 2.5 or later)
  5. mentioned          -- a lone "in 2.4" / "v3" in the question
  6. none               -- unresolved. The engine ASKS; it does not guess.

`resolve_version(..., smart=False)` is the NAIVE first-wiring behaviour kept
for the before/after measurement: only the explicit field, else silently
default to the latest (3.0) -- which is exactly what Week 11's fix did (seam S4).
"""

import re

import w12_symbols as sym

VERSION_RE = re.compile(r"(?<![\w.])v?(\d+)(?:\.(\d+))?(?:\.\d+)?(?![\w.])", re.IGNORECASE)
LATEST = (3, 0)


def parse(text):
    """'2.4', '2.4.1', 'v2.4', 'v3', '3' -> (major, minor); None if not a version.
    A bare major ('v2') gives minor None-> returned as (2, None)."""
    if text is None:
        return None
    m = re.fullmatch(r"\s*v?(\d+)(?:\.(\d+))?(?:\.\d+)?\s*", str(text), re.IGNORECASE)
    if not m:
        return None
    major = int(m.group(1))
    if major not in (2, 3):
        return None
    return (major, int(m.group(2)) if m.group(2) is not None else None)


def fmt(v):
    return f"{v[0]}.{v[1]}"


def major_tag(v):
    return f"v{v[0]}"


def parse_range(text):
    """'2.2-2.4' -> ((2,2),(2,4)); '3.0-3.99' -> ((3,0),(3,99))."""
    lo, hi = text.split("-")
    return parse_exact(lo), parse_exact(hi)


def parse_exact(text):
    m = re.fullmatch(r"(\d+)\.(\d+)", text.strip())
    return (int(m.group(1)), int(m.group(2)))


def in_range(v, lo, hi):
    return lo <= v <= hi


# --------------------------------------------------------------------------
# resolver
# --------------------------------------------------------------------------

_PIN_RE = re.compile(r"acme[-_]sdk\s*(==|~=|>=|<=|>|<)?\s*v?(\d+\.\d+(?:\.\d+)?)", re.IGNORECASE)
_STATED_RE = re.compile(
    r"(?:\b(?:i['’]?m|we['’]?re|i\s+am|we\s+are|currently|still|stuck)\s+(?:on|using|running|at)\s+|"
    r"\b(?:my|our)\s+(?:acme\s+)?(?:sdk\s+)?version\s+(?:is\s+)?|"
    r"\b(?:running|using|on)\s+(?:acme[-_ ]?sdk\s+)?(?:version\s+)?)"
    r"v?(\d+\.\d+(?:\.\d+)?|[23])(?!\w|\.\d)",
    re.IGNORECASE,
)
# a mention preceded by words like these is a TARGET ("does X work in 3.0"), not the caller's version
_TARGET_BEFORE = re.compile(
    r"(?:upgrad\w*|migrat\w*|mov\w+|go(?:ing)?|switch\w*|work|works|exist|exists|available|supported|still|removed|gone|after)"
    r"\W+(?:\w+\W+){0,4}?(?:to|in|on|into|for)?\W*(?:acme[-_ ]?sdk\s*)?(?:version\s*)?$",
    re.IGNORECASE,
)
_MENTION_RE = re.compile(r"(?<![\w.])(?:acme[-_ ]?sdk\s+)?(?:v|version\s+)?(\d+\.\d+(?:\.\d+)?|[23])(?:\.x)?(?!\w|\.\d)", re.IGNORECASE)


def _is_target(text, start):
    return bool(_TARGET_BEFORE.search(text[max(0, start - 45):start]))


def _code_signals(text):
    """Version intervals implied by code pasted into the question, from the
    symbol table. Returns (lo, hi_exclusive, evidence) or None."""
    lo, hi, why = (2, 0), (99, 0), []

    def clamp(new_lo, new_hi, label):
        nonlocal lo, hi
        lo = max(lo, new_lo) if new_lo else lo
        hi = min(hi, new_hi) if new_hi else hi
        why.append(label)

    for hit in sym.extract_symbols(text, usage_only=True):
        if hit["status_kind"] in ("unknown", "export_unknown"):
            continue
        rec = sym.lifecycle(hit["id"])
        if rec is None:
            continue
        intro = sym.parse_exact_version(rec.get("introduced"))
        removed = sym.parse_exact_version(rec.get("removed"))
        # a symbol that exists in every version gives no signal
        if intro and intro <= (2, 0) and not removed:
            continue
        clamp(intro if intro and intro > (2, 0) else None, removed, f"{hit['id']} ({rec.get('introduced')}..{rec.get('removed') or 'now'})")
    if not why or lo >= hi:
        return None
    return lo, hi, ", ".join(why)


_ERR_ATTR = re.compile(r"has no attribute ['\"](\w+)['\"]")
_ERR_KW = re.compile(r"unexpected keyword argument ['\"](\w+)['\"]")
_ERR_IMPORT = re.compile(r"cannot import name ['\"](\w+)['\"]")


def _error_signals(text):
    """An error message pasted into the question is evidence about the version: "no attribute 'sendMessage'"
    means that method is GONE where the caller runs (3.0); "unexpected keyword argument 'api_key'" means it
    does not exist YET (older than 2.5). -> (lo, hi_exclusive, evidence) or None."""
    lo, hi, why = (2, 0), (99, 0), []
    names = [("attr", m.group(1)) for m in _ERR_ATTR.finditer(text)] + [("kw", m.group(1)) for m in _ERR_KW.finditer(text)] \
        + [("import", m.group(1)) for m in _ERR_IMPORT.finditer(text)]
    for kind, name in names:
        recs = [(f"Client.{name}", sym.lifecycle(f"Client.{name}"))] if kind == "attr" else (
            [(name, sym.lifecycle(name))] if kind == "import" else sym.params_named(name))
        for sid, rec in recs:
            if not rec:
                continue
            removed, intro = sym.parse_exact_version(rec.get("removed")), sym.parse_exact_version(rec.get("introduced"))
            if removed:                       # the name is gone, so the caller is on or after the removal
                lo = max(lo, removed)
                why.append(f"{sid} is missing for you (removed in {rec['removed']})")
            elif intro and intro > (2, 0):    # the name is not there yet, so the caller is older than its introduction
                hi = min(hi, intro)
                why.append(f"{sid} is missing for you (added in {rec['introduced']})")
    if not why or lo >= hi:
        return None
    return lo, hi, "; ".join(why)


def resolve_version(question, sdk_version=None, smart=True):
    """-> dict(version, major, source, confidence, minor_exact, evidence, target_version)"""
    out = {"version": None, "major": None, "source": "none", "confidence": "none",
           "minor_exact": False, "evidence": "no version evidence found", "target_version": None}

    def done(v, source, conf, evidence, exact=True):
        out.update(version=fmt((v[0], v[1] if v[1] is not None else 0)), major=major_tag(v), source=source,
                   confidence=conf, minor_exact=exact and v[1] is not None, evidence=evidence)
        return out

    meta = parse(sdk_version)
    if meta:
        out["target_version"] = _target_in(question)
        return done(meta, "request_metadata", "high", f"IDE/CLI sent sdk_version={sdk_version!r}")

    if not smart:
        out["target_version"] = None
        out.update(version=fmt(LATEST), major=major_tag(LATEST), source="defaulted_latest", confidence="low",
                   minor_exact=False, evidence="no sdk_version sent; defaulted to the latest release")
        return out

    out["target_version"] = _target_in(question)

    pins = [m for m in _PIN_RE.finditer(question or "")]
    if pins:
        m = pins[0]
        v = parse(m.group(2))
        if v:
            return done(v, "pinned_in_text", "high" if m.group(1) in (None, "==", "~=") else "medium",
                        f"found 'acme-sdk{m.group(1) or ''}{m.group(2)}' in the question")

    m = _STATED_RE.search(question or "")
    if m:
        v = parse(m.group(1))
        if v and not _is_target(question, m.start(1)):
            return done(v, "stated_in_text", "high", f"caller wrote '{m.group(0).strip()}'")

    err = _error_signals(question or "")
    if err:
        lo, hi, why = err
        if hi <= (3, 0):
            return done(lo, "inferred_from_error", "medium", f"error text in the question: {why}", exact=False)
        return done((3, 0), "inferred_from_error", "medium", f"error text in the question: {why}", exact=False)

    sig = _code_signals(question or "")
    if sig:
        lo, hi, why = sig
        if hi <= (3, 0):
            return done(lo, "inferred_from_code", "medium", f"pasted code only works on {fmt(lo)}..2.x ({why})", exact=False)
        if lo >= (3, 0):
            return done((3, 0), "inferred_from_code", "medium", f"pasted code only works on 3.0 ({why})", exact=False)

    for m in _MENTION_RE.finditer(question or ""):
        v = parse(m.group(1))
        if v and not _is_target(question, m.start()):
            return done(v, "mentioned", "medium", f"question mentions '{m.group(0).strip()}'", exact=v[1] is not None)

    return out


def _target_in(question):
    for m in _MENTION_RE.finditer(question or ""):
        v = parse(m.group(1))
        if v and _is_target(question, m.start()):
            return fmt((v[0], v[1] if v[1] is not None else 0))
    return None
