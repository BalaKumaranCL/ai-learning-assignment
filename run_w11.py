"""Entry point: python run_w11.py

Prerequisite (once): python plant_incident.py ; python plant_incident.py --incident 2
Writes output/w11/:
  trace.json          the found trace, exactly as logged (schema v1)
  replay_summary.json last week's real requests replayed under docs_v1 vs docs_v2
  cost_by_stage.md    cost/query for the incident request, by stage, before and after
  tenx.md             one line + the numbers behind it
drill.md, the suite RED/GREEN logs and the README are written by hand / by
run_w11_suite.py -- see README-w11-task-e.md.

Everything here is computed from data/w11_prod_logs.jsonl and the shipped
service; nothing is typed in. The ASSUMED provider limits in tenx.md are
the constants below.
"""

import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

import deprecations  # noqa: E402
import w11_hunt as H  # noqa: E402
import w11_logs as L  # noqa: E402
import w11_service as S  # noqa: E402

OUT = os.path.join(BASE, "output", "w11")
WINDOW = (datetime(2026, 10, 12), datetime(2026, 10, 19))

# ---- ASSUMED production limits (replace with your real contract). ----
PROVIDER_RPM_LIMIT = 50          # requests / minute for the generation model
PROVIDER_TPM_LIMIT = 50_000      # input+output tokens / minute for the generation model
P99_LATENCY_SLO_MS = 2_500       # what the docs widget promises its users
MONTHLY_BUDGET_USD = 100.0       # what the team is allowed to spend on this assistant
WEEKS_PER_MONTH = 4.345


def _write(name, text):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def stage_costs(trace):
    out = {"retrieval": 0.0, "generation": 0.0, "tools": 0.0}
    calls = Counter()
    ms = {"retrieval": 0.0, "generation": 0.0, "tools": 0.0}
    tok = {"retrieval": 0, "generation": 0, "tools": 0}
    for s in trace["spans"]:
        out[s["stage"]] += s["cost_usd"]
        ms[s["stage"]] += s["latency_ms"]
        tok[s["stage"]] += s["tokens_in"] + s["tokens_out"]
        calls[s["stage"]] += 1
    return out, ms, tok, calls


def replay(lines, prompt_version):
    traces = []
    for l in lines:
        req = {"ts": l["ts"], "user_id": l["user_id"], "app": l["app"], "question": l["question"],
               "sdk_version_filter": l["sdk_version_filter"]}
        traces.append(S.run_request(req, l["trace_id"], prompt_version=prompt_version))
    return traces


def summarize(traces):
    lat = [t["totals"]["latency_ms"] for t in traces]
    return {
        "requests": len(traces),
        "answered_rate": round(sum(t["answered"] for t in traces) / len(traces), 4),
        "unflagged_deprecated_answers": sum(
            bool(deprecations.unflagged_deprecated_symbols(t["answer"], t["sdk_version_filter"], t["answered"]))
            for t in traces),
        "mean_cost_usd": round(statistics.mean(t["totals"]["cost_usd"] for t in traces), 8),
        "mean_tokens": round(statistics.mean(t["totals"]["tokens_in"] + t["totals"]["tokens_out"] for t in traces), 1),
        "p50_latency_ms": round(pct(lat, 50), 1),
        "p99_latency_ms": round(pct(lat, 99), 1),
    }


def peak_minute(traces):
    rpm, tpm = Counter(), Counter()
    for t in traces:
        key = t["ts"][:16]
        rpm[key] += 1
        # only the generation span goes to the rate-limited provider
        tpm[key] += sum(s["tokens_in"] + s["tokens_out"] for s in t["spans"] if s["stage"] == "generation")
    k_r = max(rpm, key=rpm.get)
    k_t = max(tpm, key=tpm.get)
    return (k_r, rpm[k_r]), (k_t, tpm[k_t])


