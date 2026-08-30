from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude" / "hooks" / "project-guard.py"


def run_hook(payload: dict[str, object] | str) -> subprocess.CompletedProcess[str]:
    encoded = payload if isinstance(payload, str) else json.dumps(payload)
    environment = os.environ.copy()
    environment["CLAUDE_PROJECT_DIR"] = str(ROOT)
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=encoded,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


class ProjectGuardTests(unittest.TestCase):
    def test_allows_write_inside_project(self) -> None:
        result = run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "docs" / "note.md")}}
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blocks_write_outside_project(self) -> None:
        result = run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": "/tmp/outside-paper-insights.md"}}
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("write outside project", result.stderr)

    def test_blocks_sensitive_file(self) -> None:
        result = run_hook({"tool_name": "Edit", "tool_input": {"file_path": str(ROOT / ".env")}})
        self.assertEqual(result.returncode, 2)
        self.assertIn("sensitive file write", result.stderr)

    def test_blocks_direct_corpus_write(self) -> None:
        result = run_hook(
            {"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "data" / "raw.xml")}}
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("direct corpus writes", result.stderr)

    def test_blocks_root_delete(self) -> None:
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}})
        self.assertEqual(result.returncode, 2)
        self.assertIn("recursive delete", result.stderr)

    def test_blocks_broad_staging(self) -> None:
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "git add ."}})
        self.assertEqual(result.returncode, 2)
        self.assertIn("broad staging", result.stderr)

    def test_allows_explicit_dot_relative_path(self) -> None:
        result = run_hook({"tool_name": "Bash", "tool_input": {"command": "git add ./README.md"}})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blocks_force_push_when_branch_precedes_flag(self) -> None:
        result = run_hook(
            {"tool_name": "Bash", "tool_input": {"command": "git push origin main --force"}}
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("force push", result.stderr)

    def test_allows_targeted_test_command(self) -> None:
        result = run_hook(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "uv run pytest tests/test_config.py -v"},
            }
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_json_fails_closed(self) -> None:
        result = run_hook("not json")
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid hook input", result.stderr)


if __name__ == "__main__":
    unittest.main()
