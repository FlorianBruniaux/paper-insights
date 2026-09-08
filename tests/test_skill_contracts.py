from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".agents" / "skills"


class SkillContractTests(unittest.TestCase):
    def test_dual_host_projection_uses_one_canonical_source(self) -> None:
        self.assertEqual((ROOT / ".claude" / "skills").resolve(), SKILLS.resolve())

    def test_each_skill_has_bounded_routing_scenarios(self) -> None:
        for skill_name in ("paper-ingest", "paper-research", "paper-citation"):
            with self.subTest(skill=skill_name):
                path = SKILLS / skill_name / "evals" / "scenarios.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(payload["skill"], skill_name)
                self.assertGreaterEqual(len(payload["positive"]), 8)
                self.assertGreaterEqual(len(payload["negative"]), 2)
                self.assertTrue(
                    all(isinstance(item, str) and item.strip() for item in payload["positive"])
                )
                self.assertTrue(
                    all(isinstance(item, str) and item.strip() for item in payload["negative"])
                )

    def test_skills_describe_the_operational_gate_2_cli(self) -> None:
        expected_tokens = {
            "paper-ingest": ("paper-insights discover", "paper-insights ingest"),
            "paper-research": ("paper-insights search papers", "paper-insights search passages"),
            "paper-citation": ("paper-insights cite",),
        }
        for skill_name, tokens in expected_tokens.items():
            with self.subTest(skill=skill_name):
                text = (SKILLS / skill_name / "SKILL.md").read_text(encoding="utf-8")
                self.assertNotIn("planned but not implemented", text)
                for token in tokens:
                    self.assertIn(token, text)


if __name__ == "__main__":
    unittest.main()
