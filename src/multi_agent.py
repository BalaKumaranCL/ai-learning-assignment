"""Week 10 docs squad: an ORCHESTRATOR that splits a migration question and
delegates to two NARROW workers, then writes the final answer.

    orchestrator  -- no tools; decomposes, delegates, synthesises
    version worker -- ONE tool: check_deprecation
    code-sample worker -- TWO tools: get_openapi_spec, search_docs
                         (deliberately NOT check_deprecation -- giving it every
                         tool would delete the narrow-prompt/fewer-tools idea
                         that is the only plausible source of a multi-agent win)

Context strategy (the brief warns against measuring a bad one): workers get
only a minimal hand-off payload -- the sub-task, the TARGET SDK VERSION, the
current endpoint name, and the version worker's one-line report -- never the
whole v2/v3 reference, and never without the version.

Same simulated-LLM convention as the rest of the repo (see llm_sim.py):
there is no live model call anywhere. Every "model call" below is one
plan_step / compose_answer from llm_sim, billed by estimate_tokens() on the
text that call would have been sent (its prompt + everything resent) plus the
text it would have produced, at llm_sim's documented price constants. The
single-agent arm (agent_loop.run_agent) is billed the same way, so tokens
are comparable.

Every model call and every message that crosses an agent boundary is
appended to a ledger -> handoffs.log.
"""

from agent_tools import call_tool
from llm_sim import (
    GATHERED_KEY_BY_TOOL,
    PRICE_PER_1K_INPUT_USD,
    PRICE_PER_1K_OUTPUT_USD,
    compose_answer,
    estimate_tokens,
    plan_step,
)

ORCH_SYSTEM = (
    "You are the orchestrator of a docs migration squad. Split the developer's question into a "
    "version/deprecation check and a code-sample/parameters lookup, delegate each to its worker, "
    "then write the final answer from their reports."
)
VERSION_SYSTEM = (
    "You are the version/deprecation worker. Your only tool is check_deprecation. Report whether the "
    "named endpoint is deprecated at the given SDK version, and its replacement."
)
CODE_SYSTEM = (
    "You are the code-sample worker. Your tools are get_openapi_spec and search_docs. Given the target "
    "SDK version and the current endpoint name, report its parameters and a usage example. "
    "Do not check deprecation."
)

BUCKET_DECOMPOSE = "orchestrator: decompose (question in)"
BUCKET_VERSION = "orchestrator -> version worker (delegation + worker calls)"
BUCKET_REPLAN = "orchestrator: re-plan after version report (resend of question + report)"
BUCKET_CODE = "orchestrator -> code-sample worker (delegation + worker calls)"
BUCKET_SYNTH = "orchestrator: synthesis (resend of both worker reports)"

MAX_WORKER_LAPS = 6
PARTIAL_DISCLOSURE = (
    "[PARTIAL ANSWER: the version/deprecation check was unavailable (worker returned HTTP 500 after "
    "retrying), so the deprecation status below is NOT verified.]"
)


class Ledger:
    """Every model call (billed) and every cross-agent message (counted)."""

    def __init__(self, question_id):
        self.question_id = question_id
        self.rows = []
        self.model_calls = 0
        self.tool_calls = 0
        self.hops = 0
        self.total_tokens = 0
        self.total_cost = 0.0

    def llm(self, agent, bucket, in_text, out_text):
        in_tok, out_tok = estimate_tokens(in_text), estimate_tokens(out_text)
        self.model_calls += 1
        self.total_tokens += in_tok + out_tok
        self.total_cost += in_tok / 1000 * PRICE_PER_1K_INPUT_USD + out_tok / 1000 * PRICE_PER_1K_OUTPUT_USD
        self.rows.append({
            "kind": "LLM", "question_id": self.question_id, "agent": agent, "bucket": bucket,
            "in_tokens": in_tok, "out_tokens": out_tok,
        })

    def handoff(self, src, dst, text):
        self.hops += 1
        self.rows.append({
            "kind": "HANDOFF", "question_id": self.question_id, "src": src, "dst": dst,
            "payload_tokens": estimate_tokens(text),
        })

    def bucket_tokens(self):
        out = {}
        for r in self.rows:
            if r["kind"] == "LLM":
                out[r["bucket"]] = out.get(r["bucket"], 0) + r["in_tokens"] + r["out_tokens"]
        return out


def _version_worker_service(args, injected_failure):
    """The version worker as a remote service: (HTTP-style status, body)."""
    if injected_failure:
        return 500, {"error": "Internal Server Error"}
    return 200, call_tool("check_deprecation", args)


def _run_version_worker(ledger, task, args, injected_failure):
    """One delegation to the version worker (2 model calls). Returns (status, data, report)."""
    ledger.handoff("orchestrator", "version-worker", task)
    ledger.llm("version-worker", BUCKET_VERSION, f"{VERSION_SYSTEM}\n{task}", f"CALL check_deprecation({args})")
    ledger.tool_calls += 1
    status, body = _version_worker_service(args, injected_failure)
    if status != 200:
        report = f"ERROR: check_deprecation failed with HTTP {status} ({body['error']})"
        ledger.llm("version-worker", BUCKET_VERSION, f"{VERSION_SYSTEM}\n{task}\nOBSERVATION[check_deprecation]: {status} {body}", report)
        ledger.handoff("version-worker", "orchestrator", report)
        return status, None, report
    if body["deprecated"]:
        report = (
            f"{body['name']} is deprecated in {body['api_version']}; replacement {body['replacement']} "
            f"(documented under {body['lookup_key']}). {body['note']}"
        )
    else:
        report = f"{body['name']} is not deprecated in {body['api_version']}."
    ledger.llm("version-worker", BUCKET_VERSION, f"{VERSION_SYSTEM}\n{task}\nOBSERVATION[check_deprecation]: {body}", f"REPORT: {report}")
    ledger.handoff("version-worker", "orchestrator", report)
    return status, body, report


