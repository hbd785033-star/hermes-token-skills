# Evaluation: Judging Whether Token Optimization Worked

Load this reference when judging or reporting whether a token optimization actually succeeded.

## Success criteria

Lower tokens alone != success.

```text
Success =
less context
+
same or better task correctness
+
preserved evidence
```

Token reduction without correctness is not success. A run that drops input tokens but fails the task is a failed optimization, not a saving.

## What counts as a claim

- **Measured token savings** require a tokenizer or tool-reported token count, the same tokenizer/model on both sides, and the same acceptance checks on original and reduced contexts. Report both counts and any observed quality difference. Do not generalize one workload's percentage to another workload.
- **Without a tokenizer**, report only operational reductions: files excluded, sections read, duplicate records removed, tool output rows retained. Describe them qualitatively (`narrower context`, `fewer files`).
- **File size or character reduction is not a token saving.** Do not present byte/character changes as model token results.
- **Upstream benchmark claims** (for example LLMLingua or TOON project numbers) belong to those projects' evaluated workloads. Attribute them; never present them as results on your workload.

## Benchmark harness

The repository provides a minimal harness:

- `benchmarks/tasks.json` defines task categories (`known-symbol`, `cross-file`, `large-repo`, `tool-output`, `structured-data`, `handoff`) with goals, required evidence, and verification steps.
- Each real run is recorded as one JSON object (see `benchmarks/README.md` for the authoritative schema). The comparator validates task id, revision, exact prompt, and canonical task-spec digest against `tasks.json`; scaffold tasks are not runnable. Repeated runs use stable `trial_id` values and a fresh isolated session. Token fields may be absent; absent fields must never be estimated or fabricated.
- `benchmark_summary.py` is a repository-level evaluation helper available in the source repository root's `scripts` directory; it pairs baseline runs (without this skill) and optimized runs (with this skill) by `(task_id, task_revision, task_spec_sha256, trial_id)` and is not required for runtime skill use.

Comparison guards in the tool:

- wrong file mode, swapped files, duplicate full pair identities, malformed structured verification, unknown/non-runnable tasks, task identity mismatches, missing or unsupported declared token sources, or invalid conditions → error exit, no comparison;
- mismatched model, tokenizer, complete run `conditions`, or `pair_order`, unpaired identities, or missing token counts → `Token reduction unavailable / incomparable`, no percentage;
- baseline run with `success=false` → incomparable; no efficiency claim rests on a failed baseline;
- optimized run with `success=false` → `FAILED OPTIMIZATION` only after model, tokenizer, conditions, pair order, and baseline success are comparable;
- successful pairs require matching accepted `token_source` values before any percentage is calculated; task aggregates require at least two comparable successful pairs and report comparable optimized failures separately.

`token_source` is declared provenance metadata. The harness validates the declared source type, not the authenticity of the provider/tokenizer measurement. Real Evaluation must preserve external provider usage or tokenizer evidence outside the comparator result.

The controlled-run `temperature` condition accepts a finite number only when the evaluated runtime explicitly sets that value. Use the exact sentinel `"provider-managed"` when the Hermes/provider path omits the temperature parameter and leaves sampling behavior to the runtime or provider. The sentinel is not a numeric estimate, does not imply temperature 0 or 1, and makes no claim that a provider default is stable across providers or over time. Baseline and optimized runs still require exact equality of their complete `conditions` objects, so a provider-managed run is incomparable with a numerically controlled run.

Use benchmark evidence to decide whether heavier retrieval machinery (for example an Aider-style context map) is justified. Do not build it speculatively.
