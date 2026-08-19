#!/usr/bin/env python3
"""Deterministic, read-only Hermes lifecycle observation and classification."""

from __future__ import annotations

import argparse
import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


CLASSIFICATION_STATES = frozenset(
    {
        "HEALTHY",
        "LONG_RUNNING_EXPECTED",
        "POSSIBLE_RUNAWAY",
        "CONFIRMED_RUNAWAY",
        "STALE_RECORD",
        "UNKNOWN",
    }
)

# V1 deliberately exposes only observation methods. Mutation methods are absent
# from this allowlist and are rejected again by ReadOnlyGatewayTransport.call.
READ_ONLY_METHODS = frozenset(
    {
        "session.active_list",
        "session.status",
        "session.usage",
        "delegation.status",
    }
)
MUTATION_METHODS = frozenset(
    {
        "session.interrupt",
        "session.close",
        "delegation.pause",
        "subagent.interrupt",
    }
)

_SECRET_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "client_secret",
}
_SECRET_QUERY_KEYS = {
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "authorization",
    "credential",
}


@dataclass(frozen=True)
class Classification:
    state: str
    reason: str
    evidence: dict[str, Any] = field(default_factory=dict)


class ReadOnlyGatewayTransport:
    """Small injectable boundary for Gateway calls; never performs mutation."""

    def __init__(self, caller: Callable[[str, Mapping[str, Any]], Mapping[str, Any]]):
        self._caller = caller

    def call(self, method: str, params: Mapping[str, Any] | None = None) -> Mapping[str, Any]:
        if method not in READ_ONLY_METHODS:
            raise ValueError(f"V1 read-only transport rejects method: {method}")
        return self._caller(method, params or {})


