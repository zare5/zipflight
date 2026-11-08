# Checks and target profiles

These profiles describe common compatibility hazards. They do not reproduce a
specific filesystem's implementation. `portable` combines the Windows, macOS,
and Linux-oriented checks. `macos` assumes a commonly used case-insensitive
volume; `linux` assumes case-sensitive names. Neither is true of every volume.

## Names and paths

| Code | Severity | Applies to | Meaning |
| --- | --- | --- | --- |
| `empty-name` | error | all | Empty member name. |
| `nul-character` | error | all | Embedded NUL, which can terminate a name. |
| `control-character` | warning | all | ASCII control character or DEL in a name. Windows also rejects U+0001–U+001F through ordinary APIs. |
| `bidi-character` | warning | all | Bidirectional formatting characters can disguise a displayed name. |
| `absolute-path` | error | all | Leading slash; Windows profiles also check drive-qualified names. |
| `path-traversal` | error | all | A `..` path component. |
| `backslash-separator` | warning | all | Backslash can be a separator or a literal character depending on the extractor. |
| `noncanonical-path` | warning | all | Dot components or repeated separators. |
| `windows-forbidden-character` | error | Windows, portable | Characters forbidden in ordinary Windows names. |
| `windows-reserved-name` | error | Windows, portable | Device names, including names with extensions and numbered COM/LPT forms. |
| `windows-trailing-character` | error | Windows, portable | A component ends in a dot or space. |
| `windows-component-length` | error | Windows, portable | A component exceeds 255 UTF-16 code units. |
| `windows-path-length` | warning | Windows, portable | Estimated destination path reaches 260 UTF-16 units. Some applications support longer paths. |
| `utf8-component-length` | warning | Linux, macOS, portable | A component exceeds 255 UTF-8 bytes, a common filesystem limit. This is a conservative advisory check on macOS. |

## Collisions

| Code | Severity | Applies to | Meaning |
| --- | --- | --- | --- |
| `duplicate-entry` | error | all | Several members have the exact same stored name. |
| `path-alias-collision` | error | all | Different stored names collapse after separator/dot-component handling. |
| `file-directory-conflict` | error | all | A path is used as both a file and a directory, including an implicit parent. |
| `windows-trim-collision` | error | Windows, portable | Different paths become identical after trailing spaces/dots are removed. |
| `unicode-normalization-collision` | warning | macOS, portable | Paths become identical under NFC normalization. |
| `case-collision` | warning | Windows, macOS, portable | Paths compare equal under full Unicode case folding (plus NFC in macOS/portable). |
| `windows-alias-collision` | warning | Windows, portable | Combined trimming and case folding reveals an additional alias. |

Collisions include intermediate directories: `Docs/a.txt` and `docs/b.txt`
may merge two trees even though their leaf filenames differ. Case folding is
intentionally advisory: for example, Python's full case fold can equate names
that a particular Windows filesystem keeps distinct. NFC is also an
approximation of macOS filesystem normalization. Choose `--fail-on warning`
when those conservative findings should block CI.

## Archive metadata

| Code | Severity | Meaning |
| --- | --- | --- |
| `symlink-entry` | warning | Unix metadata marks a symbolic link; its target is not inspected. |
| `special-file-entry` | warning | Unix metadata marks a device, socket, FIFO, or another non-regular type. |
| `conflicting-file-type` | warning | Name suffix, DOS flags, or Unix type metadata disagree about file/directory type. |
| `encrypted-entry` | warning | Encryption flags require suitable extractor/password support. |
| `compression-method` | warning | Method other than Store (0) or Deflate (8); broad support cannot be assumed. |
| `legacy-name-encoding` | warning | Non-ASCII name lacks the UTF-8 flag. The report uses ZIP's CP437 fallback; original encoding is not guessed. |
| `unicode-path-extra` | warning | Unicode path override differs from the central name. Collision checks use the central name only. |
| `declared-compression-ratio` | warning | Declared uncompressed size exceeds 100 MiB and ratio exceeds 1000:1. This is not a ZIP bomb detector. |
| `os-metadata` | info | Names such as `__MACOSX`, `.DS_Store`, `._*`, `Thumbs.db`, and `desktop.ini`. |
| `report-truncated` | warning | Finding cap reached. Counts still include omitted findings. |

No compressed member data is opened or decompressed, so CRC errors, truncated
payloads, conflicting local headers, nested content, and symbolic-link targets
are outside these checks. See [report format and limits](report-format.md).

References: [Microsoft filename conventions](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file),
[PKWARE ZIP specification](https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT),
[Python Unicode normalization](https://docs.python.org/3/library/unicodedata.html#unicodedata.normalize).
