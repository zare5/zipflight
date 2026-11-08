# Changelog

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
