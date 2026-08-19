import importlib.util
import io
import json
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "token_lifecycle_watch.py"
SPEC = importlib.util.spec_from_file_location("token_lifecycle_watch", SCRIPT)
watch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["token_lifecycle_watch"] = watch
SPEC.loader.exec_module(watch)


class TokenLifecycleWatchTests(unittest.TestCase):
    def target(self, **overrides):
        value = {
            "kind": "SESSION",
            "identity": "session-1",
            "state": "running",
            "live": True,
            "ownership": "PROVEN",
            "expected_terminal": False,
            "allowed_continue": False,
            "budget_proven": False,
            "terminal_condition_proven": False,
            "activity": {"api_attempts": 1, "tool_calls": 1, "usage_total": 10},
            "telemetry": {"usage_known": True},
            "historical": False,
        }
        value.update(overrides)
        return value

    def test_normal_active_owned_session_without_terminal_expectation_is_healthy(self):
        result = watch.classify(self.target())
        self.assertEqual(result.state, "HEALTHY")

    def test_legitimate_detached_child_is_long_running_expected(self):
        result = watch.classify(
            self.target(
                kind="SUBAGENT",
                identity="subagent-1",
                allowed_continue=True,
                budget_proven=True,
                terminal_condition_proven=True,
            )
        )
        self.assertEqual(result.state, "LONG_RUNNING_EXPECTED")

    def test_historical_running_row_without_live_target_is_stale_record(self):
        result = watch.classify(
            self.target(live=False, historical=True, state="running")
        )
        self.assertEqual(result.state, "STALE_RECORD")

    def test_owned_live_child_breaching_terminal_expectation_and_progress_is_confirmed(self):
        before = self.target(
            kind="SUBAGENT",
            identity="subagent-1",
            expected_terminal=True,
            activity={"api_attempts": 2, "tool_calls": 3, "usage_total": 20},
        )
        after = self.target(
            kind="SUBAGENT",
            identity="subagent-1",
            expected_terminal=True,
            activity={"api_attempts": 3, "tool_calls": 4, "usage_total": 30},
        )
        result = watch.classify(after, before)
        self.assertEqual(result.state, "CONFIRMED_RUNAWAY")

    def test_ambiguous_ownership_can_be_possible_but_never_confirmed(self):
        before = self.target(
            kind="SUBAGENT",
            identity="subagent-1",
            ownership="UNKNOWN",
            expected_terminal=True,
            activity={"api_attempts": 1, "tool_calls": 1},
        )
        after = self.target(
            kind="SUBAGENT",
            identity="subagent-1",
            ownership="UNKNOWN",
            expected_terminal=True,
            activity={"api_attempts": 2, "tool_calls": 2},
        )
        result = watch.classify(after, before)
        self.assertIn(result.state, {"POSSIBLE_RUNAWAY", "UNKNOWN"})
        self.assertNotEqual(result.state, "CONFIRMED_RUNAWAY")

    def test_parent_return_does_not_make_allowed_background_child_runaway(self):
        result = watch.classify(
            self.target(
                kind="SUBAGENT",
                identity="subagent-1",
                allowed_continue=True,
                budget_proven=True,
                terminal_condition_proven=True,
                parent_returned=True,
            )
        )
        self.assertEqual(result.state, "LONG_RUNNING_EXPECTED")

    def test_repeated_429_only_is_not_confirmed_runaway(self):
        before = self.target(
            expected_terminal=False,
            activity={"provider_retries": 2},
            telemetry={"usage_known": False, "provider_errors": [429, 429]},
        )
        after = self.target(
            expected_terminal=False,
            activity={"provider_retries": 4},
            telemetry={"usage_known": False, "provider_errors": [429, 429, 429, 429]},
        )
        result = watch.classify(after, before)
        self.assertNotEqual(result.state, "CONFIRMED_RUNAWAY")
        self.assertIn(result.state, {"POSSIBLE_RUNAWAY", "UNKNOWN"})

    def test_missing_usage_is_unknown_not_zero(self):
        result = watch.classify(
            self.target(
                activity={"api_attempts": 1},
                telemetry={"usage_known": False},
            )
        )
        self.assertEqual(result.state, "UNKNOWN")
        self.assertIsNone(result.evidence.get("input_token_delta"))
        self.assertNotEqual(result.evidence.get("input_token_delta"), 0)

    def test_single_snapshot_is_conservative_for_terminal_target(self):
        result = watch.classify(self.target(expected_terminal=True))
        self.assertEqual(result.state, "UNKNOWN")

    def test_session_and_subagent_identity_kinds_do_not_collide(self):
        session_key = watch.target_key(self.target(kind="SESSION", identity="same"))
        child_key = watch.target_key(self.target(kind="SUBAGENT", identity="same"))
        self.assertNotEqual(session_key, child_key)
        self.assertEqual(session_key[0], "SESSION")
        self.assertEqual(child_key[0], "SUBAGENT")

    def test_history_never_overrides_live_active_truth(self):
        result = watch.classify(
            self.target(live=True, state="running", historical=True)
        )
        self.assertNotEqual(result.state, "STALE_RECORD")

    def test_normalizer_keeps_historical_rows_out_of_live_target_set(self):
        snapshot = watch.normalize_snapshot(
            active_sessions=[{"id": "live-1", "running": True}],
            delegation={"active": []},
        )
        self.assertEqual([item["identity"] for item in snapshot["targets"]], ["live-1"])
        self.assertTrue(snapshot["targets"][0]["live"])

    def test_normalizer_preserves_session_and_subagent_kinds(self):
        snapshot = watch.normalize_snapshot(
            active_sessions=[{"id": "same", "running": True}],
            delegation={"active": [{"subagent_id": "same", "parent_id": "parent"}]},
        )
        self.assertEqual(
            {watch.target_key(item) for item in snapshot["targets"]},
            {("SESSION", "same"), ("SUBAGENT", "same")},
        )

    def test_generic_parent_id_does_not_prove_parent_session_ownership(self):
        snapshot = watch.normalize_snapshot(
            delegation={"active": [{"subagent_id": "child", "parent_id": "parent"}]},
        )
        self.assertEqual(snapshot["targets"][0]["ownership"], "UNKNOWN")

    def test_missing_usage_fields_are_not_invented_as_zero(self):
        snapshot = watch.normalize_snapshot(
            active_sessions=[{"id": "live-1", "running": True}],
            usage_by_session={"live-1": {"calls": 1}},
        )
        telemetry = snapshot["targets"][0]["telemetry"]
        self.assertFalse(telemetry["usage_known"])
        self.assertIsNone(telemetry["input_tokens"])

    def test_display_zero_usage_without_provenance_is_unknown(self):
        snapshot = watch.normalize_snapshot(
            active_sessions=[{"id": "live-1", "running": True}],
            usage_by_session={"live-1": {"calls": 0, "input": 0, "output": 0, "total": 0}},
        )
        self.assertFalse(snapshot["targets"][0]["telemetry"]["usage_known"])

    def test_long_duration_without_terminal_expectation_cannot_confirm_runaway(self):
        result = watch.classify(
            self.target(age_seconds=999999, expected_terminal=False)
        )
        self.assertNotEqual(result.state, "CONFIRMED_RUNAWAY")
        self.assertEqual(result.state, "HEALTHY")

    def test_terminal_proof_requires_explicit_expected_targets(self):
        self.assertEqual(
            watch.terminal_proof([]), "TERMINAL PROOF INCONCLUSIVE"
        )
        self.assertEqual(
            watch.terminal_proof(
                [self.target(live=False, expected_terminal=True, state="completed")]
            ),
            "TERMINAL PROOF PASS",
        )
        self.assertEqual(
            watch.terminal_proof(
                [self.target(live=True, expected_terminal=True)]
            ),
            "TERMINAL PROOF INCONCLUSIVE",
        )

    def test_default_transport_is_read_only_and_has_no_mutation_methods(self):
        self.assertEqual(
            watch.READ_ONLY_METHODS,
            {
                "session.active_list",
                "session.status",
                "session.usage",
                "delegation.status",
            },
        )
        forbidden = {
            "session.interrupt",
            "session.close",
            "delegation.pause",
            "subagent.interrupt",
        }
        self.assertTrue(forbidden.isdisjoint(watch.READ_ONLY_METHODS))
        transport = watch.ReadOnlyGatewayTransport(lambda method, params: {"method": method})
        with self.assertRaises(ValueError):
            transport.call("session.interrupt", {})
        self.assertEqual(
            transport.call("session.active_list", {})["method"],
            "session.active_list",
        )

    def test_redaction_removes_secret_values_and_query_credentials(self):
        payload = {
            "token": "secret-value",
            "Authorization": "Bearer secret-header",
            "url": "http://localhost:1/live?token=secret-query&x=1",
            "nested": {"api_key": "secret-key"},
        }
        redacted = watch.redact(payload)
        text = json.dumps(redacted)
        self.assertNotIn("secret-value", text)
        self.assertNotIn("secret-header", text)
        self.assertNotIn("secret-query", text)
        self.assertNotIn("secret-key", text)
        self.assertIn("credential_present", text)

    def test_observation_is_bounded_and_zero_is_single_snapshot(self):
        calls = []

        def snapshot():
            calls.append(time.monotonic())
            return {"targets": []}

        with patch.object(watch.time, "sleep", side_effect=lambda seconds: calls.append(seconds)):
            result = watch.observe(snapshot, 0)
        self.assertEqual(result, ({"targets": []}, None))
        self.assertEqual(len(calls), 1)

        calls.clear()
        with patch.object(watch.time, "sleep", side_effect=lambda seconds: calls.append(seconds)):
            result = watch.observe(snapshot, 0.25)
        self.assertEqual(result[0], {"targets": []})
        self.assertEqual(result[1], {"targets": []})
        self.assertEqual(calls[1], 0.25)

    def test_detector_does_not_call_llm_or_provider(self):
        with patch.object(watch, "provider_call", side_effect=AssertionError):
            result = watch.classify(self.target())
        self.assertEqual(result.state, "HEALTHY")

    def test_cli_fixture_mode_reports_classification_without_network(self):
        fixture = {
            "before": {"targets": []},
            "after": {"targets": [self.target()]},
        }
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--snapshot-json", json.dumps(fixture)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("HEALTHY", completed.stdout)
        self.assertNotIn("secret", completed.stdout.lower())

    def test_token_efficiency_skill_remains_unchanged(self):
        original = subprocess.check_output(
            ["git", "show", "HEAD:software-development/token-efficiency/SKILL.md"],
            cwd=ROOT,
            text=True,
        )
        current = (ROOT / "software-development" / "token-efficiency" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertEqual(original, current)


if __name__ == "__main__":
    unittest.main()
