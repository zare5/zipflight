import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from zipflight.cli import display, main, render_markdown


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "zipflight", *map(str, args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=20,
        )

    def test_demo_json_has_findings(self):
        result = self.invoke("--demo", "--format", "json")
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["archive"], "demo.zip")
        self.assertGreater(report["summary"]["errors"], 0)

    def test_clean_archive_and_no_files_extracted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "clean.zip"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("hello/readme.txt", "hello")
            before = path.read_bytes()
            result = self.invoke(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("PASS", result.stdout)
            self.assertEqual(list(Path(folder).iterdir()), [path])
            self.assertEqual(path.read_bytes(), before)

    def test_missing_input_json(self):
        result = self.invoke("not-a-real-archive.zip", "--format", "json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "error")
        self.assertNotIn("Traceback", result.stderr)

    def test_policy_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "symbolic.zip"
            with zipfile.ZipFile(path, "w") as archive:
                info = zipfile.ZipInfo("link")
                info.create_system = 3
                info.external_attr = 0o120777 << 16
                archive.writestr(info, "target")
            self.assertEqual(self.invoke(path).returncode, 0)
            self.assertEqual(self.invoke(path, "--fail-on", "warning").returncode, 1)

    def test_argument_errors(self):
        for args in [
            [],
            ["--demo", "archive.zip"],
            ["--demo", "--root-length", "-1"],
            ["--demo", "--target", "unknown"],
        ]:
            self.assertEqual(self.invoke(*args).returncode, 2)

    def test_output_escapes_control_and_markdown(self):
        self.assertEqual(display("a\x1b[2J\u202eb"), "a\\u001b[2J\\u202eb")
        report = {
            "archive": "<script>|.zip",
            "status": "warn",
            "entries": 1,
            "target": "portable",
            "summary": {"errors": 0, "warnings": 1, "infos": 0},
            "issues": [
                {
                    "severity": "warning",
                    "code": "example",
                    "paths": ["<img>|\n"],
                    "message": "Example",
                    "hint": "Rename.",
                }
            ],
        }
        rendered = render_markdown(report)
        self.assertNotIn("<script>", rendered)
        self.assertNotIn("<img>", rendered)
        self.assertIn("&#124;", rendered)

    def test_demo_markdown_and_text(self):
        for fmt in ["text", "markdown"]:
            with contextlib.redirect_stdout(io.StringIO()) as output:
                result = main(["--demo", "--format", fmt])
            self.assertEqual(result, 1)
            self.assertIn("Metadata only", output.getvalue())


if __name__ == "__main__":
    unittest.main()
