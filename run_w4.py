"""Entry point: python run_w4.py

Runs the Week 4 experiment (baseline hit-rate@3 -> diagnose -> BM25+RRF
fusion -> re-measure -> compare -> write output/w4/results.md) and prints a
short summary to the console.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from w4_pipeline import run  # noqa: E402


def main():
    results = run()

    baseline_eval = results["baseline_eval"]
    fused_eval = results["fused_eval"]
    tally = results["tally"]

    fixed_r = sum(
        1 for r in results["comparison_rows"]
        if r["baseline_label"] == "R" and r["verdict"] == "FIXED"
    )

    print("Week 4 Task Set E -- practice run complete")
    print(f"  Baseline hit-rate@3: {baseline_eval['score']}/{baseline_eval['total']}")
    print(f"  Fused hit-rate@3:    {fused_eval['score']}/{fused_eval['total']}")
    print(f"  Tally: HIT={tally['HIT']} R={tally['R']} G={tally['G']} NOT_IN_CORPUS={tally['NOT_IN_CORPUS']}")
    print(f"  R-failures fixed: {fixed_r}/{tally['R']}")
    print(f"  p50 latency: {results['baseline_p50_ms']:.3f} ms -> {results['fused_p50_ms']:.3f} ms")
    print(f"  results.md written to: {results['results_path']}")


if __name__ == "__main__":
    main()
