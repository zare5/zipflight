<p align="center">
  <img src="docs/assets/banner.svg" alt="Zipflight — check a ZIP before you ship it. Catch filename problems before extraction." width="100%">
</p>

<p align="center">
  <a href="https://github.com/zare5/zipflight/actions/workflows/ci.yml"><img src="https://github.com/zare5/zipflight/actions/workflows/ci.yml/badge.svg" alt="Tests"></a>
  <a href="https://github.com/zare5/zipflight/releases"><img src="https://img.shields.io/github/v/release/zare5/zipflight" alt="Release"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776ab" alt="Python 3.10 or newer">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-82e4c4" alt="MIT license"></a>
</p>

<p align="center"><a href="README.zh-CN.md">简体中文</a> · <a href="#try-it">Try it</a> · <a href="#what-it-checks">Checks</a> · <a href="#reports-and-ci">Reports &amp; CI</a> · <a href="#related-tools">Alternatives</a></p>

# Zipflight — ZIP portability checker

**Catch filenames that may fail or overwrite one another when a ZIP moves between Windows, macOS, and Linux.**

A valid ZIP can contain `CON.txt`, both `Readme.md` and `README.md`, or a file named `assets` alongside `assets/logo.png`. Zipflight explains these conflicts before you publish a release or send an archive to a client.

It runs offline, reads archive metadata, and gives you actionable text, Markdown, or JSON reports. **It never extracts or changes your archive.** The Python version uses only the standard library.

## Try it

No package installation or Git required. Download the file for your environment, then open a terminal **in the folder containing the download**.

**Python 3.10+ · Windows, macOS, Linux:** download [zipflight.pyz](https://github.com/zare5/zipflight/releases/download/v0.1.1/zipflight.pyz).

```sh
python zipflight.pyz --demo
```

Use `python3` instead of `python` if that is your system's Python command.

**Windows x64 · no Python needed:** download [zipflight-windows-x64.exe](https://github.com/zare5/zipflight/releases/download/v0.1.1/zipflight-windows-x64.exe), then use PowerShell:

```powershell
.\zipflight-windows-x64.exe --demo
```

The demo scans a temporary ZIP with deliberate problems, removes it afterwards, and exits **1**. This is expected. It never extracts the example entries. The Windows executable is an unsigned console program.

Actual demo output, with other findings omitted:

```text
Zipflight 0.1.1 | demo.zip
FAIL | 7 entries | target: portable

ERROR [windows-reserved-name] A path component is a reserved Windows device name.
  "notes/CON.txt"
  Fix: Rename the component, including names such as CON.txt or COM1.

ERROR [file-directory-conflict] This path must be both a file and a directory (possibly an implicit parent).
  "docs"
  "docs/guide.txt"
  Fix: Rename the file or the directory tree so both can exist.
```

Replace `--demo` with a ZIP path to check your own archive:

```sh
python zipflight.pyz "path/to/archive.zip" --target windows
```

The executable accepts the same arguments. All downloads and checksums are on the [release page](https://github.com/zare5/zipflight/releases/tag/v0.1.1).

### Install the command

For repeated use, install the published wheel with Python 3.10+; Git is not needed:

```sh
python -m pip install "https://github.com/zare5/zipflight/releases/download/v0.1.1/zipflight-0.1.1-py3-none-any.whl"
python -m zipflight archive.zip
```

After installation, `zipflight` is also available as a command. Examples below use that shorter form. There is no PyPI release yet.

## What it checks

| Problem | Example entries |
| --- | --- |
| Windows device names, invalid characters, trailing dots/spaces | `CON.txt`, `notes:final.txt`, `report.` |
| Case, Unicode, and path aliases | `Readme.md` + `README.md`; two Unicode spellings of `café.txt` |
| Duplicate entries and file/directory conflicts | Two `data.csv` entries; `assets` + `assets/logo.png` |
| Absolute paths, traversal, ambiguous separators | `../outside.txt`, `/root/file`, backslashes |
| Filename and destination-path lengths | A deep folder tree under a long extraction directory |
| Extractor compatibility and metadata cautions | Encryption, symlinks, unusual compression, legacy encodings, OS junk |

Control/bidirectional characters and extreme declared expansion ratios also produce findings. See [all checks and severities](docs/checks.md).

### Target profiles and path length

The default `portable` profile combines the platform checks. To focus on a recipient's system:

```sh
zipflight archive.zip --target windows
zipflight archive.zip --target macos
zipflight archive.zip --target linux
```

Windows path-length warnings assume a destination directory of **40 UTF-16 code units**, excluding its final separator. Use a larger estimate for a deeper folder:

```sh
zipflight archive.zip --target windows --root-length 80
```

Zipflight adds one separator and the entry's path length. The resulting legacy-path warning is advisory; long-path-aware tools may work beyond that limit.

## Reports and CI

```sh
zipflight archive.zip --format markdown > zip-report.md
zipflight archive.zip --format json > zip-report.json
zipflight archive.zip --fail-on warning
```

Errors fail the command by default. `--fail-on warning` also fails on warnings, including conservative case/Unicode collision checks.

| Exit | Meaning |
| --- | --- |
| `0` | No finding reached the selected failure threshold. |
| `1` | The scan completed and found an error, or a warning under `--fail-on warning`. |
| `2` | The scan could not complete, or arguments were invalid. |

A report marked `WARN` can therefore exit **0** under the default policy. See the [JSON schema, error responses, and output limits](docs/report-format.md). Reports contain filenames; review them before sharing.

<details>
<summary>GitHub Actions: check a ZIP after your build</summary>

Add these steps after the step that creates `dist/release.zip`:

```yaml
- uses: actions/setup-python@v7.1.0
  with:
    python-version: '3.12'
- run: python -m pip install "https://github.com/zare5/zipflight/releases/download/v0.1.1/zipflight-0.1.1-py3-none-any.whl"
- run: python -m zipflight dist/release.zip --target portable --fail-on warning
```

</details>

## Scope

**This is a metadata check, not an integrity test or a security guarantee.** It does not verify file contents, CRCs, local-header agreement, nested archives, available disk space, or extraction success. It does not repair names. Declared sizes and expansion ratios are not verified against payloads.

Case and Unicode comparisons approximate filesystem behavior; the profiles do not emulate a particular filesystem or extractor. A clean report means no implemented check fired. [Documented bounds](docs/report-format.md#bounds-and-unsupported-structures) limit entries, metadata, path depth, and retained findings; oversized or unsupported metadata stops the scan.

## Related tools

| If you need… | Consider |
| --- | --- |
| Portability checks for folders, Git paths, and ZIPs | [Treeport](https://github.com/rad1092/treeport), a direct alternative with broader input support and substantial overlap. |
| Previewing or applying supported ZIP filename/encoding repairs | [zipkirei](https://github.com/yuk7/zipkirei). |
| Testing compressed data and CRCs | `unzip -t` or your archive manager's integrity test. |

Zipflight's focus is a small Python tool for **local ZIP reports before sharing or releasing**. See the [full comparison](docs/alternatives.md) and [demand research](docs/research.md).

## Contribute

Found a missed collision or a false positive? [Open an issue](https://github.com/zare5/zipflight/issues/new/choose) with the target profile, finding code, and minimal filenames. You do not need to upload a private archive.

[Development and tests](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [MIT license](LICENSE)