def main():
    os.makedirs(OUT, exist_ok=True)
    lines = L.read_logs(os.path.join(BASE, "data", "w11_prod_logs.jsonl"))

    # ---- 1. the found trace -> trace.json
    found = H.hunt_v1(lines, WINDOW)["candidates"]
    assert len(found) == 1, f"expected exactly one candidate, got {len(found)}"
    bad = found[0]
    _write("trace.json", json.dumps(bad, indent=2) + "\n")

    # ---- 2. replay last week under both prompt versions
    week = [l for l in lines if H.in_window(l, *WINDOW)]
    v1, v2 = replay(week, "docs_v1"), replay(week, "docs_v2")
    s1, s2 = summarize(v1), summarize(v2)
    changed = sum(a["answer"] != b["answer"] for a, b in zip(v1, v2))
    # replay under v1 must equal what was logged -- otherwise the replay isn't a replay
    assert all(a["answer"] == l["answer"] for a, l in zip(v1, week)), "v1 replay diverged from the logs"
    _write("replay_summary.json", json.dumps(
        {"window": "2026-10-12..2026-10-18", "docs_v1": s1, "docs_v2": s2, "answers_that_changed": changed}, indent=2) + "\n")

    # ---- 3. cost by stage for the incident request, before / after
    inc_req = {"ts": bad["ts"], "user_id": bad["user_id"], "app": bad["app"],
               "question": bad["question"], "sdk_version_filter": bad["sdk_version_filter"]}
    after = S.run_request(inc_req, bad["trace_id"], prompt_version="docs_v2")
    cb, mb, tb, nb = stage_costs(bad)
    ca, ma, ta, na = stage_costs(after)
    tot_b, tot_a = sum(cb.values()), sum(ca.values())

    def row(stage):
        return (f"| {stage.capitalize()} | {nb[stage]} | {tb[stage]:,} | ${cb[stage]:.8f} | {cb[stage] / tot_b:.1%} | "
                f"{na[stage]} | {ta[stage]:,} | ${ca[stage]:.8f} | {ca[stage] / tot_a:.1%} |")

    pop = {k: [0.0, 0.0] for k in ("retrieval", "generation", "tools")}
    for t in v1:
        for k, v in stage_costs(t)[0].items():
            pop[k][0] += v
    for t in v2:
        for k, v in stage_costs(t)[0].items():
            pop[k][1] += v
    n = len(week)
    md = [
        "# cost_by_stage.md -- cost per query for the incident request",
        "",
        f"Request: trace `{bad['trace_id']}` (user {bad['user_id']}, {bad['app']}, {bad['ts']}): "
        f"\"{bad['question']}\", no sdk_version_filter.",
        "",
        "Before = the logged request, served by `docs_v1`. After = the SAME request re-run through the shipped service "
        "under `docs_v2`. Stage = the `stage` field on each span in `trace.json`.",
        "",
        "| Stage | calls (before) | tokens | $ per query | share | calls (after) | tokens | $ per query | share |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        row("retrieval"), row("generation"), row("tools"),
        f"| **Total** | | {sum(tb.values()):,} | **${tot_b:.8f}** | 100% | | {sum(ta.values()):,} | **${tot_a:.8f}** | 100% |",
        "",
        f"Cost moved by **{(tot_a / tot_b - 1):+.1%}** per query ({'$' + format(tot_a - tot_b, '+.8f')}). "
        "Where it moved, by stage: " + ", ".join(
            f"{k} {'$' + format(ca[k] - cb[k], '+.8f')}" for k in ("retrieval", "generation", "tools")) + ".",
        "",
        "## Same split over all of last week's traffic",
        "",
        f"Replaying all {n} requests from 2026-10-12..18 under each version (answers under `docs_v1` match the logs exactly):",
        "",
        "| Stage | docs_v1 $/query | docs_v2 $/query |",
        "|---|---:|---:|",
    ] + [f"| {k.capitalize()} | ${pop[k][0] / n:.8f} | ${pop[k][1] / n:.8f} |" for k in ("retrieval", "generation", "tools")] + [
        f"| **Total** | **${s1['mean_cost_usd']:.8f}** | **${s2['mean_cost_usd']:.8f}** |",
        "",
        "## What these dollars are (read this before quoting them)",
        "",
        "- **Generation** = tokens x the Week-7 Haiku-class price assumption "
        f"(${S.PRICE_PER_1K_INPUT_USD}/1K in, ${S.PRICE_PER_1K_OUTPUT_USD}/1K out). Tokens are estimated as chars/4, not tokenised.",
        f"- **Retrieval** = query embedding (${S.EMBED_USD_PER_1K_TOKENS}/1K tokens) + one vector-store read (${S.VECTOR_QUERY_USD}). "
        "The repo's real retriever is local TF-IDF/BM25 and costs nothing; this is what a hosted index would charge. An assumption.",
        f"- **Tools** = ${S.TOOL_CALL_USD} per hosted `check_deprecation` call. An assumption. `docs_v1` makes no tool calls at all, so its tools cost is exactly $0.",
        "- None of this is billing data. Change the constants at the top of `src/w11_service.py` and every number here moves with them.",
        "",
        f"Retrieval is {pop['retrieval'][1] / sum(v[1] for v in pop.values()):.1%} of spend under `docs_v2`, generation "
        f"{pop['generation'][1] / sum(v[1] for v in pop.values()):.1%}: the fix did not touch the expensive stage, "
        "it added a (cheap) tool stage and a deeper retrieval for code samples.",
        "",
    ]
    _write("cost_by_stage.md", "\n".join(md))

    # ---- 4. 10x
    (rk, rpm), (tk, tpm) = peak_minute(v2)
    weekly = len(week)
    monthly_cost = weekly * WEEKS_PER_MONTH * s2["mean_cost_usd"]
    breaks = {
        "API rate limit (requests/min)": PROVIDER_RPM_LIMIT / rpm,
        "API rate limit (tokens/min)": PROVIDER_TPM_LIMIT / tpm,
        "Cost (monthly budget)": MONTHLY_BUDGET_USD / monthly_cost,
    }
    first = min(breaks, key=breaks.get)
    lines10 = [
        "# tenx.md",
        "",
        f"**At 10x volume the API rate limit breaks first: today's busiest minute ({rk.replace('T', ' ')}) is {rpm} requests/min, "
        f"so 10x is {rpm * 10} requests/min against an assumed {PROVIDER_RPM_LIMIT}/min limit "
        f"(it would hit the limit at {breaks['API rate limit (requests/min)']:.1f}x).**",
        "",
        "## Numbers behind it (all from last week's logs, replayed under the shipped `docs_v2`)",
        "",
        "| What | Today | At 10x | Limit (ASSUMED) | Breaks at | Breaks at 10x? |",
        "|---|---:|---:|---:|---:|---|",
        f"| Peak requests/min ({rk.replace('T', ' ')}) | {rpm} | {rpm * 10} | {PROVIDER_RPM_LIMIT} | "
        f"{breaks['API rate limit (requests/min)']:.1f}x | {'**YES**' if rpm * 10 > PROVIDER_RPM_LIMIT else 'no'} |",
        f"| Peak generation tokens/min ({tk.replace('T', ' ')}) | {tpm:,} | {tpm * 10:,} | {PROVIDER_TPM_LIMIT:,} | "
        f"{breaks['API rate limit (tokens/min)']:.1f}x | {'**YES**' if tpm * 10 > PROVIDER_TPM_LIMIT else 'no'} |",
        f"| Monthly cost ({weekly} req/week x {WEEKS_PER_MONTH} x ${s2['mean_cost_usd']:.6f}) | ${monthly_cost:.2f} | ${monthly_cost * 10:.2f} | "
        f"${MONTHLY_BUDGET_USD:.0f} | {breaks['Cost (monthly budget)']:.0f}x | {'**YES**' if monthly_cost * 10 > MONTHLY_BUDGET_USD else 'no'} |",
        f"| p99 latency (modelled) | {s2['p99_latency_ms']:.0f} ms | {s2['p99_latency_ms']:.0f} ms* | {P99_LATENCY_SLO_MS} ms | "
        f"n/a* | {'already over today (not a volume effect)' if s2['p99_latency_ms'] > P99_LATENCY_SLO_MS else 'no'} |",
        "",
        "\\* Latency is modelled per request from span constants, with no shared queue, so it does not grow with volume by "
        "construction. In reality it is the second thing to go: once requests exceed the rate limit they get HTTP 429s and "
        "retries, and p99 latency then includes the retry wait. This model cannot show that number, so it is not claimed.",
        "",
        f"Separate finding: modelled p99 ({s2['p99_latency_ms']:.0f} ms) is ALREADY over the assumed {P99_LATENCY_SLO_MS} ms target at today's volume. "
        f"It comes from the modelled slow-provider tail ({S.SLOW_PROVIDER_RATE:.1%} of generations x{S.SLOW_PROVIDER_MULTIPLIER}), "
        "not from load, so it is reported here but is not the answer to \"what breaks at 10x\".",
        "",
        "## Assumptions you must replace with your real contract",
        "",
        f"- Generation model limit: **{PROVIDER_RPM_LIMIT} requests/min and {PROVIDER_TPM_LIMIT:,} tokens/min** (a low-tier assumption; "
        "check your actual account limits -- the verdict flips if your limit is >= "
        f"{rpm * 10} requests/min).",
        f"- p99 SLO {P99_LATENCY_SLO_MS} ms; monthly budget ${MONTHLY_BUDGET_USD:.0f}.",
        "- Per-minute peaks use the clock minute of each request's `ts`; the traffic is synthetic (seeded) with a 10:00 stand-up burst, "
        "so the peak is realistic in shape but is not a measured production peak.",
        f"- The first thing to break is chosen by the smallest break-multiplier above: **{first}** "
        f"at {breaks[first]:.1f}x.",
        "",
    ]
    _write("tenx.md", "\n".join(lines10))

    print(json.dumps({"docs_v1": s1, "docs_v2": s2, "changed": changed}, indent=2))
    print("incident cost before/after:", tot_b, tot_a)
    print("peak", (rk, rpm), (tk, tpm), "monthly", monthly_cost, "breaks", breaks)


if __name__ == "__main__":
    main()
