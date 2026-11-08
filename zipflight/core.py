"""Bounded, read-only ZIP central-directory inspection.

This module never opens member streams. Findings are compatibility diagnostics,
not a claim about payload integrity, malware, or extraction safety.
"""

from __future__ import annotations

import os
import re
import stat
import struct
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO


class ScanError(Exception):
    """The archive could not be inspected within the supported metadata limits."""


@dataclass(frozen=True)
class _Entry:
    name: str
    flags: int
    method: int
    compressed: int
    uncompressed: int
    external: int
    creator: int
    unicode_name: str | None = None

    @property
    def directory(self) -> bool:
        return (
            self.name.endswith("/")
            or bool(self.external & 0x10)
            or (self.creator == 3 and stat.S_ISDIR(self.external >> 16))
        )


_EOCD = struct.Struct("<4s4H2IH")
_CENTRAL = struct.Struct("<4s6H3I5H2I")
_ZIP64 = struct.Struct("<4sQ2H2I4Q")
_LOCATOR = struct.Struct("<4sIQI")
_TARGETS = {"portable", "windows", "macos", "linux"}
_BIDI = set("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")
_WINDOWS_BAD = set('<>:"|?*')
_DEVICE = re.compile(r"^(?:CON|PRN|AUX|NUL|CONIN\$|CONOUT\$|COM[1-9¹²³]|LPT[1-9¹²³])$", re.I)
_MAX_ISSUES = 2000


def _read_at(stream: BinaryIO, offset: int, length: int) -> bytes:
    if offset < 0:
        raise ScanError("Invalid ZIP metadata offset.")
    stream.seek(offset)
    data = stream.read(length)
    if len(data) != length:
        raise ScanError("Truncated ZIP metadata.")
    return data


def _directory_location(stream: BinaryIO, size: int, limit: int) -> tuple[int, int, int, int]:
    # EOCD comments are limited to 65,535 bytes by the ZIP format. Searching only
    # this tail also prevents an attacker-controlled directory size being read.
    tail_start = max(0, size - 65535 - _EOCD.size)
    tail = _read_at(stream, tail_start, size - tail_start)
    cursor = len(tail)
    record = None
    record_cursor = None
    while True:
        cursor = tail.rfind(b"PK\x05\x06", 0, cursor)
        if cursor < 0:
            break
        if cursor + _EOCD.size <= len(tail):
            candidate = _EOCD.unpack_from(tail, cursor)
            if cursor + _EOCD.size + candidate[-1] == len(tail):
                if record is not None:
                    raise ScanError(
                        "Ambiguous end-of-central-directory records (possibly inside a ZIP comment)."
                    )
                record = candidate
                record_cursor = cursor
    if record is None:
        raise ScanError("ZIP end-of-central-directory record not found (trailing data is unsupported).")
    _, disk, cd_disk, disk_count, count, cd_size, cd_offset, _ = record
    eocd_offset = tail_start + record_cursor
    central_end = eocd_offset
    if disk != 0 or cd_disk != 0:
        raise ScanError("Multi-disk ZIP archives are unsupported.")

    locator = _read_at(stream, eocd_offset - 20, 20) if eocd_offset >= 20 else b""
    has_zip64 = locator.startswith(b"PK\x06\x07")
    requires_zip64 = count == 0xFFFF or cd_size == 0xFFFFFFFF or cd_offset == 0xFFFFFFFF
    if requires_zip64 and not has_zip64:
        raise ScanError("ZIP64 metadata is missing its locator.")
    if has_zip64:
        _, zip64_disk, declared_zip64_offset, total_disks = _LOCATOR.unpack(locator)
        if zip64_disk != 0 or total_disks != 1:
            raise ScanError("Multi-disk ZIP64 archives are unsupported.")
        # Common ZIP64 records have a 44-byte body. An extensible data sector is
        # deliberately unsupported instead of scanning an unbounded region.
        zip64_offset = eocd_offset - 20 - _ZIP64.size
        z = _ZIP64.unpack(_read_at(stream, zip64_offset, _ZIP64.size))
        if z[0] != b"PK\x06\x06" or z[1] != 44:
            raise ScanError("ZIP64 extensible or malformed end records are unsupported.")
        if z[4] != 0 or z[5] != 0 or z[6] != z[7]:
            raise ScanError("Multi-disk or inconsistent ZIP64 entry counts are unsupported.")
        count, cd_size, cd_offset = z[7], z[8], z[9]
        central_end = zip64_offset
        if declared_zip64_offset > zip64_offset:
            raise ScanError("Invalid ZIP64 locator offset.")
    elif disk_count != count:
        raise ScanError("Inconsistent ZIP central-directory entry counts.")
    if cd_size > limit:
        raise ScanError(f"Central directory exceeds the {limit:,}-byte metadata limit.")
    start = central_end - cd_size
    if start < 0 or cd_offset > start:
        raise ScanError("Invalid ZIP central-directory offset or size.")
    # Offsets in a normal ZIP can omit a prepended executable/stub. Adjusting by
    # this prefix supports self-extracting and concatenated-prefix ZIPs.
    prefix = start - cd_offset
    if has_zip64 and declared_zip64_offset + prefix != central_end:
        raise ScanError("ZIP64 locator offset does not match the end record.")
    return start, cd_size, count, prefix


