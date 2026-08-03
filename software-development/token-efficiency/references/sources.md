# Source Projects and Adapted Ideas

Load this reference when selecting an optional compression tool, checking provenance, or extending the workflow.

## Microsoft LLMLingua

- Repository: https://github.com/microsoft/LLMLingua
- Purpose: prompt and KV-cache compression; the project reports compression up to 20× with minimal performance loss for its evaluated methods and tasks.
- Adapted idea: separate high-value constraints and evidence from low-value connective text; compress selectively rather than truncating blindly.
- Hermes use: apply the principle by default. Use the package only when installed or explicitly approved.
- Caveat: benchmark claims do not guarantee the same savings or accuracy on a new workload. Measure the actual prompt and verify retained constraints.

## Repomix

- Repository: https://github.com/yamadashy/repomix
- Included upstream skill: https://github.com/yamadashy/repomix/tree/main/skills/repomix-explorer
- Purpose: pack repositories into AI-friendly output with token estimates, include/ignore filters, and optional Tree-sitter-based compression.
- Adapted idea: create a repository map, narrow with include patterns, search packed output before reading it, and compress only broad repository analysis.
- Useful upstream options: `--include`, `--ignore`, `--compress`, `--output`, and `--remote`.
- Caveat: repository packing is wasteful for one-file or one-symbol questions. Secret detection is defense in depth, not permission to share packed output without review.

## Serena

- Repository: https://github.com/oraios/serena
- Purpose: MCP-based semantic code retrieval and editing using symbol-aware navigation.
- Adapted idea: retrieve definitions and symbol neighborhoods instead of reading whole files or repositories.
- Hermes use: prefer exact symbol/file search, then definition → callers/imports → configuration → tests. If Serena MCP is configured, use its semantic tools; otherwise follow the same retrieval pattern with Hermes file/search tools.
- Caveat: symbol retrieval can miss runtime registration, generated code, reflection, or configuration-driven behavior; verify those paths separately.

## Aider

- Repository: https://github.com/Aider-AI/aider
- Purpose: AI pair programming with a repository map designed to provide useful whole-codebase context without loading all source text.
- Adapted idea: map entry points and important symbols first, then load only task-relevant code.
- Hermes use: maintain a compact path/symbol/dependency map during coding tasks and cite the files used for each conclusion.
- Caveat: a map is an index, not evidence. Reopen source and tests before editing or making behavioral claims.

## TOON

- Repository: https://github.com/toon-format/toon
- Purpose: Token-Oriented Object Notation, a compact lossless representation of the JSON data model optimized for uniform structured records.
- Adapted idea: use compact tabular serialization for large arrays whose objects share the same fields.
- Hermes use: prefer Markdown tables for small human-facing datasets; consider TOON only when both ends support it and token measurement shows a benefit.
- Caveat: the project states that deeply nested or non-uniform data may be more efficient in JSON. Do not convert blindly.

## Selection Guide

| Need | First choice | Escalation |
|---|---|---|
| One symbol or known file | Hermes search + targeted read | Serena semantic retrieval |
| Large unfamiliar repository | path/symbol map | Repomix with filters and optional compression |
| Oversized prose prompt | manual constraint/evidence separation | LLMLingua if available and verified |
| Large uniform JSON records | compact table | TOON if supported and measured |
| Cross-session continuity | concise handoff + stable memory | external semantic memory provider |

## Measurement Protocol

When a tokenizer or tool-reported count is available:

1. Record the original token count.
2. Record the reduced token count using the same tokenizer/model encoding.
3. Run the same acceptance checks on original and reduced contexts.
4. Report both counts and any observed quality difference.
5. Do not generalize one workload's percentage to another workload.

When no tokenizer is available, report only operational reductions such as files excluded, sections read, duplicate records removed, or tool output rows retained.
