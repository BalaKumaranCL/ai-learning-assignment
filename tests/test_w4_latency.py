import statistics

from latency import time_search_calls, p50_latency_ms


class _StubRetriever:
    """Minimal retriever stub -- just needs a .search(query, top_k) method,
    since latency.py only ever calls that."""

    def search(self, query, top_k=3):
        return []


def test_time_search_calls_returns_one_non_negative_duration_per_question():
    questions = [{"question": f"question {i}"} for i in range(12)]
    durations = time_search_calls(_StubRetriever(), questions, top_k=3)

    assert len(durations) == 12
    assert all(d >= 0 for d in durations)


def test_p50_latency_ms_matches_independent_median_computation():
    durations = [0.001, 0.002, 0.003, 0.010, 0.020]
    expected = statistics.median(durations) * 1000

    assert p50_latency_ms(durations) == expected
