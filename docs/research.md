# Why Zipflight exists

Research checked on **2026-11-08**. This is a small collection of public problem reports and related tools, not a market-size study or proof that the idea is unique.

The workflow we chose is simple: **check a local ZIP before sharing it or attaching it to a release**. A successful build on one operating system does not tell the publisher whether names inside the archive will work on a recipient's system. Zipflight makes those names and relevant archive metadata reviewable without extracting files.

## Evidence that informed the scope

| Source | Date | Reported problem | What it supports |
| --- | --- | --- | --- |
| [BaSyx server SDK #999](https://github.com/eclipse-basyx/basyx-java-server-sdk/issues/999) | Opened 2026-04-20; closed 2026-07-19 | A Windows user reported both long-path checkout errors and a GitHub source ZIP that Explorer would not open. The maintainer recommended 7-Zip and a short extraction directory. | Long paths can become a distribution problem before the software runs. This issue already has a workaround; Zipflight does not claim to fix it. |
| [PowerShell community: Expand-Archive fails on filenames](https://www.reddit.com/r/PowerShell/comments/1g19m6k/expandarchive_fails_to_unzip_due_to_filenames/) | Older discussion; checked 2026-11-08 | A user asked how to inspect problematic names inside several ZIPs before batch extraction failed. Colon-containing names were part of the report. | An archive-first check is a concrete workflow users have requested. This is historical evidence, not a new 2026 incident. |
| [libarchive #3063](https://github.com/libarchive/libarchive/issues/3063) | Opened 2026-05-23 | A Windows extraction regression affected ZIPs containing UTF-8 names. | Extractor behavior also matters. This is adjacent evidence: Zipflight cannot predict or repair every extractor regression. |
| [Kopia #5634](https://github.com/kopia/kopia/issues/5634) | Opened 2026-09-10 | Mounting or restoring names with trailing spaces or colons failed on Windows. | These name hazards still affect current cross-platform transfers. The report concerns backup restoration, not ZIP extraction. |
| [huggingface_hub #4912](https://github.com/huggingface/huggingface_hub/issues/4912) | Opened 2026-09-15; closed as not planned when checked | A user reported trailing-dot/space names being renamed and colliding on Windows. | Reviewing individual names alone can miss collisions. This is a download-path report, not a ZIP report. |

These reports establish examples of friction. They do not establish how frequently it happens, whether affected users would adopt this tool, or whether those users endorse Zipflight.

## Why keep it small?

The initial audience is maintainers sharing ZIP releases, people exchanging folders between operating systems, and CI pipelines that need a readable report about a finished archive. The intended output is a list of findings with reasons, available as text, JSON, or Markdown.

The project stays local and read-only. It does not need a service, an account, a model, or access to a private repository. It does not rename entries or select a legacy filename encoding on the user's behalf.

## Existing work and boundaries

[Treeport](https://github.com/rad1092/treeport) already provides a direct alternative: it checks ZIPs as well as folders and Git paths against destination profiles. Other tools repair archives, validate payload integrity, or enforce extraction policies. See [alternatives](alternatives.md) before choosing a tool. Zipflight's proposition is a focused Python ZIP preflight and reports, not an uncontested category.

Case folding and Unicode normalization are advisory models, not exact simulations of every filesystem. Path limits depend on the destination directory, filesystem, application, and system configuration. Metadata can be inconsistent with payloads or local headers. A metadata-only check does not verify CRCs, decompress entries, inspect nested archives, validate symbolic-link targets, scan for malware, or certify safe extraction. A clean report means only that the implemented checks found no reportable issue.
