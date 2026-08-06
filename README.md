# Hermes Skills

A collection of reusable [Hermes Agent](https://github.com/NousResearch/hermes-agent) skills. Each skill is a directory containing a `SKILL.md`; optional supporting material belongs under that skill's `references/`, `templates/`, `scripts/`, or `assets/` directory.

## Skill index

| Skill | Path | Use it for |
|---|---|---|
| `token-efficiency` | [`software-development/token-efficiency/`](software-development/token-efficiency/) | Token-efficient retrieval and context discipline for large repositories, long sessions, and agent handoffs. |

The index is intentionally short and should be updated when a skill is added, renamed, or removed. The validator discovers every `SKILL.md` independently of this table.

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
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [short, descriptive]
    related_skills: []
---
```

Keep the trigger at the beginning of `description`: Hermes's compact skill index exposes only the beginning of long descriptions.

## Install paths by platform

The repository is source; install a skill into the active Hermes profile's `skills/` directory. Do not assume one literal `~/.hermes` path is universal. Resolve the active home/profile from the environment and the Hermes installation you are using.

| Environment | Usual default profile path | Notes |
|---|---|---|
| Linux | `$HOME/.hermes/skills/` | `HERMES_HOME` may override the Hermes home. |
| macOS | `$HOME/.hermes/skills/` | Use the same `HERMES_HOME` override when configured. |
| Windows native | `%USERPROFILE%\\.hermes\\skills\\` | In Git Bash this is commonly `/c/Users/<user>/.hermes/skills/`; use the active profile rather than copying that literal. |
| WSL | `$HOME/.hermes/skills/` inside WSL | This is separate from a native Windows Hermes home unless explicitly shared. |
| Named profile / managed install | `<Hermes home>/profiles/<profile>/skills/` (where supported) | Prefer Hermes's profile-aware commands and configuration over guessing a filesystem path. |

For a checkout, copy the skill directory (not the repository root) into the target profile, or use the Hermes skill installation workflow when the repository is exposed through a supported source. For hub-managed skills, inspect before installing and use commands such as:

```bash
hermes skills inspect <source>
hermes skills install <source>
hermes skills list --source hub
```

If an external skill directory is configured, Hermes can scan it alongside the local directory; consult the [Skills System documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/) for the current configuration and precedence rules.

## Validation

Run the repository validator from the repository root:

```bash
python scripts/validate_skills.py
```

It checks frontmatter fields and structure, lowercase kebab-case directories, local references, and whether every `metadata.hermes.related_skills` name is either present in this repository or declared as an external dependency below. Run the tests as well:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

GitHub Actions additionally runs the validator and a basic Markdown lint check on pushes and pull requests. A clean `git diff --check` is also recommended before committing.

## External `related_skills`

`metadata.hermes.related_skills` may name a skill that Hermes provides outside this repository. Such a name is an external dependency, not a file in this checkout, and may not resolve in a fresh installation. Declare each such name here with its source or installation expectation:

- `codebase-inspection` — external Hermes skill; install or enable it from the Hermes skill catalog/profile when using the related workflow.
- `systematic-debugging` — external Hermes skill; install or enable it from the Hermes skill catalog/profile when using the related workflow.

When possible, prefer repository-local related skills for portable references. If an external skill is promoted into this repository, move it into the index and remove its external declaration.

## Contributing

Keep changes focused, add or update validator tests for structural behavior, run the local checks, and use a [Conventional Commit](https://www.conventionalcommits.org/) message. Changes to this branch are not merged automatically.
