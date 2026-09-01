import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "software-development" / "token-efficiency" / "SKILL.md"
HELPER = ROOT / "scripts" / "context_lens.py"


class ContextLensSkillBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL.read_text(encoding="utf-8")

    def test_context_lens_helper_is_present_and_optional(self) -> None:
        self.assertTrue(HELPER.is_file())
        self.assertIn("optionally use `scripts/context_lens.py repo-map`", self.skill)
        self.assertIn("is optional", self.skill)

    def test_targeted_search_remains_the_narrow_default(self) -> None:
        self.assertIn("targeted search first", self.skill)
        self.assertIn("Known symbol/file | targeted search + narrow read", self.skill)

    def test_serena_remains_the_cross_file_semantic_route(self) -> None:
        self.assertIn("Cross-file semantic relationship | Serena if available", self.skill)

    def test_repomix_remains_a_broad_fallback(self) -> None:
        self.assertIn("filtered Repomix as broad fallback", self.skill)


if __name__ == "__main__":
    unittest.main()