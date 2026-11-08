# JSON report format (schema 1)

`zipflight archive.zip --format json` writes one JSON document to stdout. JSON
uses ASCII escapes for non-ASCII characters so it also works on legacy Windows
code pages; JSON parsers restore the original characters.

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer `1`. Consumers should check this before interpreting fields. |
| `archive` | Input basename, excluding its containing directory. |
| `target` | `portable`, `windows`, `macos`, or `linux`. |
| `root_length` | Assumed destination-directory length, excluding its final separator. |
| `entries` | Number of central-directory entries, including directories. |
| `declared_compressed_bytes` | Sum of compressed sizes declared in entry metadata. |
| `declared_uncompressed_bytes` | Sum of uncompressed sizes declared in entry metadata. |
| `status` | `fail` if any error, otherwise `warn` if any warning, otherwise `pass`. |
| `summary` | Counts named `errors`, `warnings`, and `infos`. |
| `issues` | Findings with `code`, `severity`, `paths`, `message`, and `hint`. |

`paths` contains archive member names or intermediate directory paths; a conflict
can involve a directory that was never explicitly stored in the archive.
Repeated rules may overlap: counts are findings, not unique affected files.
Treat archive names as untrusted text when displaying them in another UI.

The report status describes findings independently of CLI policy: a `warn`
report exits **0** by default, **1** with `--fail-on warning`. `info` findings
never make a scan fail. An operational error exits **2** and emits:

```json
{"schema_version": 1, "status": "error", "error": "Description of the problem"}
```

Argument errors use argparse's normal stderr output rather than JSON. Do not
assume a nonzero exit always means a completed scan.

## Bounds and unsupported structures

Defaults allow at most **100,000 entries**, a **32 MiB central directory**,
**256 components per path**, and an expanded path namespace budget of **33,554,432
characters**. Oversized or unsupported metadata stops the scan with exit 2;
there is no partial passing result. API callers may set `max_entries` and
`max_metadata_bytes`; the latter also sets the expanded namespace budget.

The report retains up to **2,000 findings**, prioritizing errors, then warnings,
then informational notes. Detection order is preserved within each severity.
A later error can replace an earlier note when the report is full. A
`report-truncated` warning is added when needed; summary counts include omitted
findings. Text and Markdown show at most 100 retained findings, errors first,
and six paths per finding. JSON contains all retained findings and their paths.
Split a very noisy archive to review all details.

Common ZIP64 archives and ZIPs with prepended stubs are supported. Split/multi-disk
archives, ZIP64 extensible end records, trailing data after the ZIP end record,
and unrecognized central-directory record types are outside the initial scope.

Inputs must be regular files. Pipes and devices are rejected rather than read
as streaming ZIP input; POSIX named pipes are opened without waiting for a writer.

The scanner seeks to ZIP directory metadata and the end-record search region.
Those reads may overlap nearby data; it never opens or decompresses member
streams. No payload integrity or local-header consistency verification is
performed. Encryption, legacy encodings, and Unicode path overrides are reported
as compatibility cautions rather than silently interpreted as successful extraction.

See [checks](checks.md) for finding codes and target profiles.
