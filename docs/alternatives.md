# Related tools

Checked on **2026-11-08** against the linked project documentation. This is a workflow comparison, not a performance benchmark or an exhaustive survey. Features may change.

| Tool | Documented focus | When to use it |
| --- | --- | --- |
| **Zipflight** | Read-only checks of local ZIP names and archive metadata, with text, JSON, and Markdown reports. | You want a small Python tool to review an archive before sharing it or in CI. |
| [Treeport](https://github.com/rad1092/treeport) | A Go library and CLI for folders, ZIPs, Git paths, and JSONL input; destination profiles, collision checks, destination-root path budgets, and CI integration. | You need broader filename portability checks. This is a direct alternative with substantial overlap. |
| [zipkirei](https://github.com/yuk7/zipkirei) | Repairs UTF-8 filename flags, normalizes Unicode and path separators, and removes OS metadata entries without extraction or recompression. Includes a dry-run mode. | You want to preview or apply supported archive repairs. Review its repair rules before changing an archive. |
| [safe_unzip](https://github.com/tenuo-ai/safe_unzip) | Rust/Python extraction library and CLI with traversal, symlink, and resource-limit protections; also provides listing and integrity verification. | You need to extract untrusted archives under an explicit extraction policy. |
| [portacheck](https://github.com/calasdan-sketch/portacheck) ([PyPI](https://pypi.org/project/portacheck/)) | Scans a repository directory for Windows filename hazards, case collisions, and long paths; JSON output and CI exit codes. | You want to catch problems in a source tree before packaging. |
| [Info-ZIP UnZip / ZipInfo](https://infozip.sourceforge.net/UnZip.html) | Lists archive contents and metadata; `unzip -t` tests compressed data and CRCs. | You need an established archive listing or payload-integrity check. |

These tools can complement one another. Run a metadata preflight before publishing; use an integrity test when you need to check stored data; use an extractor with appropriate defenses when unpacking untrusted input.

Zipflight does not replace those last two steps. It reads archive metadata without opening or decompressing member streams. Its bounded search for end records can overlap payload bytes in a small archive. Filename collision checks use an approximation of case-insensitive and normalization-sensitive behavior. A report is neither a guarantee that every extractor will accept the archive nor a security certification.
