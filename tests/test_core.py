"""Real ZIP fixtures stay in memory/on disk; dangerous paths are never extracted."""

import io
import json
import stat
import struct
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from zipflight.core import ScanError, scan_archive


def archive_bytes(names=(), *, comment=b"", compression=zipfile.ZIP_DEFLATED):
    output = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        with zipfile.ZipFile(output, "w", compression=compression) as archive:
            for item in names:
                if isinstance(item, tuple):
                    info, content = item
                else:
                    info, content = item, b"example payload"
                if isinstance(info, str):
                    original = info
                    info = zipfile.ZipInfo(original)
                    # ZipInfo normalizes native backslashes on Windows. Retain
                    # the authored metadata to test cross-platform ZIP input.
                    info.filename = original
                    info.compress_type = compression
                archive.writestr(info, content)
            archive.comment = comment
    return output.getvalue()


def change_central(data, field_offset, fmt, value, *, member=0):
    result = bytearray(data)
    start = -1
    for _ in range(member + 1):
        start = result.index(b"PK\x01\x02", start + 1)
    struct.pack_into(fmt, result, start + field_offset, value)
    return bytes(result)


def zip64_end(data):
    end = data.rindex(b"PK\x05\x06")
    e = struct.unpack_from("<4s4H2IH", data, end)
    record = struct.pack("<4sQ2H2I4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, e[4], e[4], e[5], e[6])
    locator = struct.pack("<4sIQI", b"PK\x06\x07", 0, end, 1)
    replacement = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0)
    return data[:end] + record + locator + replacement


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "sample.zip"

    def tearDown(self):
        self.temp.cleanup()

    def scan(self, data, **kwargs):
        self.path.write_bytes(data)
        return scan_archive(self.path, **kwargs)

    def codes(self, result):
        return {issue["code"] for issue in result["issues"]}

    def test_clean_archive_and_json_contract(self):
        report = self.scan(archive_bytes(["docs/readme.txt", "data.csv"]))
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["entries"], 2)
        self.assertEqual(report["archive"], "sample.zip")
        self.assertEqual(report["summary"], {"errors": 0, "warnings": 0, "infos": 0})
        self.assertEqual(report["declared_uncompressed_bytes"], 30)
        self.assertEqual(json.loads(json.dumps(report)), report)

    def test_empty_archive(self):
        report = self.scan(archive_bytes())
        self.assertEqual(report["entries"], 0)
        self.assertEqual(report["status"], "pass")

    def test_does_not_open_or_decompress_member_payloads(self):
        data = archive_bytes(["readme.txt"])
        # A deliberately broken compressed payload still permits metadata
        # inspection; this tool must not claim it verified the CRC/content.
        central = data.index(b"PK\x01\x02")
        damaged = bytearray(data)
        damaged[40:central] = b"x" * (central - 40)
        with patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("payload opened")):
            report = self.scan(bytes(damaged))
        self.assertEqual(report["status"], "pass")

    def test_windows_names_and_device_extensions(self):
        names = ["CON.txt", "aux .log", "COM¹", "LPT².log", "data/a:b", "trailing. "]
        report = self.scan(archive_bytes(names))
        self.assertTrue(
            {"windows-reserved-name", "windows-forbidden-character", "windows-trailing-character"}
            <= self.codes(report)
        )
        self.assertEqual(report["status"], "fail")
        reserved = [i for i in report["issues"] if i["code"] == "windows-reserved-name"]
        self.assertEqual(len(reserved), 4)

    def test_devices_are_not_reserved_substrings(self):
        report = self.scan(archive_bytes(["CONSOLE.txt", "COM10.txt", "AUXILIARY", "a/con-file.txt"]))
        self.assertEqual(report["status"], "pass")

    def test_linux_target_accepts_windows_only_names(self):
        report = self.scan(
            archive_bytes(["CON.txt", "a:b", "trailing. ", "README", "readme"]), target="linux"
        )
        self.assertEqual(report["status"], "pass")

    def test_absolute_drive_traversal_and_backslash(self):
        names = [
            "../outside.txt",
            "a/../b.txt",
            "/root.txt",
            "C:relative.txt",
            "C:/absolute.txt",
            "..\\outside.txt",
            "\\\\server\\share\\x",
        ]
        report = self.scan(archive_bytes(names))
        self.assertTrue({"path-traversal", "absolute-path", "backslash-separator"} <= self.codes(report))
        self.assertFalse((Path(self.temp.name) / "outside.txt").exists())

    def test_control_and_bidi(self):
        report = self.scan(archive_bytes(["line\nfeed.txt", "report\u202etxt.exe"]))
        self.assertTrue({"control-character", "bidi-character"} <= self.codes(report))

    def test_nul_preserved_in_metadata_without_zipfile_truncation(self):
        data = archive_bytes(["nulXtail.txt"])
        central = data.index(b"PK\x01\x02")
        changed = bytearray(data)
        changed[central + 46 + 3] = 0
        report = self.scan(bytes(changed))
        self.assertIn("nul-character", self.codes(report))
        self.assertIn("\x00tail", report["issues"][0]["paths"][0])

    def test_duplicate_and_implicit_file_directory_conflict(self):
        report = self.scan(archive_bytes(["same.txt", "same.txt", "assets", "assets/icon.png"]))
        self.assertTrue({"duplicate-entry", "file-directory-conflict"} <= self.codes(report))

    def test_explicit_directory_and_file_conflict(self):
        report = self.scan(archive_bytes(["docs", "docs/"]))
        self.assertIn("file-directory-conflict", self.codes(report))

    def test_case_collisions_include_implicit_parents(self):
        report = self.scan(archive_bytes(["Docs/a.txt", "docs/b.txt", "README", "readme"]))
        groups = [i["paths"] for i in report["issues"] if i["code"] == "case-collision"]
        self.assertIn(["Docs", "docs"], groups)
        self.assertIn(["README", "readme"], groups)

    def test_unicode_normalization_and_conservative_casefold(self):
        report = self.scan(archive_bytes(["café.txt", "cafe\u0301.txt", "Straße.txt", "STRASSE.txt"]))
        self.assertTrue({"unicode-normalization-collision", "case-collision"} <= self.codes(report))
        self.assertEqual(report["status"], "warn")
        self.assertTrue(all(i["severity"] == "warning" for i in report["issues"]))

    def test_windows_does_not_assume_nfc_normalization(self):
        report = self.scan(archive_bytes(["café.txt", "cafe\u0301.txt"]), target="windows")
        self.assertEqual(report["status"], "pass")

    def test_trailing_alias_and_combined_alias(self):
        report = self.scan(archive_bytes(["docs/file", "docs/file.", "README ", "readme"]))
        self.assertTrue({"windows-trim-collision", "windows-alias-collision"} <= self.codes(report))

    def test_path_budget_boundary_and_utf16_count(self):
        data = archive_bytes(["a" * 218])
        self.assertNotIn("windows-path-length", self.codes(self.scan(data, root_length=40)))
        self.assertIn("windows-path-length", self.codes(self.scan(data, root_length=41)))
        report = self.scan(archive_bytes(["😀" * 110]), root_length=40)
        self.assertIn("windows-path-length", self.codes(report))

    def test_component_lengths_differ_for_utf8_and_utf16(self):
        report = self.scan(archive_bytes(["é" * 128]))
        self.assertIn("utf8-component-length", self.codes(report))
        self.assertNotIn("windows-component-length", self.codes(report))
        report = self.scan(archive_bytes(["a" * 256]))
        self.assertIn("windows-component-length", self.codes(report))

    def test_symlink_special_file_and_os_junk(self):
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        fifo = zipfile.ZipInfo("pipe")
        fifo.create_system = 3
        fifo.external_attr = (stat.S_IFIFO | 0o600) << 16
        report = self.scan(archive_bytes([(link, b"../target"), (fifo, b""), ".DS_Store"]))
        self.assertTrue({"symlink-entry", "special-file-entry", "os-metadata"} <= self.codes(report))

    def test_encryption_unusual_method_and_declared_ratio(self):
        data = archive_bytes(["payload"])
        data = change_central(data, 8, "<H", 1)
        data = change_central(data, 10, "<H", 99)
        data = change_central(data, 20, "<I", 10)
        data = change_central(data, 24, "<I", 200 * 1024 * 1024)
        report = self.scan(data)
        self.assertTrue(
            {"encrypted-entry", "compression-method", "declared-compression-ratio"} <= self.codes(report)
        )

    def test_legacy_encoding(self):
        data = archive_bytes(["legacy.txt"])
        start = data.index(b"PK\x01\x02")
        changed = bytearray(data)
        changed[start + 46] = 0x82  # CP437 e-acute, no UTF-8 flag
        report = self.scan(bytes(changed))
        self.assertIn("legacy-name-encoding", self.codes(report))

    def test_unicode_extra_reports_alternate_name(self):
        info = zipfile.ZipInfo("ascii.txt")
        extra = b"\x01" + b"\0" * 4 + "other.txt".encode()
        info.extra = struct.pack("<HH", 0x7075, len(extra)) + extra
        report = self.scan(archive_bytes([(info, b"data")]))
        self.assertIn("unicode-path-extra", self.codes(report))

    def test_zip64_and_prepended_prefix(self):
        data = archive_bytes(["hello.txt"])
        for candidate in (
            data,
            b"executable stub\0" + data,
            zip64_end(data),
            b"executable stub\0" + zip64_end(data),
        ):
            with self.subTest(length=len(candidate)):
                report = self.scan(candidate)
                self.assertEqual(report["status"], "pass")

    def test_force_zip64_local_header(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            with archive.open("large.txt", "w", force_zip64=True) as target:
                target.write(b"actually small")
        self.assertEqual(self.scan(stream.getvalue())["status"], "pass")

    def test_zip64_central_member_extra(self):
        info = zipfile.ZipInfo("payload")
        info.extra = struct.pack("<HHQQQ", 0x0001, 24, 4, 4, 0)
        data = archive_bytes([(info, b"data")])
        for field_offset in (20, 24, 42):
            data = change_central(data, field_offset, "<I", 0xFFFFFFFF)
        report = self.scan(data)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["declared_compressed_bytes"], 4)
        self.assertEqual(report["declared_uncompressed_bytes"], 4)

    def test_eocd_signature_in_comment(self):
        comment = b"this comment contains PK\x05\x06 but no complete record"
        self.assertEqual(self.scan(archive_bytes(["a"], comment=comment))["status"], "pass")

    def test_ambiguous_complete_eocd_in_comment_does_not_hide_entries(self):
        fake = struct.pack("<4s4H2IH", b"PK\x05\x06", 0, 0, 0, 0, 0, 0, 0)
        with self.assertRaisesRegex(ScanError, "Ambiguous"):
            self.scan(archive_bytes(["../bad.txt"], comment=fake))

    def test_entry_limit_checks_actual_records(self):
        data = archive_bytes(["a", "b"])
        with self.assertRaisesRegex(ScanError, "entry limit"):
            self.scan(data, max_entries=1)
        end = data.rindex(b"PK\x05\x06")
        forged = bytearray(data)
        struct.pack_into("<HH", forged, end + 8, 1, 1)
        with self.assertRaisesRegex(ScanError, "entry limit"):
            self.scan(bytes(forged), max_entries=1)

    def test_directory_size_limit_before_large_read(self):
        data = archive_bytes(["a"])
        with self.assertRaisesRegex(ScanError, "metadata limit"):
            self.scan(data, max_metadata_bytes=10)
        end = data.rindex(b"PK\x05\x06")
        forged = bytearray(data)
        struct.pack_into("<I", forged, end + 12, 1_000_000_000)
        with self.assertRaisesRegex(ScanError, "metadata limit"):
            self.scan(bytes(forged))

    def test_mismatched_count_and_local_offset(self):
        data = archive_bytes(["a"])
        end = data.rindex(b"PK\x05\x06")
        changed = bytearray(data)
        struct.pack_into("<HH", changed, end + 8, 0, 0)
        with self.assertRaisesRegex(ScanError, "entry count"):
            self.scan(bytes(changed))
        with self.assertRaisesRegex(ScanError, "local-header offset"):
            self.scan(change_central(data, 42, "<I", 99999))

    def test_multidisk_and_truncation_rejected(self):
        data = archive_bytes(["a"])
        end = data.rindex(b"PK\x05\x06")
        changed = bytearray(data)
        struct.pack_into("<H", changed, end + 4, 1)
        for candidate in (bytes(changed), data[:-3], b"not a zip", data + b"trailer"):
            with self.subTest(candidate=candidate[-30:]):
                with self.assertRaises(ScanError):
                    self.scan(candidate)

    def test_malformed_utf8_and_extra_field_rejected(self):
        data = archive_bytes(["ascii.txt"])
        changed = bytearray(change_central(data, 8, "<H", 0x800))
        start = changed.index(b"PK\x01\x02")
        changed[start + 46] = 0xFF
        with self.assertRaisesRegex(ScanError, "invalid UTF-8"):
            self.scan(bytes(changed))
        info = zipfile.ZipInfo("a")
        info.extra = b"\x34\x12\xff\xff"
        with self.assertRaisesRegex(ScanError, "Truncated ZIP extra"):
            self.scan(archive_bytes([(info, b"")]))

    def test_invalid_limits_and_missing_file(self):
        for options in (
            {"root_length": -1},
            {"root_length": True},
            {"max_entries": 0},
            {"max_metadata_bytes": -1},
            {"target": "plan9"},
        ):
            with self.subTest(options=options):
                with self.assertRaises(ScanError):
                    self.scan(archive_bytes(), **options)
        with self.assertRaises(ScanError):
            scan_archive(Path(self.temp.name) / "missing.zip")

    def test_deep_paths_are_bounded(self):
        with self.assertRaisesRegex(ScanError, "256 path components"):
            self.scan(archive_bytes(["a/" * 256 + "file"]))

    def test_namespace_expansion_is_bounded(self):
        with self.assertRaisesRegex(ScanError, "Expanded path namespace"):
            self.scan(archive_bytes(["a/" * 80 + "file"]), max_metadata_bytes=512)

    def test_many_findings_are_capped_but_counted(self):
        data = archive_bytes([f"bad:{number}" for number in range(2005)])
        report = self.scan(data)
        self.assertEqual(report["summary"]["errors"], 2005)
        self.assertEqual(len(report["issues"]), 2001)
        self.assertEqual(report["issues"][-1]["code"], "report-truncated")

    def test_deterministic(self):
        data = archive_bytes(["Z/a", "z/b", "CON", "foo", "foo.", "a/../b"])
        self.assertEqual(self.scan(data), self.scan(data))


if __name__ == "__main__":
    unittest.main()
