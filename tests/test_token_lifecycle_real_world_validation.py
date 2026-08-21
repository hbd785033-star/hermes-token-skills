import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "token_lifecycle_watch.py"
SPEC = importlib.util.spec_from_file_location("token_lifecycle_watch_validation", SCRIPT)
watch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules["token_lifecycle_watch_validation"] = watch
SPEC.loader.exec_module(watch)


class TokenLifecycleRealWorldValidationTests(unittest.TestCase):
    def target(self, **overrides):
        value = {
            "kind": "SESSION",
            "identity": "validation-session",
            "state": "running",
            "live": True,
            "ownership": "PROVEN",
            "expected_terminal": False,
            "allowed_continue": False,
            "budget_proven": False,
            "terminal_condition_proven": False,
            "activity": {"api_attempts": 1, "tool_calls": 1, "usage_total": 10},
            "telemetry": {"usage_known": True, "input_tokens": 10},
            "historical": False,
        }
        value.update(overrides)
        return value

    def test_case_1_normal_short_terminal_task(self):
        terminal_target = self.target(
            state="completed",
            live=False,
            expected_terminal=True,
        )

        classification = watch.classify(terminal_target)

        self.assertNotEqual(classification.state, "CONFIRMED_RUNAWAY")
        self.assertEqual(
            watch.terminal_proof([terminal_target]),
            "TERMINAL PROOF PASS",
        )

    def test_case_2_legitimate_long_running_task(self):
        before = self.target(
            age_seconds=7_200,
            activity={"api_attempts": 10, "tool_calls": 20, "usage_total": 100},
            telemetry={"usage_known": True, "input_tokens": 100},
        )
        after = self.target(
            age_seconds=10_800,
            activity={"api_attempts": 11, "tool_calls": 23, "usage_total": 115},
            telemetry={"usage_known": True, "input_tokens": 115},
        )

        classification = watch.classify(after, before)

        self.assertEqual(classification.state, "HEALTHY")
        self.assertNotEqual(classification.state, "CONFIRMED_RUNAWAY")

    def test_case_3_insufficient_evidence(self):
        incomplete_target = self.target(
            identity="",
            ownership="UNKNOWN",
            activity={"tool_calls": 2},
            telemetry={"usage_known": False},
        )

        classification = watch.classify(incomplete_target)

        self.assertEqual(classification.state, "UNKNOWN")
        self.assertFalse(classification.evidence["expected_terminal"])
        self.assertNotEqual(classification.state, "CONFIRMED_RUNAWAY")

    def test_case_4_expected_terminal_but_still_active(self):
        before = self.target(
            identity="expected-terminal-session",
            expected_terminal=True,
            activity={"api_attempts": 4, "tool_calls": 8, "usage_total": 80},
            telemetry={"usage_known": True, "input_tokens": 80},
        )
        after = self.target(
            identity="expected-terminal-session",
            expected_terminal=True,
            activity={"api_attempts": 5, "tool_calls": 10, "usage_total": 95},
            telemetry={"usage_known": True, "input_tokens": 95},
        )

        classification = watch.classify(after, before)

        self.assertEqual(classification.state, "CONFIRMED_RUNAWAY")
        self.assertTrue(classification.evidence["expected_terminal"])
        self.assertTrue(classification.evidence["activity_delta"]["proven"])

    def test_case_5_browser_failure_retry_waste_interpretations(self):
        interpretations = (
            ("5A-no-terminal-policy", False, "POSSIBLE_RUNAWAY"),
            ("5B-explicit-terminal-policy", True, "CONFIRMED_RUNAWAY"),
        )

        for name, expected_terminal, expected_state in interpretations:
            with self.subTest(interpretation=name):
                before = self.target(
                    identity="browser-workflow",
                    expected_terminal=expected_terminal,
                    activity={"api_attempts": 1, "tool_calls": 1, "provider_retries": 0},
                    telemetry={
                        "usage_known": False,
                        "provider_errors": ["pydantic_core import/ABI incompatibility"],
                    },
                )
                after = self.target(
                    identity="browser-workflow",
                    expected_terminal=expected_terminal,
                    activity={"api_attempts": 2, "tool_calls": 4, "provider_retries": 1},
                    telemetry={
                        "usage_known": False,
                        "provider_errors": ["pydantic_core import/ABI incompatibility"],
                    },
                )

                classification = watch.classify(after, before)

                self.assertEqual(classification.state, expected_state)
                self.assertEqual(
                    classification.evidence["expected_terminal"],
                    expected_terminal,
                )
                if not expected_terminal:
                    self.assertNotEqual(classification.state, "CONFIRMED_RUNAWAY")


if __name__ == "__main__":
    unittest.main()
