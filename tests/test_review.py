"""Additional review regressions using real archives and boundary cases."""

import pathlib
import tempfile
import unittest
import zipfile

from zipflight.core import scan_archive


class ReviewTests(unittest.TestCase):
    def test_dos_directory_flag_without_slash_is_not_silent(self):
        # bsdtar honors the DOS directory bit, while Python's extractor uses
        # the name suffix and would create "assets" as a file. Both paths are
        # harmless; the check must expose the ambiguous type interpretation.
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "directory-markers.zip"
            with zipfile.ZipFile(path, "w") as archive:
                info = zipfile.ZipInfo("assets")
                info.create_system = 0
                info.external_attr = 0x10
                archive.writestr(info, b"")
                archive.writestr("assets/logo.txt", b"harmless fixture")
            report = scan_archive(path)
            self.assertNotEqual(report["status"], "pass", report)
            self.assertTrue(any("assets" in issue["paths"] for issue in report["issues"]))

    def test_classic_zip_can_contain_exactly_65535_members(self):
        # 0xffff is both the largest classic count and the ZIP64 sentinel.
        # The standard writer permits this exact count without a ZIP64 locator.
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "classic-count-boundary.zip"
            with zipfile.ZipFile(path, "w", allowZip64=False) as archive:
                for index in range(65535):
                    archive.writestr(str(index), b"")
            with path.open("rb") as stream:
                stream.seek(-42, 2)
                tail = stream.read()
            self.assertEqual(tail[-22:-18], b"PK\x05\x06")
            self.assertNotEqual(tail[:4], b"PK\x06\x07")
            report = scan_archive(path, target="linux")
            self.assertEqual(report["entries"], 65535)
            self.assertEqual(report["status"], "pass")


if __name__ == "__main__":
    unittest.main()
