from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "research-router.py"


def run_hook(prompt: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"prompt": prompt}),
        text=True,
        capture_output=True,
        check=False,
    )


class ResearchRouterTests(unittest.TestCase):
    def test_routes_ingestion(self) -> None:
        result = run_hook("Récupère les nouveaux papiers arXiv sur les coding agents")
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertIn("paper-ingest", payload["hookSpecificOutput"]["additionalContext"])

    def test_routes_local_research(self) -> None:
        result = run_hook("Cherche des papers sur l'évaluation des agents")
        payload = json.loads(result.stdout)
        self.assertEqual(result.returncode, 0)
        self.assertIn("paper-research", payload["hookSpecificOutput"]["additionalContext"])

    def test_ignores_unrelated_prompt(self) -> None:
        result = run_hook("Corrige le style de cette page Astro")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_module_compiles_without_optional_dependencies(self) -> None:
        spec = importlib.util.spec_from_file_location("research_router", HOOK)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)


if __name__ == "__main__":
    unittest.main()
