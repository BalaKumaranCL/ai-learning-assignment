"""Production logs for the Week-11 incident drill.

Three jobs:
  1. generate_base_traffic -- a week-plus of realistic requests, each answered
     by the REAL w11_service (so every log line is a genuine trace, not a
     hand-typed row).
  2. plant_incident        -- what the squadmate does: add one bad answer, at a
     time the finder doesn't know, from a caller the finder doesn't know.
  3. to_log_line           -- how a trace is written to disk. Two schemas:
       "v1" = what shipped. It logs the answer text, the context ids, spans,
              tokens, cost, prompt version -- but nothing about WHAT KIND of
              request it was or WHAT IS IN the answer.
       "v2" = the bonus wiring: adds input_type, retrieved_sdk_versions and
              output_flags.deprecated_symbols_unflagged, computed at write time.

Trace ids are hashes, not a counter, so the bad one cannot be found by
guessing where an id "looks different".
"""

import hashlib
import json
import random
from datetime import datetime, timedelta

import deprecations
import w11_service

BASE_DAY = datetime(2026, 10, 12)      # Monday; "last week" = 10-12 .. 10-18
DAYS = 9                               # 10-12 .. 10-20 (two days of "this week" noise)
SEED = 11
# The drill logs are last week's traffic, which was served by docs_v1. The
# active version has since been bumped, so logs must never default to it.
LOGGED_PROMPT_VERSION = "docs_v1"

APPS = ["web-widget", "slack-bot", "cli", "vscode-ext"]
# Apps that know the caller's package version pass a filter; the Slack bot never does.
APP_FILTER = {"web-widget": "v3", "slack-bot": None, "cli": "v3", "vscode-ext": "v3"}

# ---- question pool -------------------------------------------------------
# (question, sdk_version_filter or "APP" = whatever the calling app sends)
FACTUAL = [
    "What is the default value of retry_backoff_ms in Client.send()?",
    "What is the type and default value of timeout_ms in Client.send()?",
    "What parameter is required when creating an AuthConfig for the Client?",
    "What does Client.stream() return?",
    "Which exception is raised when timeout_ms is exceeded?",
    "Which fields are required in the Response object?",
    "What is the default value of max_retries in Client.send()?",
    "How long does the client wait between retries by default?",
    "What is the default region in AuthConfig?",
    "when should I call close() on my client",
    "does idempotency key prevent duplicate requests",
    "how do i get streaming responses",
    "What is the rate limit for Client.send()?",
    "How many concurrent requests does the SDK support?",
    "What uptime SLA does the SDK guarantee?",
]
MIGRATION = [  # the question itself names a deprecated symbol: a decoy for input-only searches
    "Our v2 code calls client.sendMessage(message=\"hi\"). Is that still valid in v3?",
    "Is Client.sendMessage deprecated?",
    "Is Client.pollStream deprecated in v3, and what replaced it?",
    "v2's AuthConfig used a token field. Is token still accepted in v3?",
]
CODE_SAMPLE_V3 = [  # code-sample requests that land on a genuine v3 sample
    "code sample for Client.send with timeout_ms and retry_backoff_ms",
    "code sample for Client.send with timeout_ms",
]
V2_LEGIT = [  # callers who explicitly asked for v2: v2 code is the RIGHT answer
    ("In SDK v2, show me a code sample of Client.sendMessage", "v2"),
    ("In SDK v2, show me a code sample for streaming with Client.pollStream", "v2"),
]


def _ts(rng, day_index):
    # business-hours-heavy, with a 10:00 stand-up burst
    base = BASE_DAY + timedelta(days=day_index)
    if rng.random() < 0.18:
        minute = rng.randint(0, 6)
        return base + timedelta(hours=10, minutes=minute, seconds=rng.randint(0, 59))
    hour = int(rng.triangular(8, 19, 13))
    return base + timedelta(hours=hour, minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))


def _trace_id(*parts):
    return "t_" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


