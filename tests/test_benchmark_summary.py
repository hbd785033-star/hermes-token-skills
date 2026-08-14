import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CONDITIONS = {
    "fixture": "hermes-agent@1a04c72",
    "tools": ["search_files", "read_file"],
    "temperature": 0,
}


def make_run(**overrides):
    run = {
        "task_id": "known-symbol-01",
        "mode": "baseline",
        "model": "model-a",
        "tokenizer": "tok-a",
        "conditions": dict(CONDITIONS),
        "input_tokens": 1000,
        "output_tokens": 200,
        "tool_calls": 8,
        "files_read": 5,
        "success": True,
        "verification": "passed",
    }
    run.update(overrides)
    return run


class BenchmarkSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_run(self, name: str, run) -> Path:
        path = self.root / name
        path.write_text(json.dumps(run), encoding="utf-8")
        return path

    def run_summary(self, baseline: Path, optimized: Path) -> subprocess.CompletedProcess[str]:
        script = Path(__file__).parents[1] / "scripts" / "benchmark_summary.py"
        return subprocess.run(
            [sys.executable, str(script), str(baseline), str(optimized)],
            capture_output=True,
            text=True,
            check=False,
        )

    def run_pair(self, baseline_run, optimized_run) -> subprocess.CompletedProcess[str]:
        baseline = self.write_run("baseline.json", baseline_run)
        optimized = self.write_run("optimized.json", optimized_run)
        return self.run_summary(baseline, optimized)

    def test_valid_comparable_run_reports_delta(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", input_tokens=400, tool_calls=3, files_read=2),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Task: known-symbol-01", result.stdout)
        self.assertIn("-600 input tokens (-60.0%)", result.stdout)
        self.assertIn("Output tokens (base/opt): 200 / 200", result.stdout)
        self.assertIn("Tool calls (base/opt):  8 / 3", result.stdout)
        self.assertIn("Files read (base/opt):  5 / 2", result.stdout)
        self.assertNotIn("incomparable", result.stdout)

    def test_rejects_optimized_mode_in_baseline_file(self) -> None:
        result = self.run_pair(
            make_run(mode="optimized"),
            make_run(mode="optimized", input_tokens=400),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected mode 'baseline'", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_rejects_baseline_mode_in_optimized_file(self) -> None:
        result = self.run_pair(make_run(), make_run(input_tokens=400))
        self.assertEqual(result.returncode, 2)
        self.assertIn("expected mode 'optimized'", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_swapped_files_cannot_produce_percentage(self) -> None:
        result = self.run_pair(
            make_run(mode="optimized", input_tokens=400),
            make_run(),
        )
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("%", result.stdout)

    def test_rejects_duplicate_baseline_task_id(self) -> None:
        result = self.run_pair(
            [make_run(), make_run()],
            make_run(mode="optimized", input_tokens=400),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate task_id 'known-symbol-01'", result.stderr)

    def test_rejects_duplicate_optimized_task_id(self) -> None:
        result = self.run_pair(
            make_run(),
            [make_run(mode="optimized"), make_run(mode="optimized")],
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate task_id 'known-symbol-01'", result.stderr)

    def test_failed_optimized_task_is_never_a_saving(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", input_tokens=100, success=False, verification="failed"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)
        self.assertNotIn("-900", result.stdout)

    def test_failed_baseline_is_incomparable(self) -> None:
        result = self.run_pair(
            make_run(success=False, verification="failed"),
            make_run(mode="optimized", input_tokens=100),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("baseline task failed", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_model_mismatch_precedes_optimized_failure(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", model="model-b", success=False, verification="failed"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("model differs", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_conditions_mismatch_precedes_optimized_failure(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(
                mode="optimized",
                conditions=dict(CONDITIONS, temperature=1),
                success=False,
                verification="failed",
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("conditions differ", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_tokenizer_mismatch_precedes_optimized_failure(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", tokenizer="tok-b", success=False, verification="failed"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("tokenizer differs", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_baseline_failure_precedes_optimized_failure(self) -> None:
        result = self.run_pair(
            make_run(success=False, verification="failed"),
            make_run(mode="optimized", success=False, verification="failed"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("baseline task failed", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_comparable_optimized_failure_remains_failed_optimization(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", success=False, verification="failed"),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_mismatched_model_suppresses_savings_claim(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", model="model-b", input_tokens=400),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_mismatched_tokenizer_suppresses_savings_claim(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", tokenizer="tok-b", input_tokens=400),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_mismatched_conditions_is_incomparable(self) -> None:
        other_conditions = dict(CONDITIONS, temperature=1)
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", conditions=other_conditions, input_tokens=400),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("conditions differ", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_missing_conditions_is_invalid(self) -> None:
        bad_run = make_run(mode="optimized")
        del bad_run["conditions"]
        result = self.run_pair(make_run(), bad_run)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing required field 'conditions'", result.stderr)

    def test_empty_conditions_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(conditions={}),
            make_run(mode="optimized", input_tokens=400),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("'conditions' must be a non-empty JSON object", result.stderr)

    def test_missing_token_count_suppresses_savings_claim(self) -> None:
        optimized_run = make_run(mode="optimized")
        del optimized_run["input_tokens"]
        result = self.run_pair(make_run(), optimized_run)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_unpaired_task_is_incomparable(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", task_id="cross-file-01", input_tokens=400),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("missing optimized run", result.stdout)
        self.assertIn("missing baseline run", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_malformed_json_exits_nonzero(self) -> None:
        baseline = self.root / "baseline.json"
        baseline.write_text("{not json", encoding="utf-8")
        optimized = self.write_run("optimized.json", make_run(mode="optimized"))
        result = self.run_summary(baseline, optimized)
        self.assertEqual(result.returncode, 2)
        self.assertIn("malformed JSON", result.stderr)

    def test_missing_required_field_exits_nonzero(self) -> None:
        bad_run = make_run(mode="optimized")
        del bad_run["tokenizer"]
        result = self.run_pair(make_run(), bad_run)
        self.assertEqual(result.returncode, 2)
        self.assertIn("missing required field 'tokenizer'", result.stderr)

    def test_metric_lists_are_compared_per_task(self) -> None:
        baselines = [make_run(), make_run(task_id="handoff-01", input_tokens=500)]
        optimized = [
            make_run(mode="optimized", input_tokens=400),
            make_run(mode="optimized", task_id="handoff-01", input_tokens=500),
        ]
        result = self.run_pair(baselines, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Task: handoff-01", result.stdout)
        self.assertIn("+0 input tokens (+0.0%)", result.stdout)


if __name__ == "__main__":
    unittest.main()
