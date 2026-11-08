"""Archive-level regressions found during independent review."""

import pathlib
import struct
import tempfile
import unittest
import zipfile

from zipflight.core import ScanError, scan_archive


class RegressionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = pathlib.Path(self.temporary.name) / "review.zip"

    def write_names(self, names):
        with zipfile.ZipFile(self.path, "w") as archive:
            for name in names:
                archive.writestr(name, "fixture")

    def make_zip64(self, prefix=b""):
        self.write_names(["readme.txt"])
        raw = self.path.read_bytes()
        eocd_offset = raw.rfind(b"PK\x05\x06")
        end = list(struct.unpack("<4s4H2IH", raw[eocd_offset:]))
        zip64 = struct.pack(
            "<4sQ2H2I4Q",
            b"PK\x06\x06",
            44,
            45,
            45,
            0,
            0,
            end[3],
            end[4],
            end[5],
            end[6],
        )
        locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, eocd_offset, 1)
        end[3] = end[4] = 0xFFFF
        end[5] = end[6] = 0xFFFFFFFF
        self.path.write_bytes(prefix + raw[:eocd_offset] + zip64 + locator + struct.pack("<4s4H2IH", *end))
        return len(prefix) + eocd_offset + len(zip64)

    def test_normalized_leaf_alias_is_a_collision(self):
        for alias in ("a//b.txt", "a/./b.txt"):
            with self.subTest(alias=alias):
                self.write_names(["a/b.txt", alias])
                result = scan_archive(self.path)
                self.assertGreater(result["summary"]["errors"], 0, result)
                self.assertTrue(
                    any(set(item["paths"]) >= {"a/b.txt", alias} for item in result["issues"]),
                    result,
                )

    def test_conflicting_directory_markers_cannot_silently_pass(self):
        with zipfile.ZipFile(self.path, "w") as archive:
            info = zipfile.ZipInfo("assets")
            info.create_system = 3
            info.external_attr = (0o100644 << 16) | 0x10
            archive.writestr(info, "regular file data")
            archive.writestr("assets/logo.txt", "fixture")
        self.assertNotEqual(scan_archive(self.path)["status"], "pass")

    def test_windows_control_characters_fail_default_threshold(self):
        self.write_names(["a\tb.txt"])
        for target in ("portable", "windows"):
            with self.subTest(target=target):
                self.assertGreater(scan_archive(self.path, target=target)["summary"]["errors"], 0)

    def test_zip64_consistent_prefix_offsets_remain_supported(self):
        self.make_zip64(prefix=b"harmless executable stub\n")
        self.assertEqual(scan_archive(self.path)["status"], "pass")

    def test_zip64_locator_must_agree_with_directory_prefix(self):
        for prefix in (b"", b"harmless executable stub\n"):
            with self.subTest(prefix=prefix):
                locator_offset = self.make_zip64(prefix=prefix)
                data = bytearray(self.path.read_bytes())
                struct.pack_into("<Q", data, locator_offset + 8, 0)
                self.path.write_bytes(data)
                with self.assertRaises(ScanError):
                    scan_archive(self.path)


if __name__ == "__main__":
    unittest.main()
