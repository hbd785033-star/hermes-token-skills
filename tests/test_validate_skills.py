import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


VALID_SKILL = """---
name: sample-skill
description: Use when validating a sample skill repository.
version: 1.0.0
author: Example Author
license: MIT
metadata:
  hermes:
    tags: [sample]
    related_skills: [host-skill]
---

# Sample Skill

See `references/guide.md`.
"""


class ValidateSkillsTests(unittest.TestCase):
    def run_validator(self, root: Path) -> subprocess.CompletedProcess[str]:
        script = Path(__file__).parents[1] / "scripts" / "validate_skills.py"
        return subprocess.run(
            [sys.executable, str(script), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def make_repository(self, skill: str = VALID_SKILL, directory: str = "sample-skill") -> Path:
        directory_path = Path(self.temp_directory.name)
        skill_dir = directory_path / "software-development" / directory
        (skill_dir / "references").mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(skill, encoding="utf-8")
        (skill_dir / "references" / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (directory_path / "README.md").write_text(
            "# Skills\n\n## External `related_skills`\n\n"
            "- `host-skill` — supplied outside this repository.\n",
            encoding="utf-8",
        )
        return directory_path

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()

    def tearDown(self) -> None:
        self.temp_directory.cleanup()

    def test_valid_repository_passes(self) -> None:
        result = self.run_validator(self.make_repository())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Validated 1 skill(s): OK", result.stdout)

    def test_missing_required_frontmatter_fails(self) -> None:
        skill = VALID_SKILL.replace("version: 1.0.0\n", "")
        result = self.run_validator(self.make_repository(skill))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing required frontmatter field 'version'", result.stdout)

    def test_bad_directory_name_fails(self) -> None:
        result = self.run_validator(self.make_repository(directory="Sample_Skill"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lowercase kebab-case", result.stdout)

    def test_undeclared_external_related_skill_fails(self) -> None:
        skill = VALID_SKILL.replace("host-skill", "not-declared")
        result = self.run_validator(self.make_repository(skill))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not-declared", result.stdout)
        self.assertIn("not declared in README.md", result.stdout)

    def test_missing_referenced_file_fails(self) -> None:
        skill = VALID_SKILL.replace("references/guide.md", "references/missing.md")
        result = self.run_validator(self.make_repository(skill))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("referenced file does not exist", result.stdout)


if __name__ == "__main__":
    unittest.main()
