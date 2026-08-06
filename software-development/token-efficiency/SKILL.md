---
name: token-efficiency
description: "Token-efficient retrieval: large repos, handoffs, long sessions."
version: 1.0.1
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [tokens, context, compression, retrieval, coding, research]
    related_skills: [codebase-inspection, systematic-debugging]
---

# Token-Efficient Agent Workflows

## Overview

Reduce token use without reducing correctness. The core loop is **map → retrieve → read narrowly → compress evidence → verify**. Treat context as a budgeted working set, not a dumping ground.

This workflow adapts ideas from LLMLingua (selective prompt compression), Repomix (repository packing and Tree-sitter compression), Serena (symbol-level semantic retrieval), Aider (repository maps), and TOON (compact representation of uniform structured data). Load `references/sources.md` only when source details or project-specific tooling are needed.

### Before / after

- **Before:** read every file in an unfamiliar repository and carry the full output into the next step.
- **After:** map the tree, search for the target symbol, read its definition plus callers/configuration/tests, and hand off only those evidence pointers and unresolved questions.

The after pattern narrows the working set; report token counts only when the same tokenizer measures both versions.

## When to Use

Use for:
- unfamiliar or large repositories;
- research involving many pages, files, logs, or API records;
- long-running sessions approaching context compression;
- repetitive tool output or large structured payloads;
- cost-sensitive multi-agent work.

Do not use when:
- the answer is already available from one small file or one focused call;
- compression would remove legally, medically, financially, or operationally critical detail;
- the user explicitly requests full verbatim output;
- exact byte-for-byte content is the deliverable.

## Non-Negotiable Rule

**Never claim a token reduction that was not measured.** If no tokenizer or tool-reported token count is available, describe the change qualitatively: `narrower context`, `fewer files`, or `less repeated output`.

Compression is successful only when the final answer remains traceable to retrieved evidence and all user requirements are satisfied.

## Workflow

### 1. Define the working set

Before broad retrieval, identify:
- the exact deliverable;
- the minimum evidence needed to support it;
- constraints that must survive compression;
- likely source locations or search terms.

Do not restate the full conversation. Carry forward only decisions, constraints, unresolved questions, evidence pointers, and verification state.

**Completion criterion:** there is a one-sentence task target and a short list of evidence classes to retrieve.

### 2. Build a cheap map before reading content

For codebases, collect only:
- top-level structure;
- language and framework indicators;
- manifests and entry points;
- relevant symbols or filenames;
- tests adjacent to the target behavior.

For web research, collect only:
- candidate source URLs;
- titles, dates, publishers, and short snippets;
- source authority and recency.

For datasets or APIs, collect only:
- schema or keys;
- row/item count when provided by a tool;
- a tiny representative sample;
- fields required by the task.

Prefer `search_files(target='files')`, `search_files(output_mode='files_only'|'count')`, compact browser snapshots, or DOM extraction over full-content reads.

**Completion criterion:** likely evidence locations are ranked before any large file/page is loaded.

### 3. Retrieve before reading

Use the narrowest available operation:

1. exact symbol, phrase, filename, or key search;
2. search with zero or minimal context;
3. targeted file/page section read;
4. expand around a confirmed hit;
5. full read only when structure or exact completeness requires it.

For code, follow a **symbol neighborhood**:
- definition;
- direct callers or imports;
- configuration affecting it;
- tests proving expected behavior.

Do not recursively enumerate a repository and then read every match. Do not request full browser snapshots when a compact snapshot or a DOM query can extract the needed fields.

**Completion criterion:** every large read is justified by a confirmed hit or an explicit completeness requirement.

### 4. Compress tool output before it enters reasoning context

When three or more mechanical calls would produce large outputs, use `execute_code` to call tools programmatically and print only the reduced result. Keep:
- source identifiers and paths;
- matched lines or fields;
- counts needed for decisions;
- errors and uncertainty;
- enough local context to verify interpretation.

Drop:
- duplicate records;
- repeated stack frames;
- unchanged boilerplate;
- irrelevant metadata;
- generated, vendor, cache, and binary paths unless directly relevant.

For browser pages, use `browser_console` to extract structured fields from the DOM instead of repeatedly loading full page text.

**Completion criterion:** downstream reasoning receives an evidence table or concise excerpts, not a raw dump.

### 5. Choose representation deliberately

Use these formats by data shape:

| Data shape | Preferred representation |
|---|---|
| Short prose evidence | concise bullets with source pointers |
| Code relationships | symbol/path map |
| Uniform records with identical fields | compact table; TOON only when supported and beneficial |
| Deeply nested or irregular data | JSON or YAML; do not force TOON |
| Repository overview | ranked file/symbol map |
| Long logs | grouped errors + first/last relevant occurrence |
| Handoff to another agent | goal, constraints, evidence, open questions, verification |