def _clean_pairs(prompt_version):
    """(question, filter) pairs the shipped service answers WITHOUT an
    unflagged deprecated symbol. The drill needs exactly one planted bad
    answer in the logs, so the background traffic is drawn only from
    requests that don't trigger the bug. Returns (clean, quarantined) --
    the quarantined ones are real failures found while building this, and
    are reported in the README rather than hidden."""
    pairs = [(q, f) for q in FACTUAL + MIGRATION + CODE_SAMPLE_V3 for f in (None, "v3")] + V2_LEGIT
    clean, quarantined = set(), []
    for q, f in pairs:
        t = w11_service.run_request({"ts": "2026-10-12T00:00:00", "user_id": "probe", "app": "probe",
                                     "question": q, "sdk_version_filter": f}, "probe", prompt_version=prompt_version)
        if deprecations.unflagged_deprecated_symbols(t["answer"], f, t["answered"]):
            quarantined.append((q, f))
        else:
            clean.add((q, f))
    return clean, quarantined


def quarantined_pairs(prompt_version=None):
    return _clean_pairs(prompt_version or LOGGED_PROMPT_VERSION)[1]


def generate_base_traffic(prompt_version=None, per_day=(95, 125)):
    """Returns a list of full traces, sorted by time, all answered by
    `prompt_version` (default: whatever is active)."""
    prompt_version = prompt_version or LOGGED_PROMPT_VERSION
    rng = random.Random(SEED)
    clean, _ = _clean_pairs(prompt_version)
    traces = []
    for d in range(DAYS):
        for _ in range(rng.randint(*per_day)):
            ts = _ts(rng, d)
            app = rng.choice(APPS)
            roll = rng.random()
            if roll < 0.58:
                question, flt = rng.choice(FACTUAL), APP_FILTER[app]
            elif roll < 0.74:
                question, flt = rng.choice(MIGRATION), APP_FILTER[app]
            elif roll < 0.92:
                # code-sample callers here always send their package version
                question, flt = rng.choice(CODE_SAMPLE_V3), "v3"
            else:
                question, flt = rng.choice(V2_LEGIT)
            if (question, flt) not in clean:
                flt = "v3"  # the caller sent its package version after all
            user = f"u-{rng.randint(1, 600):04d}"
            req = {"ts": ts.isoformat(timespec="seconds"), "user_id": user, "app": app,
                   "question": question, "sdk_version_filter": flt}
            tid = _trace_id(req["ts"], user, question, len(traces))
            traces.append(w11_service.run_request(req, tid, prompt_version=prompt_version))
    traces.sort(key=lambda t: t["ts"])
    return traces


def plant_incident(traces, ts, user_id, app, question, sdk_version_filter=None, prompt_version=None):
    """The squadmate's job: run ONE request through the shipped service and
    drop the resulting trace into the log. Returns (traces, planted_trace)."""
    prompt_version = prompt_version or LOGGED_PROMPT_VERSION
    req = {"ts": ts, "user_id": user_id, "app": app, "question": question,
           "sdk_version_filter": sdk_version_filter}
    planted = w11_service.run_request(req, _trace_id("planted", ts, user_id), prompt_version=prompt_version)
    out = sorted(traces + [planted], key=lambda t: t["ts"])
    return out, planted


# ---- on-disk schemas -----------------------------------------------------
V1_FIELDS = ("trace_id", "ts", "user_id", "app", "prompt_version", "retriever_version",
             "sdk_version_filter", "question", "answered", "answer", "cited_chunk_id",
             "retrieved_chunk_ids", "spans", "totals")


def output_flags(trace):
    return {
        "deprecated_symbols_unflagged": deprecations.unflagged_deprecated_symbols(
            trace["answer"], trace["sdk_version_filter"], trace["answered"]),
        "deprecated_symbols_any": deprecations.find_deprecated_symbols(trace["answer"]),
        "has_code_fence": "```" in trace["answer"],
    }


def to_log_line(trace, schema="v1"):
    line = {k: trace[k] for k in V1_FIELDS}
    if schema == "v2":
        line["input_type"] = trace["input_type"]
        line["retrieved_sdk_versions"] = trace["retrieved_sdk_versions"]
        line["output_flags"] = output_flags(trace)
    return line


def write_logs(path, traces, schema="v1"):
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for t in traces:
            fh.write(json.dumps(to_log_line(t, schema)) + "\n")


def read_logs(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
