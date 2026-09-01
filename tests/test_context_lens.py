import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "context_lens.py"
SPEC = importlib.util.spec_from_file_location("context_lens_under_test", SCRIPT)
assert SPEC and SPEC.loader
CONTEXT_LENS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONTEXT_LENS)


class ContextLensCliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> dict:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--format", "json"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def run_cli_text(self, *args: str) -> str:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--format", "markdown"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_cli_rejects_non_positive_budgets(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "note.md"
            source.write_text("relevant evidence", encoding="utf-8")
            for invalid in ("0", "127"):
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "prose",
                        str(source),
                        "--max-chars",
                        invalid,
                        "--format",
                        "json",
                    ],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("positive integer", proc.stderr)
                self.assertIn("at least 128", proc.stderr)

    def test_repo_map_skips_symlinks_that_escape_the_repository(self):
        with tempfile.TemporaryDirectory() as repo_tmp, tempfile.TemporaryDirectory() as outside_tmp:
            root = Path(repo_tmp)
            outside = Path(outside_tmp) / "private.txt"
            outside.write_text("EXTERNAL_SECRET Needle", encoding="utf-8")
            link = root / "linked.txt"
            try:
                link.symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"symlinks unavailable: {exc}")

            result = self.run_cli("repo-map", str(root), "--query", "Needle")

            self.assertNotIn("linked.txt", [item["path"] for item in result["files"]])

    def test_repo_map_excludes_reported_symlink_before_content_ingestion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "linked.txt"
            with mock.patch.object(CONTEXT_LENS, "git_files", return_value=[candidate]), mock.patch.object(
                Path, "is_symlink", return_value=True
            ), mock.patch.object(CONTEXT_LENS, "read_text", side_effect=AssertionError("must not ingest symlink")) as read:
                selected = list(CONTEXT_LENS.iter_candidate_files(root))

            self.assertEqual(selected, [])
            read.assert_not_called()

    def test_repo_map_ranks_manifest_entrypoint_and_query_hit_while_skipping_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "node_modules" / "pkg").mkdir(parents=True)
            (root / "package.json").write_text('{"scripts":{"start":"python src/index.py"}}', encoding="utf-8")
            (root / "src" / "index.py").write_text(
                "from .helper import helper\n\ndef Needle(value):\n    return helper(value)\n",
                encoding="utf-8",
            )
            (root / "src" / "helper.py").write_text("def helper(value):\n    return value\n", encoding="utf-8")
            (root / "src" / "multi.py").write_text("def Needle_helper(value):\n    return value\n", encoding="utf-8")
            (root / "src" / "single.py").write_text("def Needle(value):\n    return value\n", encoding="utf-8")
            (root / ".env").write_text("SECRET=do-not-index\n", encoding="utf-8")
            (root / "node_modules" / "pkg" / "index.js").write_text("Needle", encoding="utf-8")
            for locale in ("en", "fr", "de"):
                doc = root / "website" / locale / "topic.md"
                doc.parent.mkdir(parents=True, exist_ok=True)
                doc.write_text("Needle helper documentation", encoding="utf-8")

            result = self.run_cli("repo-map", str(root), "--query", "Needle", "--max-files", "5")
            paths = [item["path"] for item in result["files"]]

            self.assertIn("package.json", paths)
            self.assertIn("src/index.py", paths)
            self.assertNotIn(".env", paths)
            self.assertFalse(any(path.startswith("node_modules/") for path in paths))
            hit = next(item for item in result["files"] if item["path"] == "src/index.py")
            self.assertIn("query-hit", hit["reasons"])
            self.assertIn("Needle", hit["symbols"])
            self.assertEqual(result["estimate_method"], "chars/4 heuristic; not a tokenizer")

            ranked = self.run_cli("repo-map", str(root), "--query", "Needle helper", "--max-files", "20")
            scores = {item["path"]: item["score"] for item in ranked["files"]}
            self.assertGreaterEqual(scores["src/multi.py"] - scores["src/single.py"], 15)

            diverse = self.run_cli("repo-map", str(root), "--query", "Needle helper", "--max-files", "20")
            repeated_docs = [item for item in diverse["files"] if item["path"].endswith("/topic.md")]
            self.assertLessEqual(len(repeated_docs), 2)

    def test_repo_map_excludes_case_insensitive_sensitive_name_variants(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sensitive_names = (
                ".ENVRC",
                ".EnV.production",
                "Credential.JSON",
                "credentials.toml",
                "SECRET.yaml",
                "secrets.TXT",
                "private-key.ini",
                "PRIVATE_KEY.yml",
                "privatekey.conf",
            )
            for name in sensitive_names:
                (root / name).write_text("Needle private material", encoding="utf-8")
            secret_dir = root / "SeCrEtS"
            secret_dir.mkdir()
            (secret_dir / "notes.md").write_text("Needle private material", encoding="utf-8")
            (root / "safe.py").write_text("Needle public material", encoding="utf-8")

            result = self.run_cli("repo-map", str(root), "--query", "Needle", "--max-files", "20")
            paths = [item["path"] for item in result["files"]]

            self.assertEqual(paths, ["safe.py"])

    def test_direct_file_modes_reject_sensitive_filenames_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for command, name in (("prose", ".env"), ("records", "auth.json")):
                source = root / name
                source.write_text("DO_NOT_EXPOSE_THIS_VALUE", encoding="utf-8")
                proc = subprocess.run(
                    [sys.executable, str(SCRIPT), command, str(source), "--format", "json"],
                    text=True,
                    capture_output=True,
                    check=False,
                )

                with self.subTest(command=command, name=name):
                    self.assertEqual(proc.returncode, 2)
                    self.assertIn("sensitive filename", proc.stderr)
                    self.assertNotIn("DO_NOT_EXPOSE_THIS_VALUE", proc.stdout + proc.stderr)

    def test_git_files_uses_nul_delimiters_and_preserves_unusual_names(self):
        root = Path("repo-root").resolve()
        names = ["unicodé.py", "tab\tname.txt", "line\nname.md"]
        payload = os.fsencode("\0".join(names) + "\0")

        def fake_run(command, **kwargs):
            stdout = os.fsdecode(payload) if kwargs.get("text") else payload
            stderr = "" if kwargs.get("text") else b""
            return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr=stderr)

        with mock.patch.object(CONTEXT_LENS.subprocess, "run", side_effect=fake_run) as run, mock.patch.object(
            Path, "is_file", return_value=True
        ):
            paths = CONTEXT_LENS.git_files(root)

        self.assertIsNotNone(paths)
        self.assertEqual([path.relative_to(root).as_posix() for path in paths], names)
        command = run.call_args.args[0]
        kwargs = run.call_args.kwargs
        self.assertIn("-z", command)
        self.assertFalse(kwargs.get("text", False))

    def test_repo_map_labels_required_manual_followup_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("def main():\n    return 1\n", encoding="utf-8")

            result = self.run_cli("repo-map", str(root), "--query", "main")
            rendered = self.run_cli_text("repo-map", str(root), "--query", "main")

            self.assertNotIn("coverage_checks", result)
            self.assertEqual(
                result["required_followup_checks"],
                [
                    "manifest-and-entrypoint",
                    "query-hits",
                    "dependency-hubs",
                    "adjacent-tests",
                    "configuration-and-runtime-registration",
                ],
            )
            self.assertIn("Required manual follow-up checks (not completed coverage)", rendered)

    def test_symbols_classifies_definitions_imports_calls_and_dynamic_risk(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a.py").write_text("def target(value):\n    return value\n", encoding="utf-8")
            (root / "b.py").write_text(
                "from a import target\n\ndef run():\n    return target(3)\n",
                encoding="utf-8",
            )
            (root / "registry.py").write_text('HANDLERS = {"target": object()}\n', encoding="utf-8")

            result = self.run_cli("symbols", str(root), "target", "--limit", "20")

            self.assertTrue(any(hit["path"] == "a.py" for hit in result["definitions"]))
            self.assertTrue(any(hit["path"] == "b.py" for hit in result["imports"]))
            self.assertTrue(any(hit["path"] == "b.py" for hit in result["calls"]))
            self.assertTrue(any(hit["path"] == "registry.py" for hit in result["dynamic_risks"]))
            self.assertEqual(result["unresolved_risk_checks"], ["generated-code", "framework-routing", "reflection", "configuration"])

    def test_symbols_scans_all_files_even_when_output_limit_is_small(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(12):
                (root / f"a_ref_{index:02d}.py").write_text("value = target\n", encoding="utf-8")
            (root / "z_definition.py").write_text("def target():\n    return 1\n", encoding="utf-8")

            result = self.run_cli("symbols", str(root), "target", "--limit", "1")

            self.assertEqual(result["definitions"][0]["path"], "z_definition.py")
            self.assertGreaterEqual(result["total_text_hits"], 13)

    def test_balanced_defaults_cap_map_at_twenty_and_symbol_bucket_at_twelve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(25):
                (root / f"module_{index:02d}.py").write_text(
                    f"value_{index} = balanced_target\n", encoding="utf-8"
                )

            mapped = self.run_cli("repo-map", str(root), "--query", "balanced_target")
            symbols = self.run_cli("symbols", str(root), "balanced_target")

            self.assertEqual(mapped["files_selected"], 20)
            self.assertEqual(len(symbols["references"]), 12)

    def test_repository_scans_honor_explicit_file_bounds(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(6):
                (root / f"module_{index}.py").write_text(f"value_{index} = target\n", encoding="utf-8")

            mapped = self.run_cli("repo-map", str(root), "--query", "target", "--max-scan-files", "2")
            symbols = self.run_cli("symbols", str(root), "target", "--max-scan-files", "2")

            self.assertEqual(mapped["files_scanned"], 2)
            self.assertEqual(symbols["files_scanned"], 2)

    def test_records_compacts_uniform_json_and_refuses_irregular_shapes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uniform = root / "uniform.json"
            irregular = root / "irregular.json"
            uniform.write_text('[{"id":1,"name":"A"},{"id":2,"name":"B"}]', encoding="utf-8")
            irregular.write_text('[{"id":1,"meta":{"x":2}},{"id":2,"name":"B"}]', encoding="utf-8")

            compact = self.run_cli("records", str(uniform))
            refused = self.run_cli("records", str(irregular))

            self.assertTrue(compact["eligible_for_compact_table"])
            self.assertTrue(compact["round_trip_verified"])
            self.assertEqual(compact["columns"], ["id", "name"])
            self.assertEqual(compact["rows"], [[1, "A"], [2, "B"]])
            self.assertFalse(refused["eligible_for_compact_table"])
            self.assertEqual(refused["recommendation"], "keep-json")

    def test_records_decodes_actual_compact_text_losslessly(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "records.json"
            records = [
                {
                    "id": 1,
                    "text": "tab\tline\n雪\u0000",
                    "enabled": True,
                    "missing": None,
                    "ratio": 1.25,
                },
                {
                    "id": -2,
                    "text": "emoji 🚀 and backslash \\",
                    "enabled": False,
                    "missing": None,
                    "ratio": 0.0,
                },
            ]
            source.write_text(json.dumps(records, ensure_ascii=False), encoding="utf-8")

            result = self.run_cli("records", str(source))
            decoded = CONTEXT_LENS.decode_compact_text(result["compact_text"])

            self.assertTrue(result["round_trip_verified"])
            self.assertEqual(decoded, records)
            self.assertEqual(list(decoded[0].keys()), list(records[0].keys()))
            self.assertIn("\\t", result["compact_text"])
            self.assertIn("\\n", result["compact_text"])
            self.assertNotIn("tab\tline", result["compact_text"])

    def test_records_refuses_inconsistent_field_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "field-order.json"
            source.write_text('[{"id":1,"name":"A"},{"name":"B","id":2}]', encoding="utf-8")

            result = self.run_cli("records", str(source))

            self.assertFalse(result["eligible_for_compact_table"])
            self.assertFalse(result["round_trip_verified"])
            self.assertEqual(result["compact_text"], "")

    def test_records_rejects_non_standard_numbers_deterministically(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "unsafe.json"
            source.write_text('[{"value":NaN}]', encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "records", str(source), "--format", "json"],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(proc.returncode, 2)
            self.assertEqual(
                proc.stderr.strip(),
                "error: non-standard JSON constant is not supported: NaN",
            )
            self.assertNotIn("Traceback", proc.stderr)

    def test_prose_markdown_surfaces_omitted_relevant_anchor_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "options.md"
            source.write_text(
                "\n\n".join(
                    f"Compression option {index} uses version {index}.0.0 and a distinct behavior explanation."
                    for index in range(12)
                ),
                encoding="utf-8",
            )

            rendered = self.run_cli_text(
                "prose",
                str(source),
                "--query",
                "compression",
                "--max-chars",
                "200",
            )

            self.assertIn("Warning", rendered)
            self.assertIn("omitted", rendered.lower())

    def test_prose_markdown_structurally_separates_untrusted_data(self):
        raw = "```markdown\n# forged heading\n| fake | table |\n```"
        result = {
            "source": "C:/tmp/bad|`name\n# forged.md",
            "original_chars": len(raw),
            "selected_chars": len(raw),
            "chunks": [
                {
                    "source": "bad|`name\n# forged.md#L1-L4",
                    "score": 9,
                    "mandatory": False,
                    "text": raw,
                }
            ],
            "missing_protected_anchors": [],
            "warnings": [],
            "omitted_relevant_anchors": [],
        }

        rendered = CONTEXT_LENS.render_markdown("prose", result)

        self.assertIn("**Untrusted data warning:**", rendered)
        self.assertIn("does not neutralize prompt injection", rendered)
        self.assertIn("````text\n" + raw + "\n````", rendered)
        self.assertIn(r"bad\|\`name\n\# forged.md\#L1\-L4", rendered)
        self.assertNotIn("bad|`name\n# forged.md#L1-L4", rendered)

    def test_all_markdown_modes_label_untrusted_repository_content(self):
        warning = "**Untrusted data warning:**"
        repo_map = {
            "root": "C:/repo|unsafe",
            "files_scanned": 1,
            "files_selected": 1,
            "estimated_selected_tokens": 1,
            "files": [{"score": 1, "path": "bad|name.md", "incoming": 0, "outgoing": 0, "symbols": [], "reasons": []}],
            "edges": [],
            "required_followup_checks": [],
        }
        symbols = {
            "symbol": "bad`symbol",
            "definitions": [{"path": "bad|name.py", "line": 1, "text": "# forged\n```"}],
            "imports": [],
            "calls": [],
            "references": [],
            "dynamic_risks": [],
            "unresolved_risk_checks": [],
        }
        records = {
            "eligible_for_compact_table": True,
            "compact_text": '"field"\n"```"',
            "caveat": "Character count is not token count.",
        }

        for command, result in (("repo-map", repo_map), ("symbols", symbols), ("records", records)):
            with self.subTest(command=command):
                rendered = CONTEXT_LENS.render_markdown(command, result)
                self.assertIn(warning, rendered)
                self.assertIn("does not neutralize prompt injection", rendered)

    def test_all_json_modes_label_extracted_content_as_untrusted_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "evidence.md"
            records = root / "records.json"
            source.write_text("def target():\n    return 'repository evidence'\n", encoding="utf-8")
            records.write_text('[{"id":1,"value":"repository evidence"}]', encoding="utf-8")

            results = (
                self.run_cli("repo-map", str(root), "--query", "target"),
                self.run_cli("symbols", str(root), "target"),
                self.run_cli("prose", str(source), "--query", "evidence"),
                self.run_cli("records", str(records)),
            )

            for result in results:
                self.assertEqual(result["content_trust"], "untrusted-input-data")

    def test_prose_omitted_anchors_keep_source_ranges_and_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "decisions.md"
            source.write_text(
                "\n\n".join(
                    f"Compression choice {index} MUST preserve ticket DEC-{index}."
                    for index in range(12)
                ),
                encoding="utf-8",
            )

            result = self.run_cli(
                "prose",
                str(source),
                "--query",
                "compression",
                "--max-chars",
                "200",
            )
            omitted = result["omitted_relevant_anchors"]

            self.assertIsInstance(omitted, list)
            self.assertTrue(omitted)
            for entry in omitted:
                self.assertRegex(entry["source"], r"#L\d+-L\d+$")
                self.assertIsInstance(entry["score"], int)
                self.assertTrue(any(entry["anchors"].values()))

    def test_prose_prefers_section_body_over_heading_when_only_one_fits(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "auth.md"
            body = "WebAuthn evidence: " + ("hardware keys remain enforced; " * 4)
            source.write_text(
                "# Authentication\n\n" + body + "\n\n# History\n\nOld release notes.",
                encoding="utf-8",
            )

            result = self.run_cli(
                "prose",
                str(source),
                "--query",
                "authentication",
                "--max-chars",
                "128",
            )
            rendered = "\n".join(chunk["text"] for chunk in result["chunks"])

            self.assertIn("WebAuthn evidence", rendered)
            self.assertNotEqual(rendered.strip(), "# Authentication")

    def test_prose_heading_query_keeps_following_body_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "policy.md"
            source.write_text(
                "## Critical retry policy\n\n"
                "Workers back off after transient upload failures.\n\n"
                "Authentication failures go directly to operator review.\n\n"
                "## Unrelated appendix\n\nHistorical notes only.\n",
                encoding="utf-8",
            )

            result = self.run_cli(
                "prose",
                str(source),
                "--query",
                "critical retry policy",
                "--max-chars",
                "500",
            )
            rendered = "\n".join(chunk["text"] for chunk in result["chunks"])

            self.assertIn("Workers back off after transient upload failures.", rendered)
            self.assertIn("Authentication failures go directly to operator review.", rendered)
            self.assertNotIn("Historical notes only.", rendered)

    def test_prose_splits_a_giant_relevant_paragraph_before_budgeting(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "giant.md"
            source.write_text(
                ("Historical release notes without task relevance. " * 120)
                + "Tree-sitter compression MUST retain the final decision version 4.5.6.",
                encoding="utf-8",
            )

            result = self.run_cli(
                "prose",
                str(source),
                "--query",
                "tree-sitter compression",
                "--max-chars",
                "500",
            )
            rendered = "\n".join(chunk["text"] for chunk in result["chunks"])

            self.assertLessEqual(result["selected_chars"], 500)
            self.assertIn("MUST", rendered)
            self.assertIn("4.5.6", rendered)
            self.assertEqual(result["missing_protected_anchors"], [])

    def test_prose_does_not_make_unrelated_urls_and_versions_mandatory(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "release-notes.md"
            unrelated = "\n\n".join(
                f"Release 0.{index}.25 is documented at https://example.com/releases/{index}."
                for index in range(40)
            )
            source.write_text(
                unrelated
                + "\n\n## Compression policy\n\n"
                + "Tree-sitter compression MUST preserve version 2.1.7. "
                + "See https://example.com/compression for the decision.\n",
                encoding="utf-8",
            )

            result = self.run_cli(
                "prose",
                str(source),
                "--query",
                "tree-sitter compression",
                "--max-chars",
                "500",
            )
            rendered = "\n".join(chunk["text"] for chunk in result["chunks"])

            self.assertLessEqual(result["selected_chars"], 500)
            self.assertFalse(result["budget_overflow_for_protected_content"])
            self.assertIn("MUST", rendered)
            self.assertIn("2.1.7", rendered)
            self.assertIn("https://example.com/compression", rendered)
            self.assertNotIn("https://example.com/releases/0", rendered)
            self.assertEqual(result["missing_protected_anchors"], [])

    def test_prose_keeps_query_evidence_negations_numbers_and_source_pointers(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "incident.md"
            filler = "Unrelated background sentence. " * 80
            source.write_text(
                "# Incident\n\n"
                + filler
                + "\n\n## Retry policy\n\nWorkers MUST retry failed uploads 3 times. "
                + "They must NOT retry authentication failures. Ticket INC-42 records the decision.\n\n"
                + filler,
                encoding="utf-8",
            )

            result = self.run_cli(
                "prose",
                str(source),
                "--query",
                "retry failed uploads",
                "--max-chars",
                "500",
            )
            rendered = "\n".join(chunk["text"] for chunk in result["chunks"])

            self.assertIn("MUST", rendered)
            self.assertIn("NOT", rendered)
            self.assertIn("3", rendered)
            self.assertIn("INC-42", rendered)
            self.assertTrue(all("#L" in chunk["source"] for chunk in result["chunks"]))
            self.assertEqual(result["missing_protected_anchors"], [])
            self.assertLess(result["selected_chars"], result["original_chars"])
            self.assertEqual(result["estimate_method"], "chars/4 heuristic; not a tokenizer")


if __name__ == "__main__":
    unittest.main()
