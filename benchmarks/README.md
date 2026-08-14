# Benchmarks

A minimal harness for judging whether the `token-efficiency` skill actually helps. This is not an eval platform: it defines tasks, records real runs, and compares a baseline against an optimized run with strict guards against misleading claims.

## Principles

- Lower tokens alone is not success. Success = less context + same or better task correctness + preserved evidence.
- Never estimate or fabricate token counts. If a run has no tokenizer-reported count, the token fields stay absent and no token-saving percentage is produced.
- No fabricated results. This directory ships task definitions only; run files are produced by real agent runs.

## Tasks

`tasks.json` defines the task set across six categories:

| Category | What it exercises |
|---|---|
| `known-symbol` | Targeted search + narrow read for a known symbol/file |
| `cross-file` | Tracing across async/adapter/registry boundaries |
| `large-repo` | Mapping and filtered retrieval in an unfamiliar repository |
| `tool-output` | Local reduction of large repetitive tool output |
| `structured-data` | Compact representation of uniform records |
| `handoff` | Structured state block for session/agent handoff |

Each task has an `id`, `category`, `goal`, `required_evidence`, and `verification`. Fill in `required_evidence` and `verification` when pinning a task to a concrete repository or dataset.

## Run format

Each real run is one JSON file. Baseline runs execute **without** the token-efficiency skill; optimized runs execute **with** it.

```json
{
  "task_id": "known-symbol-01",
  "mode": "baseline",
  "model": "model-name",
  "tokenizer": "tokenizer-or-provider",
  "conditions": {
    "fixture": "hermes-agent@<commit-sha>",
    "tools": ["search_files", "read_file"],
    "temperature": 0
  },
  "input_tokens": 0,
  "output_tokens": 0,
  "tool_calls": 0,
  "files_read": 0,
  "success": true,
  "verification": "passed"
}
```

Fields:

- Required: `task_id`, `mode` (`baseline` or `optimized`), `model`, `tokenizer`, `conditions`, `success`, `verification`.
- `conditions` is a non-empty JSON object describing the run environment. For repository-based tasks, `fixture` should pin the repository revision (for example `hermes-agent@<commit-sha>`); for non-repository tasks use a stable fixture id (for example `structured-data-v1`). Baseline and optimized runs of a task are comparable only when their `conditions` objects are identical.
- Optional (omit when unmeasured): `input_tokens`, `output_tokens`, `tool_calls`, `files_read`. Token fields may be missing; missing values must never be estimated.
- `input_tokens` is the primary context-efficiency metric. Output tokens are displayed for context only; the tool computes no total-savings or cost figure.

The `examples/` directory contains format-only examples with null metrics. They are schema illustrations, not measured results.

## Comparing runs

```bash
python scripts/benchmark_summary.py baseline.json optimized.json
```

Both arguments accept a single run object or a JSON list of runs. Runs are paired by `task_id`. The summary prints, per task: baseline input tokens, optimized input tokens, delta, tool calls, files read, success, and verification.

Guards:

- The baseline file must contain only `"mode": "baseline"` runs and the optimized file only `"mode": "optimized"` runs. A wrong mode, including swapped files, is an error exit — never a comparison.
- Duplicate `task_id` values within one input file are an error exit. Runs are never silently overwritten (no first-wins or last-wins).
- Mismatched `model`, mismatched `tokenizer`, mismatched `conditions`, unpaired `task_id`, or missing token counts → `Token reduction unavailable / incomparable`. No percentage is printed.
- Baseline run with `success=false` → `Token reduction unavailable / incomparable` (baseline task failed), even when token counts exist. No efficiency claim can rest on a failed baseline.
- Comparable optimized run with `success=false` → `FAILED OPTIMIZATION`, regardless of the token delta; mismatched model, tokenizer, conditions, or a failed baseline remain incomparable first.
- Malformed JSON or missing required fields → error exit, no summary.
