#!/usr/bin/env python3
"""Compare baseline vs optimized benchmark runs for the token-efficiency skill.

Reads two JSON files (each a single run object or a list of run objects),
pairs runs by task_id, and prints a per-task summary. Standard library only.

Guards against misleading claims:
- the baseline file must contain only mode="baseline" runs and the optimized
  file only mode="optimized" runs; anything else exits non-zero;
- duplicate task_id values within one input file exit non-zero (never
  first-wins or last-wins);
- mismatched model, tokenizer, or conditions, unpaired task_id, or missing
  token counts produce "Token reduction unavailable / incomparable" and never
  a token-saving percentage;
- an optimized run with success=false is marked "FAILED OPTIMIZATION"
  regardless of the token delta;
- a baseline run with success=false is incomparable, because no efficiency
  claim can rest on a failed baseline;
- malformed JSON or missing required fields exits non-zero with an error.

input_tokens is the primary context-efficiency metric. Output tokens are
displayed for context only; no total-savings or cost figure is computed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "task_id",
    "mode",
    "model",
    "tokenizer",
    "conditions",
    "success",
    "verification",
)
METRIC_FIELDS = ("input_tokens", "output_tokens", "tool_calls", "files_read")
VALID_MODES = ("baseline", "optimized")
UNCOMPARABLE = "Token reduction unavailable / incomparable"
FAILED = "FAILED OPTIMIZATION"


class RunError(ValueError):
    """A run file is malformed or fails validation."""


def load_runs(path: Path, expected_mode: str) -> list[dict[str, Any]]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RunError(f"{path}: cannot read file: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RunError(f"{path}: malformed JSON: {exc}") from exc
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list) or not data:
        raise RunError(f"{path}: expected a run object or a non-empty list of runs")
    seen: set[str] = set()
    for index, run in enumerate(data):
        where = f"{path}[{index}]"
        validate_run(run, where)
        if run["mode"] != expected_mode:
            raise RunError(
                f"{where}: expected mode '{expected_mode}' in this file, "
                f"got '{run['mode']}'"
            )
        task_id = run["task_id"]
        if task_id in seen:
            raise RunError(f"{where}: duplicate task_id '{task_id}' in {path}")
        seen.add(task_id)
    return data


def validate_run(run: Any, where: str) -> None:
    if not isinstance(run, dict):
        raise RunError(f"{where}: each run must be a JSON object")
    for field in REQUIRED_FIELDS:
        if field not in run or run[field] is None:
            raise RunError(f"{where}: missing required field '{field}'")
    if not isinstance(run["task_id"], str) or not run["task_id"]:
        raise RunError(f"{where}: 'task_id' must be a non-empty string")
    if run["mode"] not in VALID_MODES:
        raise RunError(f"{where}: 'mode' must be one of {VALID_MODES}")
    for field in ("model", "tokenizer", "verification"):
        if not isinstance(run[field], str) or not run[field]:
            raise RunError(f"{where}: '{field}' must be a non-empty string")
    if not isinstance(run["conditions"], dict) or not run["conditions"]:
        raise RunError(f"{where}: 'conditions' must be a non-empty JSON object")
    if not isinstance(run["success"], bool):
        raise RunError(f"{where}: 'success' must be a boolean")
    for field in METRIC_FIELDS:
        value = run.get(field)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise RunError(f"{where}: '{field}' must be a non-negative integer or null")


def metric(value: Any) -> str:
    return "-" if value is None else str(value)


def summarize_pair(baseline: dict[str, Any], optimized: dict[str, Any]) -> str:
    task = baseline["task_id"]
    columns = (
        f"Task: {task}\n"
        f"  Baseline input tokens:  {metric(baseline.get('input_tokens'))}\n"
        f"  Optimized input tokens: {metric(optimized.get('input_tokens'))}\n"
        f"  Output tokens (base/opt): {metric(baseline.get('output_tokens'))} / {metric(optimized.get('output_tokens'))}\n"
        f"  Tool calls (base/opt):  {metric(baseline.get('tool_calls'))} / {metric(optimized.get('tool_calls'))}\n"
        f"  Files read (base/opt):  {metric(baseline.get('files_read'))} / {metric(optimized.get('files_read'))}\n"
        f"  Success (base/opt):     {baseline['success']} / {optimized['success']}\n"
        f"  Verification (base/opt): {baseline['verification']} / {optimized['verification']}"
    )
    if not optimized["success"]:
        verdict = f"  Delta: {FAILED} (token reduction without correctness is not success)"
    elif not baseline["success"]:
        verdict = f"  Delta: {UNCOMPARABLE} (baseline task failed)"
    elif baseline["model"] != optimized["model"]:
        verdict = f"  Delta: {UNCOMPARABLE} (model differs)"
    elif baseline["tokenizer"] != optimized["tokenizer"]:
        verdict = f"  Delta: {UNCOMPARABLE} (tokenizer differs)"
    elif baseline["conditions"] != optimized["conditions"]:
        verdict = f"  Delta: {UNCOMPARABLE} (conditions differ)"
    elif baseline.get("input_tokens") is None or optimized.get("input_tokens") is None:
        verdict = f"  Delta: {UNCOMPARABLE} (missing token count)"
    else:
        base_tokens = baseline["input_tokens"]
        opt_tokens = optimized["input_tokens"]
        delta = opt_tokens - base_tokens
        if base_tokens > 0:
            percent = delta / base_tokens * 100
            verdict = f"  Delta: {delta:+d} input tokens ({percent:+.1f}%)"
        else:
            verdict = f"  Delta: {delta:+d} input tokens (percentage unavailable: baseline is 0)"
    return columns + "\n" + verdict


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path, help="baseline run JSON (without the skill)")
    parser.add_argument("optimized", type=Path, help="optimized run JSON (with the skill)")
    args = parser.parse_args()

    try:
        baselines = {run["task_id"]: run for run in load_runs(args.baseline, "baseline")}
        optimized = {run["task_id"]: run for run in load_runs(args.optimized, "optimized")}
    except RunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    blocks: list[str] = []
    for task_id in sorted(set(baselines) | set(optimized)):
        base = baselines.get(task_id)
        opt = optimized.get(task_id)
        if base is None or opt is None:
            missing = "baseline" if base is None else "optimized"
            blocks.append(f"Task: {task_id}\n  Delta: {UNCOMPARABLE} (missing {missing} run)")
            continue
        blocks.append(summarize_pair(base, opt))

    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
