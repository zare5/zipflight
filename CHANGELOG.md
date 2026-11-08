# Changelog

## 0.1.1 — 2026-11-08

- Accept valid classic ZIPs with exactly 65,535 entries without requiring a
  ZIP64 locator.
- Report ambiguous DOS directory flags even when the creator is not Unix.
- Keep errors ahead of warnings and informational notes when limiting reports,
  so a late error is not hidden by earlier metadata noise.
- Reject pipe/device inputs; POSIX FIFOs no longer wait for a writer.
- Make zipapp metadata and storage deterministic across build platforms.
- Test installed wheels, zipapps, and Windows executables away from the source
  checkout in CI; reject mislabeled Windows builds on other architectures.
- Put direct downloads and no-install demos first in both READMEs, clarify
  warning exit codes, and fix singular labels in reports.

## 0.1.0 — 2026-11-08

First public release.

- Read-only ZIP metadata checks for portable, Windows, macOS, and Linux targets.
- Findings for filename hazards, namespace collisions, path length budgets,
  and archive features that need extra care when extracting.
- Human-readable text, Markdown issue reports, and versioned JSON output.
- Configurable CI failure threshold and an offline demonstration.
- Python wheel, source distribution, standalone Python zipapp, and Windows x64
  console executable.

This is an initial release. It does not verify file data/CRCs, extract archives,
or guarantee compatibility with every filesystem or extraction program.
