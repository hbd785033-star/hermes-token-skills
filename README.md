# Hermes Token Skills

Token-aware context engineering skills for [Hermes Agent](https://github.com/NousResearch/hermes-agent). Reduce unnecessary context without sacrificing correctness.

## What is this?

A collection of reusable Hermes skills. Each skill is a directory containing a `SKILL.md`; optional supporting material belongs under that skill's `references/`, `templates/`, `scripts/`, or `assets/` directory.

| Skill | Path | Use it for |
|---|---|---|
| `token-efficiency` | [`software-development/token-efficiency/`](software-development/token-efficiency/) | Token-aware retrieval and context discipline for large repositories, long sessions, and agent handoffs. |

The index is intentionally short and should be updated when a skill is added, renamed, or removed. The validator discovers every `SKILL.md` independently of this table.

## When should I use it?

Use `token-efficiency` when working in unfamiliar or large repositories, researching across many sources, running long sessions near context compression, handling repetitive tool output, or coordinating cost-sensitive multi-agent work. Skip it when one small file or one focused call already answers the question.

## How does it work?

Reduce unnecessary context **before** compressing what already entered it:

```text
Task
 │
 ▼
Map
 │
 ▼
Retrieve
 │
 ├── Targeted Hermes tools
 ├── Serena (optional)
 └── Repomix (broad repo only)
 │
 ▼
Narrow Read
 │
 ▼
Reduce Tool Output
 │
 ▼
Optional Compression
 │
 ├── LLMLingua
 │
 └── TOON
 │
 ▼
Verify
```

The main `SKILL.md` carries only the decision table, core rules, and workflow. Detail lives in progressively disclosed references (`retrieval`, `compression`, `handoff`, `evaluation`, `sources`) loaded only when needed. All optional tools (Serena, Repomix, LLMLingua, TOON) require an availability check and a fallback; nothing is installed silently.

## How do I install it?

The repository is source; install a skill into the active Hermes profile's `skills/` directory. Do not assume one literal `~/.hermes` path is universal. Resolve the active home/profile from the environment and the Hermes installation you are using.

| Environment | Usual default profile path | Notes |
|---|---|---|
| Linux | `$HOME/.hermes/skills/` | `HERMES_HOME` may override the Hermes home. |
| macOS | `$HOME/.hermes/skills/` | Use the same `HERMES_HOME` override when configured. |
| Windows native | `$HERMES_HOME/skills/` when `HERMES_HOME` is set; otherwise use the active Hermes installation's profile path | Hermes Desktop commonly uses `%LOCALAPPDATA%\hermes\skills\`; do not copy a guessed path if `hermes config path` or the active environment says otherwise. |
| WSL | `$HOME/.hermes/skills/` inside WSL | This is separate from a native Windows Hermes home unless explicitly shared. |
| Named profile / managed install | `<Hermes home>/profiles/<profile>/skills/` (where supported) | Prefer Hermes's profile-aware commands and configuration over guessing a filesystem path. |

For a checkout, copy the skill directory (not the repository root) into the target profile, or use the Hermes skill installation workflow when the repository is exposed through a supported source. For hub-managed skills, inspect before installing and use commands such as:

```bash
hermes skills inspect <source>
hermes skills install <source>
hermes skills list --source hub
```

If an external skill directory is configured, Hermes can scan it alongside the local directory; consult the [Skills System documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/) for the current configuration and precedence rules.

## How do I validate it?

Run the repository validator from the repository root:

```bash
python -m pip install -r requirements-dev.txt
python scripts/validate_skills.py
```

It checks frontmatter fields and structure, lowercase kebab-case directories, local references, and whether every `metadata.hermes.related_skills` name is either present in this repository or declared as an external dependency below. Run the tests as well:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

GitHub Actions additionally runs the validator and a basic Markdown lint check on pushes and pull requests. A clean `git diff --check` is also recommended before committing.

## How do I benchmark it?

The `benchmarks/` directory defines a minimal task set (`known-symbol`, `cross-file`, `large-repo`, `tool-output`, `structured-data`, `handoff`). Record real runs as JSON — one baseline run without the skill and one optimized run with it — then compare them:

```bash
python scripts/benchmark_summary.py baseline.json optimized.json
```

Token deltas are reported only for comparable successful runs: the task, model, tokenizer, and run conditions must match, both runs must succeed, and input-token counts must be measured. Otherwise the summary reports `Token reduction unavailable / incomparable`; a comparable optimized run that fails is marked `FAILED OPTIMIZATION`. See `benchmarks/README.md` for the run format.

A note on numbers: this project makes no percentage token-savings claim of its own. File-size reductions in this repository are not model token savings, and upstream project benchmarks (for example LLMLingua or TOON) apply to those projects' evaluated workloads, not to yours.

## Directory and naming conventions

Use this layout:

```text
<category>/<skill-name>/SKILL.md
<category>/<skill-name>/references/<supporting-file>.md
```

- Category and skill directories use lowercase kebab-case (`software-development`, `token-efficiency`).
- A skill directory name must match the frontmatter `name` and be at most 64 characters.
- Every `SKILL.md` starts with YAML frontmatter at byte 0 and has a non-empty body.
- Keep supporting files close to the skill that uses them. Local references must point to files that exist.
- Prefer an existing category over inventing a new top-level category. A new category should have a clear, reusable domain boundary.

Required frontmatter shape:

```yaml
---
name: my-skill
description: Use when <trigger>. <one-line behavior>.
version: 1.0.0
author: <human-contributor-name>
license: MIT
metadata:
  hermes:
    tags: [short, descriptive]
    related_skills: []
---
```

Keep the trigger at the beginning of `description`: Hermes's compact skill index exposes only the beginning of long descriptions.

## External `related_skills`

`metadata.hermes.related_skills` may name a skill that Hermes provides outside this repository. Such a name is an external dependency, not a file in this checkout, and may not resolve in a fresh installation. Declare each such name here with its source or installation expectation:

- `codebase-inspection` — external Hermes skill; install or enable it from the Hermes skill catalog/profile when using the related workflow.
- `systematic-debugging` — external Hermes skill; install or enable it from the Hermes skill catalog/profile when using the related workflow.

When possible, prefer repository-local related skills for portable references. If an external skill is promoted into this repository, move it into the index and remove its external declaration.

## Contributing

Keep changes focused, add or update validator tests for structural behavior, run the local checks, and use a [Conventional Commit](https://www.conventionalcommits.org/) message. Changes to this branch are not merged automatically.
