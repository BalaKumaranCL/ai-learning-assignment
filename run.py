"""Entry point: python run.py

Runs the full pipeline (load -> chunk -> validate -> retrieve -> evaluate ->
filter demo -> generate -> write output/results.md) and prints a short
summary to the console.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from pipeline import run  # noqa: E402


def main():
    results = run()

    eval_current = results["eval_current"]
    eval_structure = results["eval_structure"]

    print("Week 3 Task Set E -- practice run complete")
    print(f"  Pages ingested: {len(results['pages'])} -> {', '.join(results['pages'])}")
    print(f"  Current chunker:         {eval_current['score']}/{eval_current['total']}")
    print(f"  Structure-aware chunker: {eval_structure['score']}/{eval_structure['total']}")
    print(f"  Filter demo top-1 changed: {results['filter_demo']['top1_changed']}")
    print(f"  Answered (cited): {sum(1 for a in results['answered'] if a['answered'])}/{len(results['answered'])}")
    print(f"  Refused (correctly): {sum(1 for r in results['refused'] if not r['answered'])}/{len(results['refused'])}")
    print(f"  Bonus demonstrated: {results['bonus']['demonstrated']}")
    print(f"  results.md written to: {results['results_path']}")


if __name__ == "__main__":
    main()