Never convert data merely because a compact format exists. Conversion overhead and ambiguity can cost more than it saves.

**Completion criterion:** the representation preserves required structure with no unexplained field loss.

### 6. Use optional compression tools only when justified

#### Repomix

Use for broad understanding of a large or remote repository when ordinary targeted search is insufficient. Start with `--include` and exclusions; add `--compress` for large repositories. Write output outside the project unless the user requests an artifact.

Do not pack an entire repository for a one-symbol lookup. Do not trust automatic secret filtering as the only security boundary; review includes/excludes before sharing packed output.

#### LLMLingua

Use only when an LLMLingua-compatible compressor is already available or the user approves installation. Preserve instructions, negations, identifiers, numbers, citations, code, and acceptance criteria. Re-verify the compressed prompt against the original constraints before use.

#### TOON

Use for large arrays of uniform objects when both producer and consumer understand TOON. Prefer ordinary tables for small human-facing results. Keep JSON for irregular or deeply nested structures.

**Completion criterion:** optional tooling has a clear expected benefit, no silent dependency installation, and a fallback path.

### 7. Protect prompt caching and session continuity

Keep stable context stable:
- do not change toolsets or system-level context mid-session merely to save tokens;
- do not repeatedly inject the same instructions;
- keep reusable procedures in skills rather than copying them into every prompt;
- keep durable facts in memory, not session summaries;
- keep transient evidence in concise session notes or source pointers.

Before context compression or agent handoff, create a compact state block:

```text
Goal:
Constraints:
Decisions:
Evidence (path/URL + finding):
Open questions:
Verification completed:
Next action:
```

**Completion criterion:** another agent or a post-compression session can continue without replaying raw history.

### 8. Verify information retention

Before answering, compare the reduced context with the task requirements:
- every requirement is represented;
- every factual conclusion has a path, URL, or tool-result basis;
- uncertainty and conflicting evidence remain visible;
- exact identifiers, numbers, and negations were not compressed away;
- verification results are included, not replaced by a summary claim.

If compression causes ambiguity, reopen only the relevant source section.

**Completion criterion:** the final response is complete and grounded without reloading unrelated context.

## Multi-Agent Token Discipline

Delegate only independent, reasoning-heavy work. Do not delegate mechanical extraction that `execute_code` can reduce in one inference.

Each child receives only:
- a self-contained goal;
- necessary constraints;
- specific source locations;
- required output schema;
- a request for evidence handles rather than raw transcripts.

When results return, merge by claim and evidence, deduplicate overlap, and resolve contradictions before presenting them. Do not paste every child summary verbatim.

## Common Pitfalls

1. **Reading everything first.** Build a map and search before reading.
2. **Compressing instructions with evidence.** Preserve instructions and acceptance criteria verbatim; compress evidence separately.
3. **Using a large repository pack for a narrow edit.** Read the target symbol and its neighborhood instead.
4. **Moving cost to another model call.** A compressor that requires expensive inference may not reduce total cost; measure end-to-end when possible.
5. **Inventing savings percentages.** Report only measured token counts.
6. **Losing provenance.** Every compressed fact keeps its file path, URL, record ID, or line range.
7. **Over-delegating.** Parallel agents duplicate context unless their scopes are disjoint.
8. **Using compact syntax on tiny data.** For small inputs, plain text or a Markdown table is often cheaper and clearer.
9. **Treating memory as a transcript archive.** Save stable facts only; retrieve historical detail from session search or external memory.
10. **Assuming secret scanners are perfect.** Explicitly exclude credentials, environment files, keys, and private data.
11. **Searching a literal that starts with hyphens.** Some grep-backed wrappers can parse a pattern such as `--compress` as an option. Search with a surrounding token such as `["']--compress`, or use a non-leading literal; do not retry the same failing query unchanged.
12. **Stopping at an async or adapter boundary.** When tracing code, include the worker, callback, registry, or adapter that links two confirmed symbols; otherwise a narrow context can omit the decisive call edge.

## Verification Checklist

- [ ] Task target and required evidence were defined.
- [ ] A cheap map/search preceded large reads.
- [ ] Only confirmed relevant sections were expanded.
- [ ] Raw tool output was filtered and deduplicated.
- [ ] Required constraints, identifiers, numbers, and negations survived.
- [ ] Claims retain source pointers.
- [ ] Optional compressors were justified and dependencies were not installed silently.
- [ ] Any savings claim is backed by measured token counts.
- [ ] Final output satisfies the user's requested format and completeness.