def _extras(data: bytes) -> dict[int, bytes]:
    fields: dict[int, bytes] = {}
    offset = 0
    while offset < len(data):
        if offset + 4 > len(data):
            raise ScanError("Truncated ZIP extra-field header.")
        kind, length = struct.unpack_from("<HH", data, offset)
        offset += 4
        if offset + length > len(data):
            raise ScanError("Truncated ZIP extra field.")
        if kind in fields and kind in (0x0001, 0x7075):
            raise ScanError("Ambiguous duplicate ZIP64 or Unicode path extra field.")
        fields[kind] = data[offset : offset + length]
        offset += length
    return fields


def _read_entries(stream: BinaryIO, size: int, max_entries: int, max_metadata: int) -> list[_Entry]:
    start, length, declared_count, prefix = _directory_location(stream, size, max_metadata)
    if declared_count > max_entries:
        raise ScanError(f"Archive exceeds the {max_entries:,}-entry limit.")
    data = _read_at(stream, start, length)
    entries = []
    offset = 0
    while offset < len(data):
        if len(entries) >= max_entries:
            raise ScanError(f"Central directory exceeds the {max_entries:,}-entry limit.")
        if offset + _CENTRAL.size > len(data):
            raise ScanError("Truncated central-directory record.")
        c = _CENTRAL.unpack_from(data, offset)
        if c[0] != b"PK\x01\x02":
            raise ScanError("Unsupported record in ZIP central directory.")
        (
            _,
            made,
            _needed,
            flags,
            method,
            _time,
            _date,
            _crc,
            compressed,
            uncompressed,
            nlen,
            xlen,
            clen,
            disk,
            _internal,
            external,
            local_offset,
        ) = c
        end = offset + _CENTRAL.size + nlen + xlen + clen
        if end > len(data):
            raise ScanError("Truncated central-directory name, extra field, or comment.")
        raw_name = data[offset + _CENTRAL.size : offset + _CENTRAL.size + nlen]
        extra = _extras(data[offset + _CENTRAL.size + nlen : offset + _CENTRAL.size + nlen + xlen])
        z64 = extra.get(0x0001, b"")
        zi = 0
        values = [uncompressed, compressed, local_offset, disk]
        for index, width in enumerate((8, 8, 8, 4)):
            sentinel = 0xFFFF if index == 3 else 0xFFFFFFFF
            if values[index] == sentinel:
                if zi + width > len(z64):
                    raise ScanError("Missing or truncated ZIP64 member metadata.")
                values[index] = int.from_bytes(z64[zi : zi + width], "little")
                zi += width
        uncompressed, compressed, local_offset, disk = values
        if disk != 0:
            raise ScanError("Multi-disk ZIP members are unsupported.")
        if local_offset + prefix >= start:
            raise ScanError("Member local-header offset points into the central directory.")
        try:
            name = raw_name.decode("utf-8" if flags & 0x800 else "cp437")
        except UnicodeDecodeError as exc:
            raise ScanError("A ZIP member is marked UTF-8 but its filename is invalid UTF-8.") from exc
        unicode_name = None
        if 0x7075 in extra:
            value = extra[0x7075]
            if len(value) >= 5 and value[0] == 1:
                try:
                    unicode_name = value[5:].decode("utf-8")
                except UnicodeDecodeError:
                    unicode_name = "<invalid Unicode path extra field>"
            else:
                unicode_name = "<unsupported Unicode path extra field>"
        entries.append(
            _Entry(name, flags, method, compressed, uncompressed, external, made >> 8, unicode_name)
        )
        offset = end
    if len(entries) != declared_count:
        raise ScanError("Declared ZIP entry count does not match the central directory.")
    return entries