class StdioGatewayTransport(ReadOnlyGatewayTransport):
    """JSON-RPC client for a separately launched Hermes TUI Gateway process."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        startup_timeout: float = 30.0,
        response_timeout: float = 30.0,
        cleanup_timeout: float = 5.0,
    ):
        self.command = list(command)
        self.cwd = cwd
        self.env = dict(env or os.environ)
        self.startup_timeout = self._positive_timeout(startup_timeout, "startup_timeout")
        self.response_timeout = self._positive_timeout(response_timeout, "response_timeout")
        self.cleanup_timeout = self._positive_timeout(cleanup_timeout, "cleanup_timeout")
        self.stderr_policy = "discard"
        self._next_id = 1
        self._process: subprocess.Popen[str] | None = None
        self._stdout_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._stdout_reader: threading.Thread | None = None
        self._close_lock = threading.Lock()
        super().__init__(self._call)

    @staticmethod
    def _positive_timeout(value: float, name: str) -> float:
        value = float(value)
        if value <= 0:
            raise ValueError(f"{name} must be positive")
        return value

    @property
    def process(self) -> subprocess.Popen[str] | None:
        """Exact helper owned by this transport; retained through cleanup proof."""
        return self._process

    def start(self) -> None:
        if self._process is not None:
            return
        self._process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            env=self.env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            # Raw Gateway stderr can contain credentials or environment metadata.
            # Discarding it also removes the undrained-pipe saturation deadlock.
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        self._stdout_reader = threading.Thread(
            target=self._read_stdout,
            daemon=True,
            name=f"lifecycle-gateway-stdout-{self._process.pid}",
        )
        self._stdout_reader.start()
        try:
            # The Gateway emits an event before handling requests. Consume it
            # without logging payloads, because event payloads can contain metadata.
            self._read_until_ready()
        except BaseException:
            self.close()
            raise

    def _read_stdout(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._stdout_queue.put(("error", RuntimeError("Gateway stdout is unavailable")))
            return
        try:
            for line in process.stdout:
                self._stdout_queue.put(("line", line))
        except BaseException as exc:
            self._stdout_queue.put(("error", exc))
        finally:
            self._stdout_queue.put(("eof", None))

    def _next_message(self, deadline: float, operation: str) -> Mapping[str, Any]:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"timed out waiting for Hermes Gateway {operation}")
        try:
            kind, payload = self._stdout_queue.get(timeout=remaining)
        except queue.Empty as exc:
            raise TimeoutError(f"timed out waiting for Hermes Gateway {operation}") from exc
        if kind == "error":
            raise RuntimeError(f"Hermes Gateway stdout reader failed during {operation}")
        if kind == "eof":
            raise RuntimeError(f"Hermes Gateway exited during {operation}")
        try:
            message = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return {}
        return message if isinstance(message, Mapping) else {}

    def _read_until_ready(self) -> None:
        deadline = time.monotonic() + self.startup_timeout
        while True:
            message = self._next_message(deadline, "readiness")
            if message.get("method") == "event":
                params = message.get("params") or {}
                if params.get("type") == "gateway.ready":
                    return
            elif "id" in message:
                return

    def _call(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        self.start()
        assert self._process is not None
        if self._process.stdin is None:
            raise RuntimeError("Gateway stdio is unavailable")
        request_id = self._next_id
        self._next_id += 1
        self._process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)}) + "\n")
        self._process.stdin.flush()
        deadline = time.monotonic() + self.response_timeout
        while True:
            response = self._next_message(deadline, f"response for {method}")
            if response.get("id") == request_id:
                if "error" in response:
                    raise RuntimeError(str(redact(response["error"])))
                return response.get("result") or {}

    def close(self) -> None:
        with self._close_lock:
            process = self._process
            if process is None or process.poll() is not None:
                return
            if process.stdin is not None and not process.stdin.closed:
                process.stdin.close()
            try:
                process.wait(timeout=self.cleanup_timeout)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=self.cleanup_timeout)
                except subprocess.TimeoutExpired:
                    process.kill()
                    try:
                        process.wait(timeout=self.cleanup_timeout)
                    except subprocess.TimeoutExpired as exc:
                        raise RuntimeError(
                            f"CLEANUP INCONCLUSIVE: exact owned child pid={process.pid} remains live"
                        ) from exc
            if process.poll() is None:
                raise RuntimeError(
                    f"CLEANUP INCONCLUSIVE: exact owned child pid={process.pid} remains live"
                )


def provider_call(*_args: Any, **_kwargs: Any) -> None:
    """Sentinel proving this detector has no provider/LLM call path."""
    raise RuntimeError("provider calls are outside token-lifecycle-guard V1")


def _secret_marker(value: Any = None) -> dict[str, Any]:
    return {"redacted": True, "credential_present": value not in (None, "")}


def _redact_url(value: str) -> str:
    try:
        parts = urlsplit(value)
    except ValueError:
        return "<redacted-url>"
    if not parts.scheme or not parts.netloc:
        return value
    query = []
    credential_present = False
    for key, item in parse_qsl(parts.query, keep_blank_values=True):
        if key.lower() in _SECRET_QUERY_KEYS:
            credential_present = credential_present or bool(item)
            query.append((key, "<redacted>"))
        else:
            query.append((key, item))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def redact(value: Any, *, _key: str = "") -> Any:
    """Recursively redact credentials without exposing their values."""
    key = _key.lower().replace("-", "_")
    if key in _SECRET_KEYS or any(part in key for part in ("token", "secret", "credential")):
        return _secret_marker(value)
    if isinstance(value, Mapping):
        return {str(k): redact(v, _key=str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return [redact(item) for item in value]
    if isinstance(value, str) and (value.startswith("http://") or value.startswith("https://")):
        return _redact_url(value)
    return value


def target_key(target: Mapping[str, Any]) -> tuple[str, str]:
    return (str(target.get("kind") or "UNKNOWN"), str(target.get("identity") or ""))


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _activity_delta(after: Mapping[str, Any], before: Mapping[str, Any] | None) -> dict[str, Any]:
    if before is None:
        return {"proven": False, "fields": {}}
    after_activity = after.get("activity") if isinstance(after.get("activity"), Mapping) else {}
    before_activity = before.get("activity") if isinstance(before.get("activity"), Mapping) else {}
    fields: dict[str, Any] = {}
    proven = False
    for name in ("api_attempts", "tool_calls", "usage_total", "provider_retries"):
        current = _numeric(after_activity.get(name))
        previous = _numeric(before_activity.get(name))
        if current is None or previous is None:
            fields[name] = None
        else:
            delta = current - previous
            fields[name] = int(delta) if delta.is_integer() else delta
            if delta > 0 and name != "provider_retries":
                proven = True
    return {"proven": proven, "fields": fields}


def _usage_delta(after: Mapping[str, Any], before: Mapping[str, Any] | None) -> int | None:
    if before is None:
        return None
    after_telemetry = after.get("telemetry") if isinstance(after.get("telemetry"), Mapping) else {}
    before_telemetry = before.get("telemetry") if isinstance(before.get("telemetry"), Mapping) else {}
    if not after_telemetry.get("usage_known") or not before_telemetry.get("usage_known"):
        return None
    after_value = _numeric(after_telemetry.get("input_tokens"))
    before_value = _numeric(before_telemetry.get("input_tokens"))
    if after_value is None or before_value is None:
        return None
    return int(after_value - before_value)


def classify(after: Mapping[str, Any], before: Mapping[str, Any] | None = None) -> Classification:
    """Classify normalized evidence conservatively and deterministically."""
    live = bool(after.get("live"))
    historical = bool(after.get("historical"))
    if historical and not live:
        return Classification("STALE_RECORD", "historical state has no live runtime evidence")
    if not live:
        return Classification("UNKNOWN", "target liveness is not proven")

    ownership = after.get("ownership", "UNKNOWN")
    expected_terminal = bool(after.get("expected_terminal"))
    allowed_continue = bool(after.get("allowed_continue"))
    budget_proven = bool(after.get("budget_proven"))
    condition_proven = bool(after.get("terminal_condition_proven"))
    delta = _activity_delta(after, before)
    usage_delta = _usage_delta(after, before)
    telemetry = after.get("telemetry") if isinstance(after.get("telemetry"), Mapping) else {}
    usage_known = telemetry.get("usage_known") is True
    retries = _numeric((after.get("activity") or {}).get("provider_retries")) if isinstance(after.get("activity"), Mapping) else None
    provider_errors = telemetry.get("provider_errors")
    retry_signal = bool(retries and retries > 0) or bool(provider_errors)

    evidence = {
        "target": target_key(after),
        "ownership": ownership,
        "expected_terminal": expected_terminal,
        "activity_delta": delta,
        "input_token_delta": usage_delta,
        "usage_known": usage_known,
        "retry_signal": retry_signal,
    }

    if allowed_continue and ownership == "PROVEN" and budget_proven and condition_proven:
        return Classification("LONG_RUNNING_EXPECTED", "explicitly allowed live work has owner, budget, and terminal condition", evidence)
    if not usage_known and not retry_signal:
        return Classification("UNKNOWN", "live target lacks provider-native usage telemetry", evidence)
    if not expected_terminal:
        if retry_signal and not usage_known:
            return Classification("POSSIBLE_RUNAWAY", "provider retry/error activity is a risk signal without terminal breach proof", evidence)
        return Classification("HEALTHY", "live work has no explicit terminal expectation breach", evidence)
    if before is None:
        return Classification("UNKNOWN", "terminal expectation exists but bounded activity comparison is absent", evidence)
    if not delta["proven"] and usage_delta is not None and usage_delta > 0:
        delta["proven"] = True
    if ownership != "PROVEN":
        if delta["proven"] or retry_signal:
            return Classification("POSSIBLE_RUNAWAY", "activity exists but ownership is not proven", evidence)
        return Classification("UNKNOWN", "ownership and objective activity are insufficient", evidence)
    if not delta["proven"]:
        if retry_signal:
            return Classification("POSSIBLE_RUNAWAY", "retry/error activity alone cannot confirm runaway", evidence)
        return Classification("UNKNOWN", "continued objective activity is not proven", evidence)
    return Classification("CONFIRMED_RUNAWAY", "live owned target breached an explicit terminal expectation and progressed", evidence)


def terminal_proof(targets: Sequence[Mapping[str, Any]]) -> str:
    """Return PASS only when a non-empty explicit expected-terminal scope is done."""
    if not targets:
        return "TERMINAL PROOF INCONCLUSIVE"
    for target in targets:
        if not target.get("expected_terminal"):
            return "TERMINAL PROOF INCONCLUSIVE"
        if target.get("live"):
            return "TERMINAL PROOF INCONCLUSIVE"
        if str(target.get("state") or "").lower() not in {"completed", "succeeded", "failed", "cancelled", "interrupted", "absent", "closed"}:
            return "TERMINAL PROOF INCONCLUSIVE"
    return "TERMINAL PROOF PASS"


def observe(snapshot: Callable[[], Mapping[str, Any]], observation_seconds: float) -> tuple[Mapping[str, Any], Mapping[str, Any] | None]:
    """Take one snapshot or two snapshots separated by one bounded sleep."""
    if observation_seconds < 0:
        raise ValueError("observation_seconds must be non-negative")
    before = snapshot()
    if observation_seconds == 0:
        return before, None
    time.sleep(observation_seconds)
    return before, snapshot()


def _normalize_session(row: Mapping[str, Any], *, historical: bool = False) -> dict[str, Any]:
    identity = row.get("session_id") or row.get("id") or row.get("session_key") or ""
    state = str(row.get("state") or row.get("status") or ("running" if row.get("running") else "idle"))
    return {
        "kind": "SESSION",
        "identity": str(identity),
        "state": state,
        "live": True,
        "ownership": "UNKNOWN",
        "expected_terminal": False,
        "allowed_continue": False,
        "budget_proven": False,
        "terminal_condition_proven": False,
        "activity": {"api_attempts": row.get("api_calls"), "tool_calls": row.get("tool_count")},
        "telemetry": {"usage_known": False},
        "historical": historical,
    }


def _normalize_subagent(row: Mapping[str, Any]) -> dict[str, Any]:
    parent = row.get("parent_session_id")
    ownership = "PROVEN" if parent else "UNKNOWN"
    return {
        "kind": "SUBAGENT",
        "identity": str(row.get("subagent_id") or ""),
        "state": str(row.get("state") or row.get("status") or "unknown"),
        "live": True,
        "ownership": ownership,
        "parent_session_id": parent,
        "correlation_id": row.get("correlation_id"),
        "role": row.get("role"),
        "depth": row.get("depth"),
        "expected_terminal": False,
        "allowed_continue": False,
        "budget_proven": False,
        "terminal_condition_proven": False,
        "activity": {"api_attempts": row.get("api_calls"), "tool_calls": row.get("tool_count")},
        "telemetry": {"usage_known": False},
        "historical": False,
    }


def normalize_snapshot(
    active_sessions: Sequence[Mapping[str, Any]] | None = None,
    delegation: Mapping[str, Any] | None = None,
    usage_by_session: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Normalize the small subset of live Gateway data the classifier needs."""
    usage_by_session = usage_by_session or {}
    targets: list[dict[str, Any]] = []
    for row in active_sessions or []:
        target = _normalize_session(row)
        usage = usage_by_session.get(target["identity"], {})
        if isinstance(usage, Mapping) and usage:
            usage_provenance = usage.get("usage_source") or usage.get("token_source")
            target["telemetry"] = {
                "usage_known": bool(usage.get("usage_known") is True or usage_provenance),
                "input_tokens": usage.get("input"),
                "output_tokens": usage.get("output"),
                "total_tokens": usage.get("total"),
                "usage_source": usage_provenance,
            }
            target["activity"]["api_attempts"] = usage.get("calls")
        targets.append(target)
    if delegation and isinstance(delegation.get("active"), Sequence):
        targets.extend(_normalize_subagent(row) for row in delegation["active"] if isinstance(row, Mapping))
    return {"targets": targets}


