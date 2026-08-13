# Handoff: Long Sessions, Compression, and Multi-Agent Work

Load this reference for long-running sessions, context compression, child agents, or multi-agent handoffs.

## Handoff state block

Before context compression or an agent handoff, create a compact state block:

```text
Goal:
Constraints:
Decisions:
Evidence:
Open questions:
Verification:
Next action:
```

- **Goal:** the one-sentence task target.
- **Constraints:** requirements that must survive, verbatim where exact wording matters.
- **Decisions:** what was decided and why, in one line each.
- **Evidence:** pointers (path/URL/record ID + finding), not raw transcripts.
- **Open questions:** unresolved items only.
- **Verification:** checks already run and their results.
- **Next action:** the single next step.

**Completion criterion:** another agent or a post-compression session can continue without replaying raw history.

## Memory is not a transcript archive

Memory ≠ transcript archive. Save only durable facts (stable preferences, project conventions, standing decisions). Keep transient evidence as references — paths, URLs, record IDs — and retrieve historical detail from session search or external memory when needed.

## Session continuity and prompt caching

Keep stable context stable:

- do not change toolsets or system-level context mid-session merely to save tokens;
- do not repeatedly inject the same instructions;
- keep reusable procedures in skills rather than copying them into every prompt;
- keep durable facts in memory, not session summaries.

## Child agents and multi-agent work

Delegate only independent, reasoning-heavy work. Do not delegate mechanical extraction that `execute_code` can reduce in one inference. Parallel agents duplicate context unless their scopes are disjoint.

Each child receives only:

- a self-contained goal;
- necessary constraints;
- specific source locations;
- a required output schema;
- a request for evidence handles rather than raw transcripts.

When results return, merge by claim and evidence, deduplicate overlap, and resolve contradictions before presenting. Do not paste every child summary verbatim.
