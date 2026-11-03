"""Week 12: cost per question by stage, and the 10x plan -- what breaks first, with the number behind it.

MEASURED here: tokens per stage, MCP calls, the MCP round trip and the code check (stopwatch), laps. MODELLED here
(repo convention, w12_llm.py): the model calls' dollars and latency. ASSUMED here (the constants in ASSUMPTIONS): how many
integrators ask how often, and the provider limits. Change an assumption and `breaks_at` moves with it; none of these are
billing or traffic data, and the report says so.

"1x" is a pilot to 10% of integrators (900 people); "10x" is all 9,000.
"""

import statistics

ASSUMPTIONS = {
    "integrators_at_1x": 900, "integrators_at_10x": 9000,
    "active_share_per_day": 0.35, "questions_per_active_integrator_per_day": 8, "peak_hour_share_of_daily": 0.15,
    "llm_requests_per_min_limit": 1000, "llm_input_tokens_per_min_limit": 250_000,
    "p99_latency_target_ms": 3000, "monthly_budget_usd": 2000, "days_per_month": 30, "mcp_server_processes": 1,
}


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def per_question(results):
    """results: engine results (dicts with spans/totals/by_stage). -> table by stage + totals."""
    stages = {}
    for r in results:
        for st, v in r["by_stage"].items():
            if st in ("request", "agent"):
                continue
            a = stages.setdefault(st, {"cost": [], "tokens_in": [], "tokens_out": [], "latency_ms": [], "spans": []})
            a["cost"].append(v["cost_usd"])
            a["tokens_in"].append(v["tokens_in"])
            a["tokens_out"].append(v["tokens_out"])
            a["latency_ms"].append(v["latency_ms"])
            a["spans"].append(v["spans"])
    n = len(results)
    table = []
    for st, a in stages.items():
        pad = [0.0] * (n - len(a["cost"]))
        table.append({"stage": st, "mean_cost_usd": sum(a["cost"]) / n, "mean_tokens_in": sum(a["tokens_in"]) / n,
                      "mean_tokens_out": sum(a["tokens_out"]) / n, "mean_latency_ms": sum(a["latency_ms"]) / n,
                      "mean_spans": sum(a["spans"]) / n, "kind": {"plan": "modelled model call", "generate": "modelled model call",
                                                                 "tool": "MCP round trip (measured) + assumed call price",
                                                                 "gate": "local code check (measured)", "resolve": "local (measured)",
                                                                 "redact": "local (measured)"}.get(st, "")})
    table.sort(key=lambda x: -x["mean_cost_usd"])
    total_cost = [r["totals"]["cost_usd"] for r in results]
    lat = [r["totals"]["latency_ms"] for r in results]
    return {"n": n, "stages": table, "cost_mean": sum(total_cost) / n, "cost_p50": pct(total_cost, .5), "cost_p95": pct(total_cost, .95),
            "cost_max": max(total_cost), "latency_p50": pct(lat, .5), "latency_p95": pct(lat, .95), "latency_p99": pct(lat, .99),
            "tokens_in_mean": sum(r["totals"]["tokens_in"] for r in results) / n,
            "tokens_out_mean": sum(r["totals"]["tokens_out"] for r in results) / n,
            "laps_mean": sum(r["laps"] for r in results) / n,
            "mcp_calls_mean": sum(sum(1 for s in r["spans"] if s["side"] == "server") for r in results) / n}


def tenx(results, a=ASSUMPTIONS):
    pq = per_question(results)
    qd1 = a["integrators_at_1x"] * a["active_share_per_day"] * a["questions_per_active_integrator_per_day"]
    peak_qpm_1x = qd1 * a["peak_hour_share_of_daily"] / 60
    llm_calls = pq["laps_mean"] + 1
    tok = pq["tokens_in_mean"]
    server = [s["latency_ms"] for r in results for s in r["spans"] if s["side"] == "server"]
    svc_ms = statistics.mean(server) if server else 0.0
    rows = [
        {"constraint": "LLM requests per minute", "load_at_1x": peak_qpm_1x * llm_calls, "limit": a["llm_requests_per_min_limit"],
         "breaks_at": a["llm_requests_per_min_limit"] / (peak_qpm_1x * llm_calls), "basis": f"{llm_calls:.1f} model calls per question (laps + compose)"},
        {"constraint": "LLM input tokens per minute", "load_at_1x": peak_qpm_1x * tok, "limit": a["llm_input_tokens_per_min_limit"],
         "breaks_at": a["llm_input_tokens_per_min_limit"] / (peak_qpm_1x * tok), "basis": f"{tok:,.0f} input tokens per question (transcript resent every lap)"},
        {"constraint": "Monthly budget", "load_at_1x": qd1 * a["days_per_month"] * pq["cost_mean"], "limit": a["monthly_budget_usd"],
         "breaks_at": a["monthly_budget_usd"] / (qd1 * a["days_per_month"] * pq["cost_mean"]), "basis": f"${pq['cost_mean']:.5f} per question"},
        {"constraint": "MCP server throughput (1 process, serial)",
         "load_at_1x": peak_qpm_1x / 60 * pq["mcp_calls_mean"] * svc_ms / 1000,   # utilisation = arrivals/s x service s
         "limit": 1.0, "breaks_at": (1.0 / (peak_qpm_1x / 60 * pq["mcp_calls_mean"] * svc_ms / 1000)) if svc_ms else float("inf"),
         "basis": f"{pq['mcp_calls_mean']:.1f} calls per question x {svc_ms:.1f} ms measured server time per call"},
    ]
    p99 = pq["latency_p99"]
    for r in rows:
        r["breaks_at"] = round(r["breaks_at"], 1)
    rows.sort(key=lambda r: r["breaks_at"])
    return {"per_question": pq, "constraints": rows, "p99_ms": p99, "p99_target_ms": a["p99_latency_target_ms"],
            "p99_breached_at_1x": p99 > a["p99_latency_target_ms"], "queries_per_day_1x": qd1, "queries_per_day_10x": qd1 * 10,
            "peak_questions_per_min_1x": peak_qpm_1x, "first_to_break": rows[0], "assumptions": a, "mcp_service_ms": svc_ms}
