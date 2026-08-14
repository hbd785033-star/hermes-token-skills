import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "benchmark_summary.py"
SPEC = importlib.util.spec_from_file_location("benchmark_summary", SCRIPT)
benchmark_summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(benchmark_summary)


CONDITIONS = {
    "fixture": "hermes-agent@1a04c72",
    "provider": "provider-a",
    "hermes_version": "0.20.0",
    "tools": ["search_files", "read_file"],
    "temperature": 0,
    "session_type": "fresh-isolated",
}

PASSED_VERIFICATION = {"status": "passed", "evidence": ["task checks passed"]}
FAILED_VERIFICATION = {"status": "failed", "evidence": ["task checks failed"]}

RUNNABLE_TASK = {
    "id": "known-symbol-01",
    "revision": 1,
    "category": "known-symbol",
    "goal": "Locate and explain a known symbol with minimum context.",
    "prompt": "Locate Example.symbol and explain it with cited evidence.",
    "required_evidence": ["definition path and line"],
    "verification": ["answer identifies the symbol definition"],
}
RUNNABLE_TASKS = {
    task["id"]: task
    for task in (
        RUNNABLE_TASK,
        dict(
            RUNNABLE_TASK,
            id="cross-file-01",
            category="cross-file",
            goal="Trace a cross-file call edge.",
            prompt="Trace Example.call across files with cited evidence.",
        ),
        dict(
            RUNNABLE_TASK,
            id="handoff-01",
            category="handoff",
            goal="Produce a verifiable handoff.",
            prompt="Produce a handoff with cited state evidence.",
        ),
    )
}


def make_run(**overrides):
    task_id = overrides.get("task_id", RUNNABLE_TASK["id"])
    task = RUNNABLE_TASKS.get(task_id, RUNNABLE_TASK)
    run = {
        "task_id": task_id,
        "task_revision": task["revision"],
        "task_prompt": task["prompt"],
        "task_spec_sha256": benchmark_summary.task_spec_sha256(task),
        "trial_id": "t1",
        "pair_order": "baseline-first",
        "mode": "baseline",
        "model": "model-a",
        "tokenizer": "tok-a",
        "token_source": "provider_usage",
        "conditions": dict(CONDITIONS),
        "input_tokens": 1000,
        "output_tokens": 200,
        "tool_calls": 8,
        "files_read": 5,
        "success": True,
        "verification": dict(PASSED_VERIFICATION),
    }
    run.update(overrides)
    return run


class BenchmarkSummaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.tasks_path = self.write_run(
            "tasks.json",
            {
                "version": 1,
                "description": "test registry",
                "categories": ["known-symbol", "cross-file", "handoff"],
                "tasks": [dict(task) for task in RUNNABLE_TASKS.values()],
            },
        )

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def write_run(self, name: str, run) -> Path:
        path = self.root / name
        path.write_text(json.dumps(run), encoding="utf-8")
        return path

    def write_registry(self, tasks) -> None:
        self.tasks_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "description": "test registry",
                    "categories": sorted({task["category"] for task in tasks}),
                    "tasks": tasks,
                }
            ),
            encoding="utf-8",
        )

    def run_summary(self, baseline: Path, optimized: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--tasks",
                str(self.tasks_path),
                str(baseline),
                str(optimized),
            ],
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
            make_run(mode="optimized", input_tokens=100, success=False, verification=FAILED_VERIFICATION),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)
        self.assertNotIn("-900", result.stdout)

    def test_failed_baseline_is_incomparable(self) -> None:
        result = self.run_pair(
            make_run(success=False, verification=FAILED_VERIFICATION),
            make_run(mode="optimized", input_tokens=100),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("baseline task failed", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_model_mismatch_precedes_optimized_failure(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", model="model-b", success=False, verification=FAILED_VERIFICATION),
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
                verification=FAILED_VERIFICATION,
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
            make_run(mode="optimized", tokenizer="tok-b", success=False, verification=FAILED_VERIFICATION),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("tokenizer differs", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_baseline_failure_precedes_optimized_failure(self) -> None:
        result = self.run_pair(
            make_run(success=False, verification=FAILED_VERIFICATION),
            make_run(mode="optimized", success=False, verification=FAILED_VERIFICATION),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertIn("baseline task failed", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_comparable_optimized_failure_remains_failed_optimization(self) -> None:
        result = self.run_pair(
            make_run(),
            make_run(mode="optimized", success=False, verification=FAILED_VERIFICATION),
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

    def test_same_task_different_trial_id_is_allowed(self) -> None:
        baselines = [make_run(), make_run(trial_id="t2", pair_order="optimized-first")]
        optimized = [
            make_run(mode="optimized", input_tokens=700),
            make_run(mode="optimized", trial_id="t2", pair_order="optimized-first", input_tokens=800),
        ]
        result = self.run_pair(baselines, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Trial: t1", result.stdout)
        self.assertIn("Trial: t2", result.stdout)

    def test_duplicate_task_and_trial_pair_is_rejected(self) -> None:
        result = self.run_pair(
            [make_run(), make_run()],
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("duplicate pair ('known-symbol-01', 1,", result.stderr)
        self.assertIn("'t1')", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_different_trial_ids_are_unpaired(self) -> None:
        result = self.run_pair(
            make_run(trial_id="t1"),
            make_run(
                mode="optimized",
                trial_id="t2",
                pair_order="optimized-first",
                input_tokens=700,
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("missing optimized run", result.stdout)
        self.assertIn("missing baseline run", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_pair_order_mismatch_is_incomparable(self) -> None:
        result = self.run_pair(
            make_run(trial_id="t4", pair_order="baseline-first"),
            make_run(
                mode="optimized",
                trial_id="t4",
                pair_order="optimized-first",
                input_tokens=700,
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pair_order differs", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_pair_order_mismatch_precedes_optimized_failure(self) -> None:
        result = self.run_pair(
            make_run(trial_id="t4", pair_order="baseline-first"),
            make_run(
                mode="optimized",
                trial_id="t4",
                pair_order="optimized-first",
                success=False,
                verification=FAILED_VERIFICATION,
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("pair_order differs", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_missing_required_condition_field_is_invalid(self) -> None:
        conditions = dict(CONDITIONS)
        del conditions["provider"]
        result = self.run_pair(
            make_run(conditions=conditions),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("conditions missing required field 'provider'", result.stderr)

    def test_blank_condition_provenance_is_invalid(self) -> None:
        for field in ("fixture", "provider", "hermes_version", "session_type"):
            with self.subTest(field=field):
                result = self.run_pair(
                    make_run(conditions=dict(CONDITIONS, **{field: "  "})),
                    make_run(mode="optimized", input_tokens=700),
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(f"conditions.{field}", result.stderr)
                self.assertNotIn("%", result.stdout)

    def test_empty_tools_condition_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(conditions=dict(CONDITIONS, tools=[])),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("conditions.tools", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_non_numeric_temperature_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(conditions=dict(CONDITIONS, temperature="zero")),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("conditions.temperature", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_non_isolated_session_type_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(conditions=dict(CONDITIONS, session_type="shared")),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("conditions.session_type must be 'fresh-isolated'", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_trial_pair_order_schedule_is_enforced(self) -> None:
        for trial_id, wrong_order in (
            ("t1", "optimized-first"),
            ("t2", "baseline-first"),
            ("t3", "optimized-first"),
        ):
            with self.subTest(trial_id=trial_id):
                result = self.run_pair(
                    make_run(trial_id=trial_id, pair_order=wrong_order),
                    make_run(
                        mode="optimized",
                        trial_id=trial_id,
                        pair_order=wrong_order,
                        input_tokens=700,
                    ),
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(f"trial_id '{trial_id}' requires pair_order", result.stderr)
                self.assertNotIn("%", result.stdout)

    def test_success_true_with_failed_verification_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(verification=FAILED_VERIFICATION),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("success=true requires verification.status='passed'", result.stderr)

    def test_success_false_with_passed_verification_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(success=False, verification=PASSED_VERIFICATION),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("success=false requires verification.status='failed'", result.stderr)

    def test_empty_verification_evidence_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(verification={"status": "passed", "evidence": []}),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("verification.evidence", result.stderr)

    def test_old_string_verification_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(verification="passed"),
            make_run(mode="optimized"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("'verification' must be a JSON object", result.stderr)

    def test_missing_verification_status_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(verification={"evidence": ["task checks passed"]}),
            make_run(mode="optimized"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("verification.status", result.stderr)

    def test_blank_verification_evidence_item_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(verification={"status": "passed", "evidence": [""]}),
            make_run(mode="optimized"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("verification.evidence", result.stderr)

    def test_tokens_without_token_source_are_invalid(self) -> None:
        baseline = make_run()
        del baseline["token_source"]
        result = self.run_pair(baseline, make_run(mode="optimized", input_tokens=700))
        self.assertEqual(result.returncode, 2)
        self.assertIn("token_source is required when token metrics are present", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_invalid_token_source_is_rejected_without_percentage(self) -> None:
        result = self.run_pair(
            make_run(token_source="estimated"),
            make_run(mode="optimized", input_tokens=700),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("'token_source' must be one of", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_optimized_failure_precedes_token_source_parity(self) -> None:
        result = self.run_pair(
            make_run(token_source="provider_usage"),
            make_run(
                mode="optimized",
                token_source="exact_tokenizer",
                success=False,
                verification=FAILED_VERIFICATION,
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("Token reduction unavailable / incomparable", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_three_valid_pairs_report_correct_aggregate_medians(self) -> None:
        baselines = [
            make_run(trial_id="t1", input_tokens=1000),
            make_run(trial_id="t2", pair_order="optimized-first", input_tokens=1200),
            make_run(trial_id="t3", input_tokens=800),
        ]
        optimized = [
            make_run(mode="optimized", trial_id="t1", input_tokens=700),
            make_run(mode="optimized", trial_id="t2", pair_order="optimized-first", input_tokens=900),
            make_run(mode="optimized", trial_id="t3", input_tokens=600),
        ]
        result = self.run_pair(baselines, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Task aggregate: known-symbol-01", result.stdout)
        self.assertIn("Total trials: 3", result.stdout)
        self.assertIn("Comparable successful pairs: 3", result.stdout)
        self.assertIn("Median baseline input tokens: 1000", result.stdout)
        self.assertIn("Median optimized input tokens: 700", result.stdout)
        self.assertIn("Median absolute delta: -300", result.stdout)
        self.assertIn("Median pairwise percentage delta: -25.0%", result.stdout)

    def test_aggregate_keeps_optimized_failure_visible(self) -> None:
        baselines = [
            make_run(trial_id="t1", input_tokens=1000),
            make_run(trial_id="t2", pair_order="optimized-first", input_tokens=1000),
            make_run(trial_id="t3", input_tokens=1000),
        ]
        optimized = [
            make_run(mode="optimized", trial_id="t1", input_tokens=800),
            make_run(
                mode="optimized",
                trial_id="t2",
                pair_order="optimized-first",
                input_tokens=700,
            ),
            make_run(
                mode="optimized",
                trial_id="t3",
                input_tokens=100,
                success=False,
                verification=FAILED_VERIFICATION,
            ),
        ]
        result = self.run_pair(baselines, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Optimized failures: 1", result.stdout)
        self.assertIn("Comparable successful pairs: 2", result.stdout)
        self.assertIn("FAILED OPTIMIZATION", result.stdout)
        self.assertIn("Median pairwise percentage delta: -25.0%", result.stdout)

    def test_model_mismatch_still_precedes_optimized_failure_for_trial(self) -> None:
        result = self.run_pair(
            make_run(trial_id="t2", pair_order="optimized-first"),
            make_run(
                mode="optimized",
                trial_id="t2",
                pair_order="optimized-first",
                model="model-b",
                success=False,
                verification=FAILED_VERIFICATION,
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("model differs", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_conditions_mismatch_still_precedes_optimized_failure_for_trial(self) -> None:
        result = self.run_pair(
            make_run(trial_id="t2", pair_order="optimized-first"),
            make_run(
                mode="optimized",
                trial_id="t2",
                pair_order="optimized-first",
                conditions=dict(CONDITIONS, temperature=1),
                success=False,
                verification=FAILED_VERIFICATION,
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("conditions differ", result.stdout)
        self.assertNotIn("FAILED OPTIMIZATION", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_single_valid_pair_has_no_aggregate_claim(self) -> None:
        result = self.run_pair(make_run(), make_run(mode="optimized", input_tokens=700))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("INSUFFICIENT REPEATED TRIALS", result.stdout)

    def test_null_token_metrics_may_omit_token_source(self) -> None:
        baseline = make_run(input_tokens=None, output_tokens=None)
        optimized = make_run(mode="optimized", input_tokens=None, output_tokens=None)
        del baseline["token_source"]
        del optimized["token_source"]
        result = self.run_pair(baseline, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("missing token count", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_output_only_token_metric_never_produces_input_percentage(self) -> None:
        baseline = make_run(input_tokens=None, output_tokens=200, token_source="provider_usage")
        optimized = make_run(
            mode="optimized",
            input_tokens=None,
            output_tokens=100,
            token_source="provider_usage",
        )
        result = self.run_pair(baseline, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("missing token count", result.stdout)
        self.assertNotIn("%", result.stdout)

    def test_one_success_and_two_incomparable_is_insufficient(self) -> None:
        baselines = [
            make_run(trial_id="t1"),
            make_run(trial_id="t2", pair_order="optimized-first"),
            make_run(trial_id="t3"),
        ]
        optimized = [
            make_run(mode="optimized", trial_id="t1", input_tokens=700),
            make_run(
                mode="optimized",
                trial_id="t2",
                pair_order="optimized-first",
                model="model-b",
            ),
            make_run(mode="optimized", trial_id="t3", tokenizer="tok-b"),
        ]
        result = self.run_pair(baselines, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Comparable successful pairs: 1", result.stdout)
        self.assertIn("Incomparable pairs: 2", result.stdout)
        self.assertIn("INSUFFICIENT REPEATED TRIALS", result.stdout)

    def test_one_success_and_two_optimized_failures_is_insufficient(self) -> None:
        baselines = [
            make_run(trial_id="t1"),
            make_run(trial_id="t2", pair_order="optimized-first"),
            make_run(trial_id="t3"),
        ]
        optimized = [
            make_run(mode="optimized", trial_id="t1", input_tokens=700),
            make_run(
                mode="optimized",
                trial_id="t2",
                pair_order="optimized-first",
                success=False,
                verification=FAILED_VERIFICATION,
            ),
            make_run(
                mode="optimized",
                trial_id="t3",
                success=False,
                verification=FAILED_VERIFICATION,
            ),
        ]
        result = self.run_pair(baselines, optimized)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Comparable successful pairs: 1", result.stdout)
        self.assertIn("Optimized failures: 2", result.stdout)
        self.assertIn("INSUFFICIENT REPEATED TRIALS", result.stdout)

    def test_zero_successful_pairs_is_insufficient(self) -> None:
        result = self.run_pair(
            [make_run(trial_id="t1"), make_run(trial_id="t2", pair_order="optimized-first")],
            [
                make_run(mode="optimized", trial_id="t1", model="model-b"),
                make_run(
                    mode="optimized",
                    trial_id="t2",
                    pair_order="optimized-first",
                    success=False,
                    verification=FAILED_VERIFICATION,
                ),
            ],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Comparable successful pairs: 0", result.stdout)
        self.assertIn("INSUFFICIENT REPEATED TRIALS", result.stdout)

    def test_unknown_task_id_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(task_id="not-in-tasks-json"),
            make_run(task_id="not-in-tasks-json", mode="optimized"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unknown task_id 'not-in-tasks-json'", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_task_prompt_mismatch_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(task_prompt=RUNNABLE_TASK["prompt"] + " "),
            make_run(mode="optimized"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("task_prompt does not exactly match", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_task_revision_mismatch_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(task_revision=2),
            make_run(mode="optimized"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("does not match registry revision", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_task_spec_digest_mismatch_is_invalid(self) -> None:
        result = self.run_pair(
            make_run(task_spec_sha256="0" * 64),
            make_run(mode="optimized"),
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("task_spec_sha256 does not match", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_task_definition_change_rejects_old_digest_without_revision_bump(self) -> None:
        baseline = make_run()
        changed = dict(RUNNABLE_TASK, goal=RUNNABLE_TASK["goal"] + " Changed.")
        self.write_registry([changed])
        result = self.run_pair(baseline, make_run(mode="optimized"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("task_spec_sha256 does not match", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_verification_criteria_change_rejects_old_digest(self) -> None:
        baseline = make_run()
        changed = dict(RUNNABLE_TASK, verification=["different acceptance criterion"])
        self.write_registry([changed])
        result = self.run_pair(baseline, make_run(mode="optimized"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("task_spec_sha256 does not match", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_required_evidence_change_rejects_old_digest(self) -> None:
        baseline = make_run()
        changed = dict(RUNNABLE_TASK, required_evidence=["different evidence requirement"])
        self.write_registry([changed])
        result = self.run_pair(baseline, make_run(mode="optimized"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("task_spec_sha256 does not match", result.stderr)
        self.assertNotIn("%", result.stdout)

    def test_cross_revision_or_spec_runs_never_pair(self) -> None:
        for override in ({"task_revision": 2}, {"task_spec_sha256": "f" * 64}):
            with self.subTest(override=override):
                result = self.run_pair(
                    make_run(),
                    make_run(mode="optimized", **override),
                )
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("%", result.stdout)

    def test_scaffold_task_is_not_runnable(self) -> None:
        scaffold = {
            "id": "scaffold-01",
            "revision": 1,
            "category": "known-symbol",
            "goal": "Future Phase B task.",
            "prompt": "",
            "required_evidence": [],
            "verification": [],
        }
        self.write_registry([scaffold])
        run = make_run(
            task_id="scaffold-01",
            task_revision=1,
            task_prompt="format-only placeholder",
            task_spec_sha256=benchmark_summary.task_spec_sha256(scaffold),
        )
        result = self.run_pair(run, dict(run, mode="optimized"))
        self.assertEqual(result.returncode, 2)
        self.assertIn("task 'scaffold-01' is not runnable", result.stderr)
        self.assertNotIn("%", result.stdout)


if __name__ == "__main__":
    unittest.main()
