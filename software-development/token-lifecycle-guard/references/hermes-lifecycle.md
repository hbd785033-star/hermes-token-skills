# Hermes Lifecycle Contract Reference

This reference records the locally audited contract used by V1 development. It is not a universal Hermes contract; re-check the installed source after upgrades.

## Verified Installation

The development audit used:

```text
Hermes Agent v0.20.4
Source: C:\Users\EDY\AppData\Local\hermes\hermes-agent
Profile/home: C:\Users\EDY\AppData\Local\hermes
```

The installed source registered these methods in `tui_gateway/methods_session.py`:

```text
session.active_list
session.status
session.usage
session.interrupt
session.close
delegation.status
delegation.pause
subagent.interrupt
```

V1 calls only `session.active_list`, `session.usage`, and `delegation.status`. `session.status` is part of the verified read-only allowlist for future normalized fields but is not required by the minimum smoke path.

## Live Versus Historical

`session.active_list` returns sessions from the current Gateway process's in-memory `_sessions` registry. It excludes finalized records and is the authoritative live session snapshot for that Gateway process.

`session.list` and persisted `state.db` rows are historical/session-store discovery. They can be useful for historical evidence, but a row with `running` state does not prove a runtime is executing now.

Use this precedence:

```text
live Gateway identity > process evidence > persisted history
```

If historical evidence was explicitly supplied or is otherwise available, a historical running row absent from the live set can be classified as `STALE_RECORD`, not live work. The V1 live transport does not call `session.list` or enumerate persisted history, so a live-only report cannot claim that all stale historical rows were checked.

## Session Method Semantics

`session.active_list` accepts an optional `current_session_id` and returns an object containing a `sessions` list. A row can contain a live session identifier, running/status information, and metadata. The exact optional fields are version-sensitive.

`session.usage` accepts the target session parameters and returns usage fields such as `calls`, `input`, `output`, and `total` when the current live agent exposes them. The current implementation can return display zeroes for a session without a live agent or usage snapshot. Do not treat those zeroes as provider-native proof. Normalize missing/unproven usage to `UNKNOWN` or `None`.

`session.status` returns formatted status text and includes a running indicator and token display. It is not a replacement for structured active-list or usage evidence.

## Delegation And Subagents

`delegation.status` returns:

```text
active
paused
max_spawn_depth
max_concurrent_children
```

The installed `list_active_subagents()` rows are live registry copies. The documented minimum row includes:

```text
subagent_id
parent_id
depth
goal
model
started_at
tool_count
status
```

The `agent` object and ownership transport internals are removed from the RPC projection. `parent_session_id` and `correlation_id` are not guaranteed in this response in v0.20.4. Therefore the watchdog must not promote `parent_id` or a guessed relationship to ownership proof unless the exact installed lifecycle identity contract verifies it for the current target.

Hermes's delegation source also keeps process-local active subagents separate from recently finished attribution records. Recent attribution is useful for reporting, not live execution proof.

The stable public subagent lifecycle API documents these states for its own handle-based service:

```text
PENDING, STARTING, RUNNING, SUCCEEDED, FAILED,
INTERRUPTED, CANCEL_REQUESTED, CANCELLED, UNKNOWN
```

That API is distinct from the TUI `delegation.status` projection. Do not merge the two schemas or assume a handle is reconnectable after process restart.

## Control Methods Are V1.1

The installed semantics are mutating:

- `session.interrupt` requests turn interruption and may clear stale running state.
- `session.close` tears down a live session.
- `delegation.pause` changes the process-global spawn pause flag.
- `subagent.interrupt` requests a live child interruption.

They are documented here only for future re-audit. V1's transport rejects them before any RPC call. V1 does not use `process.kill`, `prompt.submit`, `prompt.background`, `delegate_task`, or model/provider calls.

## Background Semantics

Synchronous `delegate_task` waits for a child summary. `delegate_task(background=true)` returns a delegation handle while the child runs in a process-local daemon executor; completion is later delivered through the shared completion queue. Child identity and parent ownership are separate from an ordinary session history row.

A background process started by a child can outlive the child summary. That fact does not itself make it runaway. An explicitly allowed detached child remains `LONG_RUNNING_EXPECTED` when owner, budget, and terminal condition are proven.

## Version Drift

Do not copy any `child_timeout_seconds` value into policy as a Hermes default. In the audited source, the current built-in delegation default is `child_timeout_seconds: 0`, meaning no wall-clock child timeout, while other releases may differ. Documentation policy examples must be labeled as local example policy, never as a universal Hermes default.

Required upgrade procedure:

```text
inspect installed Hermes version
inspect installed source and registered RPC methods
inspect current profile config
choose bounded policy intentionally
update normalized adapter and fixtures if semantics changed
```

## Gateway Transport And Secrets

The TUI Gateway stdio entrypoint emits a `gateway.ready` event and then accepts one JSON-RPC request per line. A read-only shadow smoke may launch this installed entrypoint as a separate process, consume readiness, query only allowlisted methods, and close stdin.

The V1 transport has one stdout reader thread, so the controlling thread never performs blocking pipe reads. The reader only feeds an internal queue; malformed, unrelated, or wrong-ID messages do not complete a wait or reset its monotonic deadline. After the exact child is terminal, cleanup joins the reader within a bounded interval and reports `CLEANUP INCONCLUSIVE` if terminal reader state cannot be proven.

Authentication and profile credentials must come from the installed Hermes secure environment/profile mechanism. Never add a `--token` option to the watchdog, never print raw environment contents, and never log a Gateway URL containing credential query parameters. Redact values and report only credential presence.
