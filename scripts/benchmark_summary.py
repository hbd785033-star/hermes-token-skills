#!/usr/bin/env python3
"""Compare baseline vs optimized benchmark runs for the token-efficiency skill.

Reads two JSON files (each a single run object or a list of run objects),
validates each run against the authoritative task registry, pairs runs by the
full task-spec/trial identity, and prints pair and task summaries. Standard
library only.

Guards against misleading claims:
- the baseline file must contain only mode="baseline" runs and the optimized
  file only mode="optimized" runs; anything else exits non-zero;
- duplicate full pair identities within one input file exit non-zero (never
  first-wins or last-wins);
- mismatched model, tokenizer, conditions, or pair order, unpaired identities,
  or unavailable/incompatible declared token measurements produce
  "Token reduction unavailable / incomparable" and never a percentage;
- an optimized run with success=false is marked "FAILED OPTIMIZATION" only
  after model, tokenizer, conditions, pair order, and baseline success are
  comparable;
- a baseline run with success=false is incomparable, because no efficiency
  claim can rest on a failed baseline;
- malformed JSON or missing required fields exits non-zero with an error.

input_tokens is the primary context-efficiency metric. Output tokens are
displayed for context only; no total-savings or cost figure is computed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = (
    "task_id",
    "task_revision",
    "task_prompt",
    "task_spec_sha256",
    "trial_id",
    "pair_order",
    "mode",
    "model",
    "tokenizer",
    "conditions",
    "success",
    "verification",
)
METRIC_FIELDS = ("input_tokens", "output_tokens", "tool_calls", "files_read")
VALID_MODES = ("baseline", "optimized")
VALID_PAIR_ORDERS = ("baseline-first", "optimized-first")
TRIAL_PAIR_ORDER = {
    "t1": "baseline-first",
    "t2": "optimized-first",
    "t3": "baseline-first",
}
VALID_TOKEN_SOURCES = ("provider_usage", "exact_tokenizer")
VALID_VERIFICATION_STATUSES = ("passed", "failed")
REQUIRED_CONDITION_FIELDS = (
    "fixture",
    "provider",
    "hermes_version",
    "tools",
    "temperature",
    "session_type",
)
UNCOMPARABLE = "Token reduction unavailable / incomparable"
FAILED = "FAILED OPTIMIZATION"
TASK_CONTRACT_FIELDS = (
    "id",
    "revision",
    "category",
    "goal",
    "prompt",
    "required_evidence",
    "verification",
)
PairIdentity = tuple[str, int, str, str]


class RunError(ValueError):
    """A run file is malformed or fails validation."""


def load_task_registry(path: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RunError(f"{path}: cannot read task registry: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RunError(f"{path}: malformed task registry JSON: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise RunError(f"{path}: task registry must contain a 'tasks' list")
    registry: dict[str, dict[str, Any]] = {}
    for index, task in enumerate(data["tasks"]):
        where = f"{path}.tasks[{index}]"
        if not isinstance(task, dict):
            raise RunError(f"{where}: task definition must be a JSON object")
        task_id = task.get("id")
        if not isinstance(task_id, str) or not task_id.strip():
            raise RunError(f"{where}: task 'id' must be a non-empty string")
        if task_id in registry:
            raise RunError(f"{where}: duplicate task id '{task_id}'")
        registry[task_id] = task
    return registry


def canonical_task_contract(task: dict[str, Any]) -> dict[str, Any]:
    missing = [field for field in TASK_CONTRACT_FIELDS if field not in task]
    if missing:
        raise RunError(f"task '{task.get('id', '<unknown>')}': missing contract field '{missing[0]}'")
    return {field: task[field] for field in TASK_CONTRACT_FIELDS}


def task_spec_sha256(task: dict[str, Any]) -> str:
    encoded = json.dumps(
        canonical_task_contract(task),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_task_identity(
    run: dict[str, Any], registry: dict[str, dict[str, Any]], where: str
) -> None:
    task_id = run["task_id"]
    task = registry.get(task_id)
    if task is None:
        raise RunError(f"{where}: unknown task_id '{task_id}'")

    try:
        contract = canonical_task_contract(task)
    except RunError as exc:
        raise RunError(f"{where}: task '{task_id}' is not runnable: {exc}") from exc
    revision = contract["revision"]
    if not isinstance(revision, int) or isinstance(revision, bool) or revision <= 0:
        raise RunError(f"{where}: task '{task_id}' is not runnable: revision must be a positive integer")
    for field in ("category", "goal", "prompt"):
        value = contract[field]
        if not isinstance(value, str) or not value.strip():
            raise RunError(f"{where}: task '{task_id}' is not runnable: {field} must be non-empty")
    for field in ("required_evidence", "verification"):
        value = contract[field]
        if (
            not isinstance(value, list)
            or not value
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise RunError(
                f"{where}: task '{task_id}' is not runnable: {field} must be a non-empty string list"
            )

    if run["task_revision"] != revision:
        raise RunError(
            f"{where}: task_revision {run['task_revision']!r} does not match registry revision {revision}"
        )
    if run["task_prompt"] != contract["prompt"]:
        raise RunError(f"{where}: task_prompt does not exactly match registry prompt")
    expected_digest = task_spec_sha256(task)
    if run["task_spec_sha256"] != expected_digest:
        raise RunError(f"{where}: task_spec_sha256 does not match registry task contract")


def load_runs(
    path: Path, expected_mode: str, registry: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
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
    seen: set[PairIdentity] = set()
    for index, run in enumerate(data):
        where = f"{path}[{index}]"
        validate_run(run, where)
        validate_task_identity(run, registry, where)
        if run["mode"] != expected_mode:
            raise RunError(
                f"{where}: expected mode '{expected_mode}' in this file, "
                f"got '{run['mode']}'"
            )
        identity = (
            run["task_id"],
            run["task_revision"],
            run["task_spec_sha256"],
            run["trial_id"],
        )
        if identity in seen:
            raise RunError(
                f"{where}: duplicate pair {identity!r} in {path}; duplicate task_id "
                f"'{run['task_id']}' for the same trial_id"
            )
        seen.add(identity)
    return data


def validate_run(run: Any, where: str) -> None:
    if not isinstance(run, dict):
        raise RunError(f"{where}: each run must be a JSON object")
    for field in REQUIRED_FIELDS:
        if field not in run or run[field] is None:
            raise RunError(f"{where}: missing required field '{field}'")
    for field in ("task_id", "task_spec_sha256", "trial_id", "model", "tokenizer"):
        if not isinstance(run[field], str) or not run[field].strip():
            raise RunError(f"{where}: '{field}' must be a non-empty string")
    if not isinstance(run["task_prompt"], str):
        raise RunError(f"{where}: 'task_prompt' must be a string")
    if (
        not isinstance(run["task_revision"], int)
        or isinstance(run["task_revision"], bool)
        or run["task_revision"] <= 0
    ):
        raise RunError(f"{where}: 'task_revision' must be a positive integer")
    if run["mode"] not in VALID_MODES:
        raise RunError(f"{where}: 'mode' must be one of {VALID_MODES}")
    if run["pair_order"] not in VALID_PAIR_ORDERS:
        raise RunError(f"{where}: 'pair_order' must be one of {VALID_PAIR_ORDERS}")
    expected_pair_order = TRIAL_PAIR_ORDER.get(run["trial_id"])
    if expected_pair_order is not None and run["pair_order"] != expected_pair_order:
        raise RunError(
            f"{where}: trial_id '{run['trial_id']}' requires pair_order "
            f"'{expected_pair_order}'"
        )
    if not isinstance(run["conditions"], dict) or not run["conditions"]:
        raise RunError(f"{where}: 'conditions' must be a non-empty JSON object")
    for field in REQUIRED_CONDITION_FIELDS:
        if field not in run["conditions"] or run["conditions"][field] is None:
            raise RunError(f"{where}: conditions missing required field '{field}'")
    for field in ("fixture", "provider", "hermes_version", "session_type"):
        value = run["conditions"][field]
        if not isinstance(value, str) or not value.strip():
            raise RunError(f"{where}: 'conditions.{field}' must be a non-empty string")
    if run["conditions"]["session_type"] != "fresh-isolated":
        raise RunError(f"{where}: conditions.session_type must be 'fresh-isolated'")
    tools = run["conditions"]["tools"]
    if (
        not isinstance(tools, list)
        or not tools
        or any(not isinstance(tool, str) or not tool.strip() for tool in tools)
    ):
        raise RunError(
            f"{where}: 'conditions.tools' must be a non-empty list of non-empty strings"
        )
    temperature = run["conditions"]["temperature"]
    if (
        not isinstance(temperature, (int, float))
        or isinstance(temperature, bool)
        or not math.isfinite(temperature)
    ):
        raise RunError(f"{where}: 'conditions.temperature' must be a finite number")
    if not isinstance(run["success"], bool):
        raise RunError(f"{where}: 'success' must be a boolean")
    verification = run["verification"]
    if not isinstance(verification, dict):
        raise RunError(f"{where}: 'verification' must be a JSON object")
    if verification.get("status") not in VALID_VERIFICATION_STATUSES:
        raise RunError(
            f"{where}: 'verification.status' must be one of {VALID_VERIFICATION_STATUSES}"
        )
    evidence = verification.get("evidence")
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(item, str) or not item.strip() for item in evidence)
    ):
        raise RunError(
            f"{where}: 'verification.evidence' must be a non-empty list of non-empty strings"
        )
    expected_status = "passed" if run["success"] else "failed"
    if verification["status"] != expected_status:
        success = str(run["success"]).lower()
        raise RunError(
            f"{where}: success={success} requires verification.status='{expected_status}'"
        )
    for field in METRIC_FIELDS:
        value = run.get(field)
        if value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0):
            raise RunError(f"{where}: '{field}' must be a non-negative integer or null")
    token_metrics_present = any(run.get(field) is not None for field in ("input_tokens", "output_tokens"))
    token_source = run.get("token_source")
    if token_metrics_present and token_source is None:
        raise RunError(f"{where}: token_source is required when token metrics are present")
    if token_source is not None and token_source not in VALID_TOKEN_SOURCES:
        raise RunError(f"{where}: 'token_source' must be one of {VALID_TOKEN_SOURCES}")


def metric(value: Any) -> str:
    return "-" if value is None else str(value)


def pair_outcome(baseline: dict[str, Any], optimized: dict[str, Any]) -> tuple[str, str]:
    if baseline["model"] != optimized["model"]:
        return "incomparable", "model differs"
    if baseline["tokenizer"] != optimized["tokenizer"]:
        return "incomparable", "tokenizer differs"
    if baseline["conditions"] != optimized["conditions"]:
        return "incomparable", "conditions differ"
    if baseline["pair_order"] != optimized["pair_order"]:
        return "incomparable", "pair_order differs"
    if not baseline["success"]:
        return "incomparable", "baseline task failed"
    if not optimized["success"]:
        return "optimized_failure", "token reduction without correctness is not success"
    if baseline.get("input_tokens") is None or optimized.get("input_tokens") is None:
        return "incomparable", "missing token count"
    if baseline.get("token_source") != optimized.get("token_source"):
        return "incomparable", "token_source differs"
    return "comparable_success", ""


def summarize_pair(baseline: dict[str, Any], optimized: dict[str, Any]) -> tuple[str, str]:
    task = baseline["task_id"]
    trial = baseline["trial_id"]
    columns = (
        f"Task: {task}\n"
        f"  Trial: {trial}\n"
        f"  Pair order (base/opt): {baseline['pair_order']} / {optimized['pair_order']}\n"
        f"  Baseline input tokens:  {metric(baseline.get('input_tokens'))}\n"
        f"  Optimized input tokens: {metric(optimized.get('input_tokens'))}\n"
        f"  Output tokens (base/opt): {metric(baseline.get('output_tokens'))} / {metric(optimized.get('output_tokens'))}\n"
        f"  Tool calls (base/opt):  {metric(baseline.get('tool_calls'))} / {metric(optimized.get('tool_calls'))}\n"
        f"  Files read (base/opt):  {metric(baseline.get('files_read'))} / {metric(optimized.get('files_read'))}\n"
        f"  Success (base/opt):     {baseline['success']} / {optimized['success']}\n"
        f"  Verification (base/opt): {baseline['verification']['status']} / "
        f"{optimized['verification']['status']}"
    )
    outcome, reason = pair_outcome(baseline, optimized)
    if outcome == "incomparable":
        verdict = f"  Delta: {UNCOMPARABLE} ({reason})"
    elif outcome == "optimized_failure":
        verdict = f"  Delta: {FAILED} ({reason})"
    else:
        base_tokens = baseline["input_tokens"]
        opt_tokens = optimized["input_tokens"]
        delta = opt_tokens - base_tokens
        if base_tokens > 0:
            percent = delta / base_tokens * 100
            verdict = f"  Delta: {delta:+d} input tokens ({percent:+.1f}%)"
        else:
            verdict = f"  Delta: {delta:+d} input tokens (percentage unavailable: baseline is 0)"
    return columns + "\n" + verdict, outcome


def format_number(value: int | float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.1f}"


def summarize_task(
    task_id: str,
    identities: list[PairIdentity],
    baselines: dict[PairIdentity, dict[str, Any]],
    optimized: dict[PairIdentity, dict[str, Any]],
) -> str:
    comparable: list[tuple[dict[str, Any], dict[str, Any]]] = []
    incomparable = 0
    optimized_failures = 0
    for identity in identities:
        baseline = baselines.get(identity)
        optimization = optimized.get(identity)
        if baseline is None or optimization is None:
            incomparable += 1
            continue
        outcome, _ = pair_outcome(baseline, optimization)
        if outcome == "comparable_success":
            comparable.append((baseline, optimization))
        elif outcome == "optimized_failure":
            optimized_failures += 1
        else:
            incomparable += 1

    lines = [
        f"Task aggregate: {task_id}",
        f"  Total trials: {len(identities)}",
        f"  Comparable successful pairs: {len(comparable)}",
        f"  Incomparable pairs: {incomparable}",
        f"  Optimized failures: {optimized_failures}",
    ]
    if len(comparable) < 2:
        lines.append("  Aggregate: INSUFFICIENT REPEATED TRIALS")
        return "\n".join(lines)

    baseline_tokens = [pair[0]["input_tokens"] for pair in comparable]
    optimized_tokens = [pair[1]["input_tokens"] for pair in comparable]
    deltas = [optimized - baseline for baseline, optimized in zip(baseline_tokens, optimized_tokens)]
    percentages = [delta / baseline * 100 for baseline, delta in zip(baseline_tokens, deltas) if baseline > 0]
    lines.extend(
        [
            f"  Median baseline input tokens: {format_number(statistics.median(baseline_tokens))}",
            f"  Median optimized input tokens: {format_number(statistics.median(optimized_tokens))}",
            f"  Median absolute delta: {format_number(statistics.median(deltas))}",
        ]
    )
    if len(percentages) != len(comparable):
        lines.append("  Median pairwise percentage delta: unavailable (baseline is 0)")
    else:
        lines.append(
            f"  Median pairwise percentage delta: {statistics.median(percentages):+.1f}%"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tasks",
        type=Path,
        default=Path(__file__).parents[1] / "benchmarks" / "tasks.json",
        help="authoritative task registry JSON",
    )
    parser.add_argument("baseline", type=Path, help="baseline run JSON (without the skill)")
    parser.add_argument("optimized", type=Path, help="optimized run JSON (with the skill)")
    args = parser.parse_args()

    try:
        registry = load_task_registry(args.tasks)
        baselines = {
            (
                run["task_id"],
                run["task_revision"],
                run["task_spec_sha256"],
                run["trial_id"],
            ): run
            for run in load_runs(args.baseline, "baseline", registry)
        }
        optimized = {
            (
                run["task_id"],
                run["task_revision"],
                run["task_spec_sha256"],
                run["trial_id"],
            ): run
            for run in load_runs(args.optimized, "optimized", registry)
        }
    except RunError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    blocks: list[str] = []
    identities = sorted(set(baselines) | set(optimized))
    for identity in identities:
        task_id, _, _, trial_id = identity
        base = baselines.get(identity)
        opt = optimized.get(identity)
        if base is None or opt is None:
            missing = "baseline" if base is None else "optimized"
            blocks.append(
                f"Task: {task_id}\n  Trial: {trial_id}\n"
                f"  Delta: {UNCOMPARABLE} (missing {missing} run)"
            )
            continue
        pair_summary, _ = summarize_pair(base, opt)
        blocks.append(pair_summary)

    for task_id in sorted({identity[0] for identity in identities}):
        task_identities = [identity for identity in identities if identity[0] == task_id]
        blocks.append(summarize_task(task_id, task_identities, baselines, optimized))

    print("\n\n".join(blocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
