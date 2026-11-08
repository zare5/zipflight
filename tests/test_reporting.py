"""Reports should show the cause of failure even in noisy archives."""

import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from zipflight.cli import render_markdown, render_text
from zipflight.core import ScanError, scan_archive


class ReportingTests(unittest.TestCase):
    def test_late_error_survives_notes_and_warning_limits(self):
        with tempfile.TemporaryDirectory() as folder:
            archive_path = Path(folder) / "noisy.zip"
            with zipfile.ZipFile(archive_path, "w") as archive:
                for index in range(2005):
                    archive.writestr(f"__MACOSX/._file{index}", "")
                for index in range(105):
                    archive.writestr(f"visible\u202e{index}.txt", "")
                archive.writestr("CON.txt", "")
            report = scan_archive(archive_path)
        self.assertEqual(report["summary"], {"errors": 1, "warnings": 106, "infos": 2005})
        self.assertEqual(len(report["issues"]), 2001)
        self.assertEqual(report["issues"][0]["code"], "windows-reserved-name")
        self.assertEqual(report["issues"][-1]["code"], "report-truncated")
        self.assertEqual(sum(i["severity"] == "info" for i in report["issues"]), 1894)
        for renderer in (render_text, render_markdown):
            output = renderer(report)
            self.assertIn("CON.txt", output)
            self.assertIn("Finding limit reached", output)
            self.assertLess(output.index("windows-reserved-name"), output.index("bidi-character"))

    def test_nonregular_input_is_rejected(self):
        with self.assertRaises(ScanError):
            scan_archive(os.devnull)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO input is a POSIX case")
    def test_fifo_without_writer_returns_instead_of_hanging(self):
        with tempfile.TemporaryDirectory() as folder:
            fifo = Path(folder) / "input.zip"
            os.mkfifo(fifo)
            result = subprocess.run(
                [sys.executable, "-m", "zipflight", str(fifo)],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("regular ZIP file", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
