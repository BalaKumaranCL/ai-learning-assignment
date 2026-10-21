"""Build the drill logs and plant ONE bad answer in them.

    python plant_incident.py                       # incident #1 -> data/w11_prod_logs.jsonl (schema v1)
    python plant_incident.py --incident 2          # incident #2 -> data/w11_prod_logs_v2.jsonl (schema v2)

A squadmate can plant their own instead -- pick any time, user and question,
and DON'T tell the finder:

    python plant_incident.py --out data/my_drill.jsonl --schema v1 \
        --ts 2026-10-16T11:02:09 --user u-0042 --app slack-bot \
        --question "show me a code sample for streaming responses with Client.stream"

The planted line is not typed by hand: it is produced by running the shipped
service (prompt docs_v1, no version filter) and logging what it really said.
The script prints the planted trace id ONLY with --reveal, so the finder
isn't spoiled by reading the output.
"""

import argparse
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

import w11_logs as L  # noqa: E402

INCIDENTS = {
    # 1: sendMessage sample -- slack bot, no package version, Thursday afternoon
    1: dict(ts="2026-10-15T14:37:12", user="u-0417", app="slack-bot",
            question="give me a code sample for sending a message with the client",
            out="data/w11_prod_logs.jsonl", schema="v1"),
    # 2: pollStream sample -- a different symbol, a different day, a different app
    2: dict(ts="2026-10-17T09:05:41", user="u-0233", app="vscode-ext",
            question="show me a code sample for streaming responses with Client.stream",
            out="data/w11_prod_logs_v2.jsonl", schema="v2"),
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--incident", type=int, choices=sorted(INCIDENTS), default=1)
    ap.add_argument("--out")
    ap.add_argument("--schema", choices=["v1", "v2"])
    ap.add_argument("--ts")
    ap.add_argument("--user")
    ap.add_argument("--app")
    ap.add_argument("--question")
    ap.add_argument("--filter", default=None, help="sdk_version_filter the caller sent (default: none)")
    ap.add_argument("--reveal", action="store_true", help="print the planted trace id (spoils the drill)")
    a = ap.parse_args()

    d = dict(INCIDENTS[a.incident])
    for k in ("out", "schema", "ts", "user", "app", "question"):
        if getattr(a, k) is not None:
            d[k] = getattr(a, k)

    base = L.generate_base_traffic()
    traces, planted = L.plant_incident(base, d["ts"], d["user"], d["app"], d["question"], a.filter)
    path = d["out"] if os.path.isabs(d["out"]) else os.path.join(BASE, d["out"])
    L.write_logs(path, traces, d["schema"])
    print(f"wrote {len(traces)} log lines ({d['schema']} schema) to {path}; 1 planted.")
    if a.reveal:
        print("planted trace id:", planted["trace_id"])


if __name__ == "__main__":
    main()
