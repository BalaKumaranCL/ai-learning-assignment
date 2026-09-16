"""Trace schema, logging, and replay for the Week 5 error-analysis exercise.

Realistic wrinkle baked in on purpose: the docs assistant's logging was not
built with error analysis in mind. For its first several days in
production, a trace only recorded {trace_id, timestamp, question,
sdk_version_filter, answered, raw_output} -- no retrieved chunk_ids/scores,
no retriever/generator version, no latency. Someone noticed the gap partway
through the week and added the rest. That means most of the trace log
genuinely cannot tell you *why* an answer was wrong -- only *what* the
answer was -- which is exactly the kind of realistic limitation this
exercise is supposed to surface, not paper over.
"""

import json

RICH_SCHEMA_CUTOVER_DAY = 5  # traces from day 5 onward (of a 7-day window) get full fields


def trace_to_dict(trace):
    """Render one trace as the dict that actually gets persisted to the log
    -- older traces (day < RICH_SCHEMA_CUTOVER_DAY) drop the fields that
    weren't being recorded yet, exactly as a real incomplete log would."""

    base = {
        "trace_id": trace["trace_id"],
        "timestamp": trace["timestamp"],
        "day": trace["day"],
        "question": trace["question"],
        "sdk_version_filter": trace["sdk_version_filter"],
        "answered": trace["answered"],
        "raw_output": trace["raw_output"],
    }
    if trace["day"] >= RICH_SCHEMA_CUTOVER_DAY:
        base["retriever_version"] = trace["retriever_version"]
        base["generator_version"] = trace["generator_version"]
        base["min_score_threshold"] = trace["min_score_threshold"]
        base["retrieved"] = trace["retrieved"]
        base["cited_chunk_id"] = trace["cited_chunk_id"]
        base["latency_ms"] = trace["latency_ms"]
    return base


def write_traces_jsonl(path, traces):
    with open(path, "w", encoding="utf-8") as fh:
        for trace in traces:
            fh.write(json.dumps(trace_to_dict(trace)) + "\n")


def load_traces_jsonl(path):
    traces = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                traces.append(json.loads(line))
    return traces


def replay_trace(trace, retriever, retriever_version, generator_version, min_score_threshold):
    """Replay a trace from the trace's OWN recorded fields alone: its
    question, plus its sdk_version_filter if that field was logged.

    Returns the fresh output plus a note of anything about the ORIGINAL
    run that could not be reconstructed (because the field was never
    logged in the first place -- no amount of replaying recovers it).
    """

    from docs_assistant import answer_question

    sdk_version = trace.get("sdk_version_filter")
    result = answer_question(trace["question"], retriever, sdk_version=sdk_version)

    missing_fields = []
    for field_name in ("retriever_version", "generator_version", "min_score_threshold", "retrieved", "cited_chunk_id", "latency_ms"):
        if field_name not in trace:
            missing_fields.append(field_name)

    return {
        "trace_id": trace["trace_id"],
        "original_raw_output": trace["raw_output"],
        "original_answered": trace["answered"],
        "replayed_raw_output": result["answer"],
        "replayed_answered": result["answered"],
        "replayed_chunk_id": result["chunk_id"],
        "replayed_score": result["score"],
        "replay_retriever_version": retriever_version,
        "replay_generator_version": generator_version,
        "replay_min_score_threshold": min_score_threshold,
        "outputs_match": trace["raw_output"].strip() == result["answer"].strip(),
        "missing_fields_in_original_trace": missing_fields,
        "sdk_version_filter_used_for_replay": sdk_version,
        "sdk_version_filter_was_logged": "sdk_version_filter" in trace and trace["sdk_version_filter"] is not None,
    }
