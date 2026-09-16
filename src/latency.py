"""Measures search latency so a retrieval change's speed cost can be
reported honestly alongside its accuracy gain."""

import statistics
import time


def time_search_calls(retriever, questions, top_k=3):
    """Return one wall-clock duration (seconds) per question's search call."""

    durations = []
    for q in questions:
        start = time.perf_counter()
        retriever.search(q["question"], top_k=top_k)
        durations.append(time.perf_counter() - start)
    return durations


def p50_latency_ms(durations):
    return statistics.median(durations) * 1000