def _fixture_snapshot(payload: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    before = payload.get("before")
    after = payload.get("after")
    if not isinstance(after, Mapping):
        raise ValueError("snapshot fixture requires an 'after' object")
    return dict(before) if isinstance(before, Mapping) else {}, dict(after)


def _classify_snapshot(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, Any]:
    previous = {target_key(item): item for item in before.get("targets", []) if isinstance(item, Mapping)}
    results = []
    for target in after.get("targets", []):
        if not isinstance(target, Mapping):
            continue
        results.append({
            "target": target_key(target),
            "classification": classify(target, previous.get(target_key(target))).__dict__,
        })
    return {"targets": results, "terminal_proof": terminal_proof(after.get("expected_terminal_targets", []))}


def _default_command() -> list[str]:
    raw = os.environ.get("HERMES_GATEWAY_COMMAND", "").strip()
    if not raw:
        raise RuntimeError("live mode requires HERMES_GATEWAY_COMMAND; use the installed Hermes Gateway command")
    return shlex.split(raw, posix=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-json", help="deterministic fixture JSON; no Gateway is contacted")
    parser.add_argument("--observation-seconds", type=float, default=0.0)
    parser.add_argument("--gateway-command", help="installed Hermes TUI Gateway command, passed as argv")
    args = parser.parse_args(argv)

    transport: StdioGatewayTransport | None = None
    try:
        if args.snapshot_json:
            before, after = _fixture_snapshot(json.loads(args.snapshot_json))
        else:
            command = shlex.split(args.gateway_command, posix=False) if args.gateway_command else _default_command()
            transport = StdioGatewayTransport(command)
            transport.start()

            def snapshot() -> Mapping[str, Any]:
                active = transport.call("session.active_list", {}).get("sessions", [])
                delegation = transport.call("delegation.status", {})
                usage: dict[str, Mapping[str, Any]] = {}
                for row in active:
                    sid = row.get("id") or row.get("session_id") or row.get("session_key")
                    if sid:
                        usage[str(sid)] = transport.call("session.usage", {"session_id": sid})
                return normalize_snapshot(active, delegation, usage)

            before_raw, after_raw = observe(snapshot, args.observation_seconds)
            before = before_raw
            after = after_raw if after_raw is not None else before_raw
        result = _classify_snapshot(before, after)
        print(json.dumps(redact(result), sort_keys=True))
        if not result["targets"]:
            print("NO LIVE TARGETS")
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(redact(str(exc)))}, sort_keys=True), file=sys.stderr)
        return 2
    finally:
        if transport is not None:
            transport.close()


if __name__ == "__main__":
    raise SystemExit(main())
