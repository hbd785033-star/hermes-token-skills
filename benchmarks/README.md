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

`tasks.json` is the authoritative registry. A runnable task requires `id`, a positive integer `revision`, `category`, `goal`, a non-empty exact `prompt`, non-empty `required_evidence`, and non-empty `verification` criteria. The checked-in tasks remain Phase A scaffolds with empty prompt/evidence/verification, so runs referencing them are invalid until Phase B makes selected definitions runnable. Do not invent criteria merely to satisfy the schema.

## Run format

Each real run is one JSON file. Baseline runs execute **without** the token-efficiency skill; optimized runs execute **with** it. Every trial uses a fresh isolated session. Use stable, readable trial ids such as `t1`, `t2`, and `t3`; do not use random UUIDs.

```json
{
  "task_id": "known-symbol-01",
  "task_revision": 1,
  "task_prompt": "exact prompt from the authoritative registry",
  "task_spec_sha256": "sha256-of-canonical-task-contract",
  "trial_id": "t1",
  "pair_order": "baseline-first",
  "mode": "baseline",
  "model": "model-name",
  "tokenizer": "tokenizer-or-provider",
  "token_source": "provider_usage",
  "conditions": {
    "fixture": "hermes-agent@<commit-sha>",
    "provider": "provider-name",
    "hermes_version": "0.20.0",
    "tools": ["search_files", "read_file"],
    "temperature": 0,
    "session_type": "fresh-isolated"
  },
  "input_tokens": 0,
  "output_tokens": 0,
  "tool_calls": 0,
  "files_read": 0,
  "success": true,
  "verification": {
    "status": "passed",
    "evidence": ["verification evidence"]
  }
}
```

Fields:

- Required: `task_id`, `task_revision`, `task_prompt`, `task_spec_sha256`, `trial_id`, `pair_order` (`baseline-first` or `optimized-first`), `mode` (`baseline` or `optimized`), `model`, `tokenizer`, `conditions`, `success`, and `verification`.
- Every run is independently validated against `tasks.json`. Unknown ids, non-runnable scaffold tasks, revision mismatches, non-exact prompts, and task-spec digest mismatches are invalid input and produce no comparison.
- Pair identity is `(task_id, task_revision, task_spec_sha256, trial_id)`. Repeating a task spec across different trials is valid; repeating the same identity in one input file is an error. Different revisions/specs never pair.
- `task_spec_sha256` is SHA-256 over the UTF-8 JSON encoding of the canonical fields `id`, `revision`, `category`, `goal`, `prompt`, `required_evidence`, and `verification`, using `sort_keys=True`, `separators=(",", ":")`, and `ensure_ascii=False`. The comparator calculates the digest from the registry; use its `task_spec_sha256()` helper rather than duplicating the algorithm.
- The three-trial evaluation uses enforced counterbalanced execution order: `t1 = baseline-first`, `t2 = optimized-first`, `t3 = baseline-first`. Both sides of every pair must declare the same `pair_order`; other stable trial ids may use either allowed order.
- `conditions` requires `fixture`, `provider`, `hermes_version`, `tools`, `temperature`, and `session_type`. The provenance fields are non-empty strings, `tools` is a non-empty list of non-empty strings, and `session_type` must be `fresh-isolated`. `temperature` accepts either a finite number when the evaluated runtime explicitly controls that parameter, or the exact string `"provider-managed"` when the Hermes/provider path sends no explicit temperature parameter. The sentinel records omitted/provider-managed behavior; it is not a numeric estimate and does not imply any particular provider default. For repository-based tasks, `fixture` pins the repository revision (for example `hermes-agent@<commit-sha>`); for non-repository tasks use a stable fixture id (for example `structured-data-v1`). Baseline and optimized runs are comparable only when their complete `conditions` objects are identical, so `"provider-managed"` does not compare with a numeric temperature.
- `verification` is an object with `status` (`passed` or `failed`) and a non-empty `evidence` list of non-empty strings. `success=true` requires `status=passed`; `success=false` requires `status=failed`. Contradictory runs are invalid.
- `token_source` is declared provenance metadata and accepts only `provider_usage` or `exact_tokenizer`. It is required when `input_tokens` or `output_tokens` has a numeric value and may be omitted when both are missing/null. The harness validates the declared source type, not the authenticity of the external measurement. Real Evaluation must retain provider/tokenizer evidence outside comparator output.
- Optional (omit when unmeasured): `input_tokens`, `output_tokens`, `tool_calls`, `files_read`. Token fields may be missing; missing values must never be estimated.
- `input_tokens` is the primary context-efficiency metric. Output tokens are displayed for context only; the tool computes no total-savings or cost figure.

The `examples/` directory contains format-only examples with null metrics. They are schema illustrations referencing a non-runnable scaffold and are neither valid measured benchmark results nor runnable comparator inputs.

## Comparing runs

```bash
python scripts/benchmark_summary.py baseline.json optimized.json
```

Both arguments accept a single run object or a JSON list of runs. By default the comparator loads `benchmarks/tasks.json`; tests may supply an isolated registry with `--tasks`. Runs are paired by `(task_id, task_revision, task_spec_sha256, trial_id)`. The summary prints every pair, then a task-level repeated-trial aggregate.

Guards:

- The baseline file must contain only `"mode": "baseline"` runs and the optimized file only `"mode": "optimized"` runs. A wrong mode, including swapped files, is an error exit — never a comparison.
- Duplicate `(task_id, trial_id)` values within one input file are an error exit. Runs are never silently overwritten (no first-wins or last-wins).
- Mismatched `model`, mismatched `tokenizer`, mismatched `conditions`, mismatched `pair_order`, or unpaired identities → `Token reduction unavailable / incomparable`. After both runs pass correctness, missing token counts or mismatched token sources are also incomparable. No percentage is printed.
- Baseline run with `success=false` → `Token reduction unavailable / incomparable` (baseline task failed), even when token counts exist. No efficiency claim can rest on a failed baseline.
- Comparable optimized run with `success=false` → `FAILED OPTIMIZATION`, regardless of the token delta; mismatched model, tokenizer, conditions, or a failed baseline remain incomparable first.
- Malformed JSON or missing required fields → error exit, no summary.
- Unknown or non-runnable tasks, task revision/prompt/spec mismatches, and missing or unsupported declared token sources → error exit, no summary.

## Controlled evaluation contract

Each trial must run in a fresh isolated session. Within one baseline/optimized pair, keep the model, provider, fixture SHA, Hermes version, tools, temperature, session type, task prompt, and verification criteria identical. The only treatment difference is whether `token-efficiency` is disabled for baseline or enabled for optimized. Do not manufacture savings by changing the prompt, system configuration, tools, model, temperature, or fixture.

Do not pin a rolling repository revision until the real evaluation deliberately freezes its fixture SHA. The format examples are not results, and this repository contains no V2.1 measurement from them.

## Repeated-trial aggregate

For each task, the summary reports total trials, comparable successful pairs, incomparable pairs, and optimized failures. It uses `statistics.median` for baseline input tokens, optimized input tokens, absolute delta, and pairwise percentage delta across valid comparable successful pairs only.

At least two valid comparable successful pairs are required; otherwise the aggregate says `INSUFFICIENT REPEATED TRIALS`. Comparable optimized failures are counted explicitly and never folded into or hidden by a median. Unpaired or parity-mismatched failures remain incomparable under the comparator precedence. The harness does not assign `Worth Using`, `Neutral`, or `Potentially Harmful` verdicts.
