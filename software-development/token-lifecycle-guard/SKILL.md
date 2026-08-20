---
name: token-lifecycle-guard
description: "Detect delegated lifecycle risk with read-only evidence."
version: 1.0.0
author: hbd785033-star
license: MIT
metadata:
  hermes:
    tags: [lifecycle, safety, delegation, watchdog, postflight]
    related_skills: [token-efficiency]
---

# Token Lifecycle Guard

## Purpose

`token-lifecycle-guard` is an orthogonal lifecycle-safety layer for Hermes. It detects lifecycle risk when spawned, detached, background, or provider-retry work may have exceeded an explicit boundary. It does not prevent every runaway and does not replace Hermes execution or `token-efficiency` retrieval policy.

Core contract:

```text
spawned work must have an owner, a budget, a terminal condition, and terminal proof
```

Unknown is not safe to enforce. Missing live evidence remains `UNKNOWN`.

## Daily Stack Boundary

Keep the normal stack unchanged:

```text
Hermes native tools
  -> Serena for on-demand semantic or cross-file escalation
  -> filtered Repomix for targeted broad-repository fallback
```

`token-efficiency` reduces unnecessary context during healthy work. This skill detects whether work has escaped its intended lifecycle. It does not select retrieval tools, make Serena always-on, make Repomix persistent, or change either configuration.

## V1 Behavior

The V1 watchdog is deterministic local Python and read-only by default:

```text
Prevent Policy
  -> Discover
  -> Observe
  -> Correlate Identity
  -> Classify
  -> Report
  -> Postflight / Terminal Audit
```

It does not call an LLM, delegate a reviewer, poll a provider through a model, kill a process, interrupt a session or subagent, close a session, pause delegation, delete state, or rewrite configuration.

The stdio transport uses one daemon stdout reader that owns blocking pipe I/O and a bounded queue consumed by the request thread. Startup and RPC deadlines use `time.monotonic()`. Cleanup retains the exact child `Popen` handle, proves the child terminal with bounded EOF/terminate/kill waits, then performs a bounded stdout-reader join; an inconclusive reader or process state is reported explicitly.

The implementation is the [watchdog script](../../scripts/token_lifecycle_watch.py). Its pure classifier consumes normalized snapshots, while the Gateway transport is a separate injectable boundary. Run a fixture-only check with:

```bash
python scripts/token_lifecycle_watch.py --snapshot-json '{"before":{"targets":[]},"after":{"targets":[]}}'
```

For live mode, provide the installed Gateway command explicitly through `--gateway-command` or `HERMES_GATEWAY_COMMAND`. The command must be the locally verified Hermes TUI Gateway entrypoint. The watchdog sends only:

```text
session.active_list
session.status
session.usage
delegation.status
```

If the installed version exposes a different transport or response shape, stop and re-audit the installed source. Do not infer a contract from a network document.

## Evidence And Identity

Use evidence in this order:

1. installed Hermes live Gateway state;
2. live delegation or subagent lifecycle state;
3. live usage or activity telemetry;
4. explicit identity and correlation metadata;
5. process evidence when genuinely necessary;
6. persisted DB/history as historical evidence only.

`session.active_list` is a live in-memory Gateway snapshot in the verified Hermes `v0.20.4` installation. `session.list` is persisted or historical discovery, but the V1 live transport does not acquire it. A historical `running` row never proves current execution. `STALE_RECORD` is available only when historical evidence is explicitly supplied or otherwise available; a live-only run does not claim to enumerate or audit all historical rows.

Keep target kinds distinct:

```text
SESSION  -> session_id and live session state
SUBAGENT -> subagent_id, parent_session_id when exposed, correlation_id when exposed, role, depth, state
```

A live target does not prove ownership. Ownership is `PROVEN` only when an explicit parent/session/correlation relationship or other installed lifecycle identity proves it. Otherwise it is `UNKNOWN`.

## Classification

The classifier returns:

- `HEALTHY`: live work follows the current contract without a terminal breach.
- `LONG_RUNNING_EXPECTED`: live work is explicitly allowed to continue and has a proven owner, budget, and terminal condition.
- `POSSIBLE_RUNAWAY`: risk or continued activity exists, but the evidence is insufficient for confirmation.
- `CONFIRMED_RUNAWAY`: live identity, ownership, terminal expectation, continued objective activity, and the breach are all proven.
- `STALE_RECORD`: explicitly supplied or otherwise available historical state says running, but live runtime evidence is absent.
- `UNKNOWN`: live truth, ownership, expectation, or telemetry is insufficient.

A long duration alone is not runaway. A parent response returning is not proof that an allowed detached child should stop. Repeated `429`, `5xx`, timeout, or retry signals are risk evidence only; provider error alone cannot confirm runaway.

Missing token telemetry is unknown, not zero. The installed Hermes `session.usage` response may contain display zeroes when no usage is available; treat those as unproven unless the response includes verified provider-native usage provenance.

## Bounded Observation

Use one snapshot when `--observation-seconds 0`. Otherwise use exactly two snapshots separated by the requested bounded interval. Do not create a resident daemon, recursive poller, model call, or background watcher.

## Postflight

For an explicit expected-terminal scope:

1. identify the owned targets and their exact identities;
2. query live Gateway truth;
3. take a bounded second snapshot when activity comparison is needed;
4. verify every target is terminal or absent from the live set;
5. separate supplied historical evidence from live execution; do not claim a historical audit when none was acquired;
6. report unresolved or unknown targets.

Only a non-empty explicit scope with every target terminal can report `TERMINAL PROOF PASS`. Any unknown or still-live expected target reports `TERMINAL PROOF INCONCLUSIVE`.

## Security

Read credentials only through the installed Hermes secure environment/profile mechanism. Never accept a secret through a CLI argument, log raw process arguments, print `HERMES_DASHBOARD_SESSION_TOKEN`, API keys, OAuth tokens, authorization headers, `.env` contents, or query-string credential values. Diagnostics may state only `token=<redacted>` or `credential_present=true`.

Do not modify `config.yaml`, `.env`, active profiles, Serena configuration, MCP configuration, or Repomix configuration. Policy values in documentation are examples, not Hermes universal defaults. Inspect the installed version and current config before choosing any bounded policy.

## V1.1 Backlog, Not Implemented

The following are deliberately out of scope for V1:

```text
explicit --enforce
session.interrupt / session.close
subagent.interrupt
delegation.pause
exact target terminal confirmation beyond observation
continuous supervisor
runtime-level budget enforcement
```

Before V1.1, re-audit the installed Hermes contract. An interrupt request is not terminal confirmation. Never kill a shared Hermes backend, CCSwitch, Serena, Repomix, or an unrelated process.

## Verification

Run the repository's existing gates:

```bash
python scripts/validate_skills.py
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Then perform one read-only live shadow smoke against the installed Hermes version. Do not create work merely to test the detector. `NO LIVE TARGETS` is a valid result.
