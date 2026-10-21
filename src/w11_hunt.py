"""The incident hunt: find one bad answer in the logs from a vague complaint.

The complaint ("a dev got a code sample using a method we deprecated, some
time last week") gives exactly three usable clues and nothing else:
  * a time window  -> last week
  * an input type  -> a code-sample request
  * an output fact -> the generated sample calls a deprecated method
It gives NO trace id, NO user, NO package version.

hunt_v1 works on logs as they shipped: the answer is only free text, so the
output fact has to be found by scanning every answer for the deprecated call
patterns, and a legitimate mention (a migration note, or a caller who asked
for v2) has to be ruled out by hand-written rules.

hunt_indexed works on schema-v2 logs, where the same fact was computed once,
at write time, into output_flags.deprecated_symbols_unflagged.

Every step records how many log lines it looked at and how long it took, so
the write-up can say which step the time went into.
"""

import time
from datetime import datetime

import deprecations


def _step(steps, name, before, after, t0):
    steps.append({"step": name, "in": before, "out": after, "ms": round((time.perf_counter() - t0) * 1000, 2)})


def in_window(line, start, end):
    ts = datetime.fromisoformat(line["ts"])
    return start <= ts < end


def hunt_v1(lines, window):
    start, end = window
    steps = []
    t_all = time.perf_counter()

    t0 = time.perf_counter()
    in_w = [l for l in lines if in_window(l, start, end)]
    _step(steps, "slice: time window (last week)", len(lines), len(in_w), t0)

    t0 = time.perf_counter()
    hits = [l for l in in_w if l["answered"] and deprecations.find_deprecated_symbols(l["answer"])]
    _step(steps, "scan answered text for deprecated call patterns", len(in_w), len(hits), t0)

    t0 = time.perf_counter()
    not_legit = [l for l in hits if l["sdk_version_filter"] != "v2"]
    _step(steps, "rule out callers who explicitly asked for v2", len(hits), len(not_legit), t0)

    t0 = time.perf_counter()
    candidates = [l for l in not_legit if not deprecations.has_migration_note(l["answer"])]
    _step(steps, "rule out migration notes (answer says 'deprecated'/'renamed')", len(not_legit), len(candidates), t0)

    return {"candidates": candidates, "steps": steps,
            "total_ms": round((time.perf_counter() - t_all) * 1000, 2)}


def hunt_indexed(lines, window):
    start, end = window
    steps = []
    t_all = time.perf_counter()

    t0 = time.perf_counter()
    in_w = [l for l in lines if in_window(l, start, end)]
    _step(steps, "slice: time window (last week)", len(lines), len(in_w), t0)

    t0 = time.perf_counter()
    candidates = [l for l in in_w if l["output_flags"]["deprecated_symbols_unflagged"]]
    _step(steps, "slice: output_flags.deprecated_symbols_unflagged is non-empty", len(in_w), len(candidates), t0)

    return {"candidates": candidates, "steps": steps,
            "total_ms": round((time.perf_counter() - t_all) * 1000, 2)}


def input_only_search(lines, window):
    """The tempting wrong search: grep the QUESTION for a deprecated name.
    Kept so the write-up can show how many wrong leads it produces."""
    start, end = window
    return [l for l in lines if in_window(l, start, end) and deprecations.find_deprecated_symbols(l["question"])]


def fmt_mmss(seconds):
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:05.2f}"