def _run_code_worker(ledger, question_meta, payload, dep, flag):
    """Code-sample worker loop (same stand-in planner as the single agent, but
    check_deprecation is marked as not-its-tool). Returns (gathered, report)."""
    ledger.handoff("orchestrator", "code-sample-worker", payload)
    gathered = {"deprecation": dep} if dep is not None else {}
    called = ["check_deprecation"]  # not this worker's tool: plan_step must never pick it
    transcript = []
    report = ""
    for lap in range(1, MAX_WORKER_LAPS + 1):
        decision, out_text = plan_step(question_meta, gathered, called, lap, require_spec_after_deprecation=flag)
        ledger.llm("code-sample-worker", BUCKET_CODE, "\n".join([CODE_SYSTEM, payload] + transcript), out_text)
        if decision["type"] == "final_answer":
            report = decision["answer"]
            break
        name, args = decision["tool"], decision["arguments"]
        result = call_tool(name, args)
        ledger.tool_calls += 1
        called.append(name)
        gathered[GATHERED_KEY_BY_TOOL[name]] = result
        transcript += [out_text, f"OBSERVATION[{name}]: {result}"]
    ledger.handoff("code-sample-worker", "orchestrator", report)
    return gathered, report


def run_squad(question_meta, flag=False, version_worker_failures=0, max_retries=1, disclose_failures=False):
    """Run one question through the squad.

    version_worker_failures: how many consecutive version-worker attempts return
    HTTP 500 for THIS question (0 = healthy; a big number = persistent outage).
    max_retries / disclose_failures are the ORCHESTRATOR's failure policy:
    the shipped default is the plain first implementation -- retry, and if the
    worker is still down carry on with whatever it has and say nothing
    (disclose_failures=False). disclose_failures=True is the fix measured in
    failure_case.md.
    """
    q = question_meta["question"]
    ledger = Ledger(question_meta["id"])
    api_version = question_meta["api_version"]

    # 1. orchestrator decomposes
    plan_out = (
        f"DELEGATE version-worker(check deprecation of {question_meta['target_name']} at {api_version}); "
        f"THEN DELEGATE code-sample-worker(parameters + usage at {api_version})"
    )
    ledger.llm("orchestrator", BUCKET_DECOMPOSE, f"{ORCH_SYSTEM}\nQ: {q}", plan_out)
    orch_transcript = [f"Q: {q}", plan_out]

    # 2. version worker, with the orchestrator's retry policy
    task = f"Check whether {question_meta['target_name']} is deprecated at SDK {api_version}."
    args = {"name": question_meta["target_name"], "api_version": api_version}
    attempts, dep, dep_report, failures_left = 0, None, None, version_worker_failures
    for attempts in range(1, max_retries + 2):
        status, body, report = _run_version_worker(ledger, task, args, injected_failure=failures_left > 0)
        failures_left -= 1
        orch_transcript.append(f"REPORT[version-worker attempt {attempts}]: {report}")
        if status == 200:
            dep, dep_report = body, report
            break
    version_check_ok = dep is not None

    # 3. orchestrator re-plans (resends question + everything so far) and delegates to the code worker
    endpoint = dep["lookup_key"] if (dep and dep["deprecated"]) else question_meta["target_name"]
    payload = f"Find the parameters and a usage example for {endpoint} at SDK {api_version}."
    if version_check_ok:
        payload += f" Version check says: {dep_report}"
    delegate_out = f"DELEGATE code-sample-worker({payload})"
    ledger.llm("orchestrator", BUCKET_REPLAN, "\n".join([ORCH_SYSTEM] + orch_transcript), delegate_out)
    orch_transcript.append(delegate_out)

    # 4. code-sample worker
    gathered, code_report = _run_code_worker(ledger, question_meta, payload, dep, flag)
    orch_transcript.append(f"REPORT[code-sample-worker]: {code_report}")

    # 5. orchestrator synthesises from the reports (resends all of them)
    answer = compose_answer(question_meta, gathered if version_check_ok else {k: v for k, v in gathered.items() if k != "deprecation"})
    if not version_check_ok and disclose_failures:
        answer = PARTIAL_DISCLOSURE + "\n\n" + answer
    ledger.llm("orchestrator", BUCKET_SYNTH, "\n".join([ORCH_SYSTEM] + orch_transcript), f"FINAL ANSWER: {answer}")

    return {
        "question_id": question_meta["id"],
        "answer": answer,
        "total_tokens": ledger.total_tokens,
        "total_cost_usd": round(ledger.total_cost, 6),
        "model_calls": ledger.model_calls,
        "tool_calls": ledger.tool_calls,
        "hops": ledger.hops,
        "version_attempts": attempts,
        "version_check_ok": version_check_ok,
        "disclosed": answer.startswith(PARTIAL_DISCLOSURE),
        "ledger": ledger,
    }
