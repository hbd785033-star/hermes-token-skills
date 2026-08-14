---
name: token-efficiency
description: "Use for token-saving work in repos, sessions, and handoffs."
version: 2.0.1
author: hbd785033-star
license: MIT
metadata:
  hermes:
    tags: [tokens, context, compression, retrieval, coding, research]
    related_skills: [codebase-inspection, systematic-debugging]
---

# Token-Efficient Agent Workflows

## Overview

Reduce token use without reducing correctness. Reduce unnecessary context **before** compressing what already entered it. Treat context as a budgeted working set:

```text
Map → Retrieve → Narrow Read → Reduce Tool Output → Optional Compression → Verify
```

Do not ask "how do I compress this?" first. Ask "why is this entering context at all?"

Load references only when the situation requires them:

| Reference | Load when |
|---|---|
| `references/retrieval.md` | Searching code, large or unfamiliar repos, symbol tracing |
| `references/compression.md` | Reducing tool output, choosing data formats, LLMLingua/TOON |
| `references/handoff.md` | Long sessions, context compression, child/multi-agent handoff |
| `references/evaluation.md` | Judging or reporting whether an optimization worked |
| `references/sources.md` | Upstream project details, options, and provenance |

## When to Use

- unfamiliar or large repositories;
- research across many pages, files, logs, or API records;
- long sessions approaching context compression;
- repetitive tool output or large structured payloads;
- cost-sensitive multi-agent work.

## When NOT to Use

- the answer is available from one small file or one focused call;
- compression would remove legally, medically, financially, or operationally critical detail;
- the user requests full verbatim output;
- exact byte-for-byte content is the deliverable.

## Core Rules (non-negotiable)

1. Never claim token savings without measurement. Without a tokenizer or tool-reported count, describe changes qualitatively: `narrower context`, `fewer files`, `less repeated output`.
2. Preserve instructions, acceptance criteria, identifiers, numbers, negations, and citations/provenance.
3. Search before broad read.
4. Full-file or full-repo reads require justification: a confirmed hit or an explicit completeness requirement.
5. Compression must not destroy traceability; every fact keeps a path, URL, record ID, or line range.
6. Mechanical extraction prefers code and tools (for example `execute_code`) over extra agent calls.
7. Security-sensitive files (credentials, keys, environment files, private data) must not be blindly packed or shared.
8. Compression failure must fall back to reopening the original evidence.

## Routing Decision

| Need | Preferred path |
|---|---|
| Known symbol/file | targeted search + narrow read |
| Cross-file semantic relationship | Serena if available, else search-based tracing |
| Large unfamiliar repository | cheap map + targeted search; filtered Repomix only if needed |
| Large repetitive tool output | `execute_code` / local reduction |
| Long prose context | manual reduction first |
| Oversized prose after reduction | LLMLingua (optional) |
| Uniform structured records | compact table; TOON optional |
| Long-session handoff | structured state block |

Every optional tool requires an availability check and a fallback. Never install dependencies silently.

## Core Workflow

1. **Map.** Define the deliverable and the minimum evidence for it. Build a cheap map (tree, manifests, entry points, candidate URLs or schemas) before reading content. Prefer `search_files(target='files')` or `search_files(output_mode='files_only'|'count')` over content reads.
2. **Retrieve.** Use the narrowest operation: exact search → minimal-context search → targeted section read → expand around a confirmed hit → full read only when justified. For code, follow the symbol neighborhood: definition → callers/imports → configuration → tests. Details: `references/retrieval.md`.
3. **Narrow Read.** Expand only around confirmed hits. Never enumerate a repository and read every match.
4. **Reduce Tool Output.** Filter and deduplicate output before it enters reasoning context. When tool calls would return large or repetitive output, use `execute_code` or local reduction to batch, filter, and print only the evidence needed for reasoning. Details: `references/compression.md`.
5. **Optional Compression.** Only after the steps above: LLMLingua for oversized prose, TOON for large uniform records. Both are optional, measured, and reversible. Details: `references/compression.md`.
6. **Verify.** Compare the reduced context against the task requirements before answering. For session or agent handoffs, use the state block in `references/handoff.md`.

## Failure / Fallback

- An optional tool is unavailable (Serena, Repomix, LLMLingua, TOON): fall back to targeted Hermes search/read and manual reduction. This workflow must work without any of them.
- Compression causes ambiguity or drops constraints: discard the compressed form, reopen only the relevant source section, and proceed from the original evidence.
- A search literal starts with hyphens (for example `--compress`) and the wrapper parses it as an option: search with a surrounding token such as `["']--compress`, or use a non-leading literal. Do not retry the same failing query unchanged.
- A narrow trace ends at an async, adapter, or registry boundary: include the worker, callback, registry, or adapter that links the confirmed symbols before concluding.

## Verification

- [ ] Task target and minimum evidence were defined before retrieval.
- [ ] A map or search preceded every large read; each full read is justified.
- [ ] Tool output was filtered and deduplicated before reasoning.
- [ ] Constraints, identifiers, numbers, negations, and provenance survived.
- [ ] Optional tools were availability-checked, justified, and not silently installed.
- [ ] Any savings claim is backed by measured token counts from the same tokenizer; otherwise only qualitative reductions are reported. See `references/evaluation.md` and `benchmarks/`.
- [ ] The final output satisfies the requested format and completeness.
