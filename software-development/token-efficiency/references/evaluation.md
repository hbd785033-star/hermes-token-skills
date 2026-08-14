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
- Each real run is recorded as one JSON object (see `benchmarks/README.md` for the schema). Token fields may be absent; absent fields must never be estimated or fabricated.
- `benchmark_summary.py` is a repository-level evaluation helper available in the source repository root's `scripts` directory; it compares a baseline run (without this skill) against an optimized run (with this skill) for the same task and is not required for runtime skill use.

Comparison guards in the tool:

- wrong file mode, swapped files, or duplicate `task_id` values → error exit, no comparison;
- mismatched model, tokenizer, or run `conditions`, unpaired tasks, or missing token counts → `Token reduction unavailable / incomparable`, no percentage;
- baseline run with `success=false` → incomparable; no efficiency claim rests on a failed baseline;
- optimized run with `success=false` → `FAILED OPTIMIZATION` only after model, tokenizer, conditions, and baseline success are comparable.

Use benchmark evidence to decide whether heavier retrieval machinery (for example an Aider-style context map) is justified. Do not build it speculatively.
