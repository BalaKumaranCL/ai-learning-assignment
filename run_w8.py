"""Entry point: python run_w8.py

Runs the Week 8 Task Set E exercise end to end:

1. trajectory_eval.py over the 10 w7_questions.json cases, BEFORE the
   mitigation -- the 4 trajectory numbers, the outcome-vs-trajectory gap,
   and the named right-answer-wrong-path trace.
2. failure_zoo.py over the same 10 plus 4 synthetic stress cases -- the
   per-mode counts, the top failure mode, and (run again with the
   mitigation applied) the before -> after regression table.
3. trajectory_eval.py again, AFTER the mitigation -- confirms the gap
   closes and reports the price paid.
4. prompt_injection_demo.py -- the bonus attack/defense.

Writes output/w8/*.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from trajectory_eval import run_trajectory_eval, write_outputs  # noqa: E402
from failure_zoo import regression_table, run_zoo, top_failure_mode  # noqa: E402
import prompt_injection_demo as inj  # noqa: E402
from guardrails import guard_output  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "w8")


def _print_summary(label, summary):
    print(f"\n-- {label} --")
    print(f"  outcome_pass_rate         {summary['outcome_pass_rate']:.2f}")
    print(f"  trajectory_pass_rate      {summary['trajectory_pass_rate']:.2f}")
    print(f"  outcome_vs_trajectory_gap {summary['outcome_vs_trajectory_gap']:.2f}")
    print(f"  tool_choice_accuracy      {summary['tool_choice_accuracy']:.4f}")
    print(f"  argument_validity_rate    {summary['argument_validity_rate']:.4f}")
    print(f"  step_efficiency_mean      {summary['step_efficiency_mean']:.4f}")
    print(f"  cost_p50_usd              {summary['cost_p50_usd']:.6f}")
    print(f"  cost_max_usd              {summary['cost_max_usd']:.6f}")


def _write_zoo_counts_csv(counts, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["mode", "count"])
        for mode, n in counts.items():
            writer.writerow([mode, n])


def _write_regression_csv(table, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["mode", "before", "after", "direction"])
        for row in table:
            writer.writerow([row["mode"], row["before"], row["after"], row["direction"]])


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Week 8 Task Set E -- trajectory eval, failure zoo, single mitigation, regression check")

    before = run_trajectory_eval(require_spec_after_deprecation=False)
    _print_summary("BEFORE mitigation (Week 7's shipped agent behavior)", before["summary"])
    print("\n  right-answer-wrong-path cases:")
    for r in before["right_answer_wrong_path"]:
        print(f"    {r['id']}: called {r['observed_sequence']}, never called {r['missing_tools']}")
    before_paths = write_outputs(before, "before")

    zoo_before = run_zoo(require_spec_after_deprecation=False)
    top_mode = top_failure_mode(zoo_before["counts"])
    print(f"\n-- zoo, before mitigation -- top failure mode: {top_mode} ({zoo_before['counts'][top_mode]}) --")
    for mode, n in zoo_before["counts"].items():
        print(f"  {mode:<22} {n}")

    after = run_trajectory_eval(require_spec_after_deprecation=True)
    _print_summary("AFTER mitigation (require_spec_after_deprecation=True)", after["summary"])
    after_paths = write_outputs(after, "after")

    zoo_after = run_zoo(require_spec_after_deprecation=True)
    table = regression_table(zoo_before["counts"], zoo_after["counts"])
    print("\n-- regression table --")
    for row in table:
        print(f"  {row['mode']:<22} before={row['before']:<3} after={row['after']:<3} {row['direction']}")
    worsened = [row for row in table if row["direction"] == "WORSE"]
    print(f"\n  modes that got worse: {[r['mode'] for r in worsened] or 'none'}")

    before_cost = sum(r["total_cost_usd"] for r in before["rows"])
    after_cost = sum(r["total_cost_usd"] for r in after["rows"])
    before_tokens = sum(r["total_tokens"] for r in before["rows"])
    after_tokens = sum(r["total_tokens"] for r in after["rows"])
    price_lines = [
        f"top failure mode: {top_mode}",
        f"count before -> after: {zoo_before['counts'][top_mode]} -> {zoo_after['counts'][top_mode]}",
        f"total tokens (10 q) before -> after: {before_tokens} -> {after_tokens} (+{after_tokens - before_tokens})",
        f"total cost (10 q) before -> after: ${before_cost:.6f} -> ${after_cost:.6f} (+${after_cost - before_cost:.6f})",
        f"cost per question, mean, before -> after: ${before_cost/10:.6f} -> ${after_cost/10:.6f}",
        f"outcome_vs_trajectory_gap before -> after: {before['summary']['outcome_vs_trajectory_gap']:.2f} -> {after['summary']['outcome_vs_trajectory_gap']:.2f}",
    ]
    zoo_before_csv = os.path.join(OUTPUT_DIR, "failure_zoo_before.csv")
    zoo_after_csv = os.path.join(OUTPUT_DIR, "failure_zoo_after.csv")
    regression_csv = os.path.join(OUTPUT_DIR, "failure_zoo_regression.csv")
    mitigation_txt = os.path.join(OUTPUT_DIR, "mitigation_summary.txt")
    _write_zoo_counts_csv(zoo_before["counts"], zoo_before_csv)
    _write_zoo_counts_csv(zoo_after["counts"], zoo_after_csv)
    _write_regression_csv(table, regression_csv)
    with open(mitigation_txt, "w", encoding="utf-8") as fh:
        fh.write("\n".join(price_lines) + "\n")

    print("\n-- bonus: indirect prompt injection --")
    undefended = inj.attack_undefended()
    sanitized, hits = inj.attack_with_sanitizer()
    both, _, blocked = inj.attack_with_both_layers()
    obf_sanitized, obf_hits = inj.attack_with_sanitizer(inj.OBFUSCATED_DOCS_RESULT)
    obf_guarded, obf_blocked = guard_output(obf_sanitized)
    clean_overhead = inj.measure_clean_traffic_overhead()
    attack_cost = inj.measure_attack_case_token_cost()

    injection_lines = [
        "=== undefended ===",
        undefended,
        f"payload present: {inj.INJECTION_PAYLOAD in undefended}",
        "",
        "=== sanitizer only ===",
        sanitized,
        f"payload present: {inj.INJECTION_PAYLOAD in sanitized} | patterns matched: {hits}",
        "",
        "=== sanitizer + output guardrail ===",
        both,
        f"payload present: {inj.INJECTION_PAYLOAD in both} | output guardrail also fired: {blocked}",
        "",
        "=== obfuscated retry (residual risk -- still gets through) ===",
        obf_guarded,
        f"obfuscated payload still present: {'stops checking who' in obf_guarded}",
        "",
        "=== measured cost ===",
        f"clean-traffic scan overhead: {clean_overhead['passages_scanned']} real docs passages "
        f"(10 w7 questions), {clean_overhead['elapsed_s']*1000:.2f} ms total, "
        f"{clean_overhead['elapsed_s']*1000/clean_overhead['passages_scanned']:.3f} ms/passage",
        f"attack-case token delta (undefended -> defended): "
        f"{attack_cost['undefended_tokens']} -> {attack_cost['defended_tokens']} tokens "
        f"({attack_cost['delta_tokens']:+d})",
    ]
    injection_path = os.path.join(OUTPUT_DIR, "prompt_injection_report.txt")
    with open(injection_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(injection_lines) + "\n")

    print(f"\nwrote: {before_paths}")
    print(f"wrote: {after_paths}")
    print(f"wrote: {zoo_before_csv}")
    print(f"wrote: {zoo_after_csv}")
    print(f"wrote: {regression_csv}")
    print(f"wrote: {mitigation_txt}")
    print(f"wrote: {injection_path}")


if __name__ == "__main__":
    main()