def _utf16len(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def scan_archive(
    path: str | os.PathLike[str],
    *,
    target: str = "portable",
    root_length: int = 40,
    max_entries: int = 100000,
    max_metadata_bytes: int = 33554432,
) -> dict:
    """Inspect ZIP metadata without opening/decompressing any member payload.

    ``root_length`` is the UTF-16 length of the destination directory, excluding
    its final separator. Case folding is conservative, not a filesystem emulator.
    At most 2,000 findings are emitted; summary counts include omitted findings.
    """
    if target not in _TARGETS:
        raise ScanError(f"Unknown target {target!r}; choose portable, windows, macos, or linux.")
    if isinstance(root_length, bool) or not isinstance(root_length, int) or root_length < 0:
        raise ScanError("root_length must be a nonnegative integer.")
    for label, value in (("max_entries", max_entries), ("max_metadata_bytes", max_metadata_bytes)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ScanError(f"{label} must be a positive integer.")
    try:
        with open(path, "rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            entries = _read_entries(stream, size, max_entries, max_metadata_bytes)
    except ScanError:
        raise
    except (OSError, ValueError, struct.error, OverflowError) as exc:
        raise ScanError(f"Cannot inspect ZIP archive: {exc}") from exc

    issues: list[dict] = []
    counts = {"errors": 0, "warnings": 0, "infos": 0}
    omitted = 0

    def add(code: str, severity: str, paths: list[str], message: str, hint: str) -> None:
        nonlocal omitted
        counts[{"error": "errors", "warning": "warnings", "info": "infos"}[severity]] += 1
        item = {"code": code, "severity": severity, "paths": paths, "message": message, "hint": hint}
        if len(issues) < _MAX_ISSUES:
            issues.append(item)
        else:
            omitted += 1

    windows = target in ("portable", "windows")
    unix_names = target in ("portable", "linux", "macos")
    case_sensitive = target == "linux"
    normalize = target in ("portable", "macos")
    originals: dict[str, list[_Entry]] = defaultdict(list)
    # Node maps include implicit parent directories. Keeping node spellings
    # exposes Docs/a + docs/b directory aliases, not just leaf-name collisions.
    nodes: dict[str, set[str]] = defaultdict(set)
    node_examples: dict[tuple[str, str], str] = {}
    canonical_leaves: dict[str, set[str]] = defaultdict(set)
    namespace_chars = 0

    for entry in entries:
        name = entry.name
        originals[name].append(entry)
        display = [name]
        path_text = name.replace("\\", "/") if windows else name
        parts = path_text.split("/")
        if not name:
            add(
                "empty-name",
                "error",
                display,
                "A member has an empty filename.",
                "Recreate the archive with a nonempty member name.",
            )
        if "\x00" in name:
            add(
                "nul-character",
                "error",
                display,
                "A filename contains NUL; extractors may truncate it.",
                "Remove NUL characters before creating the archive.",
            )
        if any(ord(c) < 32 or ord(c) == 127 for c in name if c != "\x00"):
            add(
                "control-character",
                "warning",
                display,
                "A filename contains control characters.",
                "Use visible printable characters for reliable tooling and display.",
            )
        if any(c in _BIDI for c in name):
            add(
                "bidi-character",
                "warning",
                display,
                "A filename contains bidirectional formatting characters.",
                "Review its escaped spelling; these characters can disguise the displayed name.",
            )
        if path_text.startswith("/") or (windows and re.match(r"^[A-Za-z]:", path_text)):
            add(
                "absolute-path",
                "error",
                display,
                "A member uses an absolute or drive-qualified path.",
                "Store relative paths inside the archive.",
            )
        if ".." in parts:
            add(
                "path-traversal",
                "error",
                display,
                "A member contains a parent-directory (..) segment.",
                "Recreate the archive using paths relative to one root directory.",
            )
        if "\\" in name:
            add(
                "backslash-separator",
                "warning",
                display,
                "Backslashes may be treated as separators or literal filename characters.",
                "ZIP member paths should use forward slashes.",
            )
        clean = [p for p in parts if p not in ("", ".")]
        if len(clean) > 256:
            raise ScanError("A member exceeds the supported limit of 256 path components.")
        if "." in parts or "//" in path_text:
            add(
                "noncanonical-path",
                "warning",
                display,
                "A path has repeated separators or dot segments.",
                "Normalize member paths before creating the archive.",
            )
        if windows:
            if any(any(c in _WINDOWS_BAD or ord(c) < 32 for c in p) for p in clean):
                add(
                    "windows-forbidden-character",
                    "error",
                    display,
                    "A path component contains a character forbidden by ordinary Windows file APIs.",
                    'Avoid < > : " | ? * in names; use / only as a ZIP directory separator.',
                )
            if any(_DEVICE.fullmatch(p.split(".", 1)[0].rstrip(" ")) for p in clean):
                add(
                    "windows-reserved-name",
                    "error",
                    display,
                    "A path component is a reserved Windows device name.",
                    "Rename the component, including names such as CON.txt or COM1.",
                )
            if any(p.endswith((".", " ")) for p in clean):
                add(
                    "windows-trailing-character",
                    "error",
                    display,
                    "A path component ends in a dot or space and may be rejected or silently renamed.",
                    "Remove trailing dots/spaces and check for resulting name collisions.",
                )
            if any(_utf16len(p) > 255 for p in clean):
                add(
                    "windows-component-length",
                    "error",
                    display,
                    "A component exceeds 255 UTF-16 code units.",
                    "Shorten the filename or directory component.",
                )
            total = root_length + 1 + _utf16len(path_text.rstrip("/"))
            if total >= 260:
                add(
                    "windows-path-length",
                    "warning",
                    display,
                    f"Estimated destination path is {total} UTF-16 code units (legacy limit: 259).",
                    "Use a shorter destination/name or a long-path-aware extractor; application limits vary.",
                )
        if unix_names and any(len(p.encode("utf-8")) > 255 for p in clean):
            add(
                "utf8-component-length",
                "warning",
                display,
                "A component exceeds 255 UTF-8 bytes, a common Linux/filesystem limit.",
                "Shorten the component; byte limits differ by filesystem and normalization.",
            )
        if entry.creator == 3 and stat.S_ISLNK(entry.external >> 16):
            add(
                "symlink-entry",
                "warning",
                display,
                "Unix metadata marks this member as a symbolic link.",
                "Extractor support differs; link targets are payload data and were not inspected.",
            )
        elif entry.creator == 3 and stat.S_IFMT(entry.external >> 16) not in (0, stat.S_IFREG, stat.S_IFDIR):
            add(
                "special-file-entry",
                "warning",
                display,
                "Unix metadata marks this member as a special file.",
                "Check extractor behavior before using device, socket, or FIFO metadata.",
            )
        if entry.creator == 3:
            unix_kind = stat.S_IFMT(entry.external >> 16)
            if (unix_kind in (stat.S_IFREG, stat.S_IFLNK) and entry.directory) or (
                unix_kind == stat.S_IFDIR and not name.endswith("/")
            ):
                add(
                    "conflicting-file-type",
                    "warning",
                    display,
                    "The filename, DOS attributes, and Unix file type do not consistently identify a file or directory.",
                    "Recreate the archive with consistent file-type metadata; extractors may choose different interpretations.",
                )
        if entry.flags & (1 | 64):
            add(
                "encrypted-entry",
                "warning",
                display,
                "This member is marked encrypted.",
                "Confirm the recipient's extractor supports the encryption; no password or payload was tested.",
            )
        if entry.method not in (0, 8):
            add(
                "compression-method",
                "warning",
                display,
                f"Compression method {entry.method} is less widely supported than Store (0) or Deflate (8).",
                "Use Deflate for broad compatibility or confirm the recipient's extractor supports this method.",
            )
        if not entry.flags & 0x800 and any(ord(c) > 127 for c in name):
            add(
                "legacy-name-encoding",
                "warning",
                display,
                "A non-ASCII filename lacks the UTF-8 flag; this report decodes it as CP437.",
                "Recreate the archive with UTF-8 filenames; legacy code-page assumptions vary by extractor.",
            )
        if entry.unicode_name is not None and entry.unicode_name != name:
            add(
                "unicode-path-extra",
                "warning",
                [name, entry.unicode_name],
                "A Unicode path extra field differs from the central filename; extractors may choose different names.",
                "This report checks the central filename only. Recreate with matching UTF-8 names and no conflicting override.",
            )
        if entry.uncompressed > 100 * 1024 * 1024 and entry.uncompressed > 1000 * max(1, entry.compressed):
            add(
                "declared-compression-ratio",
                "warning",
                display,
                "Declared size exceeds 100 MiB and the declared compression ratio exceeds 1000:1.",
                "Check expected sizes and extraction resources; these metadata values were not verified against the payload.",
            )
        if any(
            p == "__MACOSX"
            or p == ".DS_Store"
            or p.startswith("._")
            or p.lower() in ("thumbs.db", "desktop.ini")
            for p in clean
        ):
            add(
                "os-metadata",
                "info",
                display,
                "This path resembles operating-system metadata.",
                "Exclude it when creating an archive if the recipient does not need it.",
            )
        for i in range(1, len(clean) + 1):
            node = "/".join(clean[:i])
            if node not in nodes:
                namespace_chars += len(node)
                if namespace_chars > max_metadata_bytes:
                    raise ScanError("Expanded path namespace exceeds the metadata limit.")
            kind = "directory" if i < len(clean) or entry.directory else "file"
            nodes[node].add(kind)
            node_examples.setdefault((node, kind), name)
        if clean:
            canonical_leaves["/".join(clean)].add(name.rstrip("/"))

    for name, group in sorted(originals.items()):
        if len(group) > 1:
            add(
                "duplicate-entry",
                "error",
                [name],
                f"The archive contains {len(group)} members with this exact name.",
                "Keep one unambiguous member per path; overwrite behavior depends on the extractor.",
            )
    for name, kinds in sorted(nodes.items()):
        if len(kinds) > 1:
            paths = sorted({node_examples[(name, kind)] for kind in kinds})
            add(
                "file-directory-conflict",
                "error",
                paths,
                "This path must be both a file and a directory (possibly an implicit parent).",
                "Rename the file or the directory tree so both can exist.",
            )
    for group in sorted(sorted(group) for group in canonical_leaves.values() if len(group) > 1):
        add(
            "path-alias-collision",
            "error",
            group,
            "Different member names resolve to the same path after separator/dot normalization.",
            "Keep one member per normalized relative path.",
        )

    emitted_groups: set[tuple[str, ...]] = set()

    def collisions(code: str, key, message: str, severity: str = "warning") -> None:
        groups: dict[str, list[str]] = defaultdict(list)
        for name in nodes:
            groups[key(name)].append(name)
        for group in sorted((sorted(g) for g in groups.values() if len(g) > 1)):
            if code == "windows-alias-collision" and tuple(group) in emitted_groups:
                continue
            add(
                code,
                severity,
                group,
                message,
                "Choose distinct names under the target's path rules; directory aliases can merge separate trees.",
            )
            emitted_groups.add(tuple(group))

    if windows:
        collisions(
            "windows-trim-collision",
            lambda n: "/".join(p.rstrip(" .") for p in n.split("/")),
            "Paths become identical when Windows strips trailing dots/spaces.",
            "error",
        )
    if normalize:
        collisions(
            "unicode-normalization-collision",
            lambda n: unicodedata.normalize("NFC", n),
            "Paths become identical after Unicode NFC normalization.",
        )
    if not case_sensitive:
        # Unicode full casefold intentionally errs on the side of reporting.
        # It is not NTFS/APFS's exact comparison algorithm (for example ß/ss).
        collisions(
            "case-collision",
            lambda n: unicodedata.normalize("NFC", n).casefold() if normalize else n.casefold(),
            "Paths may alias on case-insensitive filesystems (conservative Unicode case folding).",
        )
        if windows:
            collisions(
                "windows-alias-collision",
                lambda n: "/".join(p.rstrip(" .").casefold() for p in n.split("/")),
                "Paths may alias after Windows trailing-character handling and conservative case folding.",
            )
    if omitted:
        counts["warnings"] += 1
        issues.append(
            {
                "code": "report-truncated",
                "severity": "warning",
                "paths": [],
                "message": f"{omitted:,} additional findings omitted; summary includes them.",
                "hint": "Split the archive into smaller groups to inspect every finding.",
            }
        )
    return {
        "schema_version": 1,
        "archive": Path(path).name,
        "target": target,
        "root_length": root_length,
        "entries": len(entries),
        "declared_compressed_bytes": sum(e.compressed for e in entries),
        "declared_uncompressed_bytes": sum(e.uncompressed for e in entries),
        "issues": issues,
        "summary": counts,
        "status": "fail" if counts["errors"] else "warn" if counts["warnings"] else "pass",
    }
