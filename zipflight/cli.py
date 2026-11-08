"""Command-line interface and readable, terminal-safe reports."""

import argparse
import html
import json
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

from . import __version__
from .core import ScanError, scan_archive


def display(value):
    """Keep archive names from injecting terminal controls or bidi text."""
    return "".join(
        (f"\\u{ord(char):04x}" if unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"} else char)
        for char in str(value)
    )


def md(value):
    return html.escape(display(value), quote=True).replace("|", "&#124;")


def render_text(report):
    summary = report["summary"]
    lines = [
        f"Zipflight {__version__} | {display(report['archive'])}",
        f"{report['status'].upper()} | {report['entries']:,} entries | target: {report['target']}",
        f"{summary['errors']} errors, {summary['warnings']} warnings, {summary['infos']} notes",
        "",
    ]
    for issue in report["issues"][:100]:
        lines.append(f"{issue['severity'].upper()} [{issue['code']}] {display(issue['message'])}")
        for path in issue["paths"][:6]:
            lines.append("  " + display(json.dumps(path, ensure_ascii=False)))
        if len(issue["paths"]) > 6:
            lines.append(f"  ... and {len(issue['paths']) - 6} more paths (see JSON report)")
        lines.append("  Fix: " + display(issue["hint"]))
        lines.append("")
    if len(report["issues"]) > 100:
        lines.append("Showing the first 100 findings; --format json includes all retained findings.")
    if any(issue["code"] == "report-truncated" for issue in report["issues"]):
        lines.append(
            "Finding limit reached. Summary includes omitted findings; split the archive for full detail."
        )
    lines.append("Metadata only. File contents, CRCs, and extraction success are not verified.")
    return "\n".join(lines)


def render_markdown(report):
    summary = report["summary"]
    lines = [
        "## Zipflight report",
        "",
        f"**{report['status'].upper()}** · <code>{md(report['archive'])}</code> · "
        f"{report['entries']:,} entries · target: **{report['target']}**",
        "",
        f"{summary['errors']} errors, {summary['warnings']} warnings, {summary['infos']} notes.",
        "",
        "| Severity | Check | Paths | Finding / next step |",
        "| --- | --- | --- | --- |",
    ]
    for issue in report["issues"][:100]:
        paths = "<br>".join(f"<code>{md(path)}</code>" for path in issue["paths"][:6])
        if len(issue["paths"]) > 6:
            paths += "<br>More paths in JSON report."
        lines.append(
            f"| {issue['severity']} | {issue['code']} | {paths} | "
            f"{md(issue['message'])}<br>{md(issue['hint'])} |"
        )
    if len(report["issues"]) > 100:
        lines.extend(["", "Only the first 100 findings are shown; JSON includes all retained findings."])
    if any(issue["code"] == "report-truncated" for issue in report["issues"]):
        lines.extend(
            [
                "",
                "Finding limit reached. Summary includes omitted findings; split the archive for full detail.",
            ]
        )
    lines.extend(["", "Metadata only. File contents, CRCs, and extraction success are not verified."])
    return "\n".join(lines)


def create_demo(path):
    """Create harmless fixture entries; never extract their problematic names."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in [
            "README.txt",
            "assets/Logo.svg",
            "assets/logo.svg",
            "notes/CON.txt",
            "reports/quarter:four.txt",
            "docs",
            "docs/guide.txt",
        ]:
            archive.writestr(name, "Zipflight demo fixture.\n")


def nonnegative(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if not 0 <= number <= 32767:
        raise argparse.ArgumentTypeError("must be between 0 and 32767")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="zipflight", description="Check a ZIP before you ship it. Offline, read-only metadata checks."
    )
    parser.add_argument("archive", nargs="?", type=Path, help="local ZIP to inspect (never extracted)")
    parser.add_argument("--target", choices=["portable", "windows", "macos", "linux"], default="portable")
    parser.add_argument(
        "--root-length",
        type=nonnegative,
        default=40,
        help="estimated extraction-directory UTF-16 length, excluding final separator (default: 40)",
    )
    parser.add_argument("--format", choices=["text", "json", "markdown"], default="text")
    parser.add_argument(
        "--fail-on",
        choices=["error", "warning"],
        default="error",
        help="exit 1 on errors only, or also warnings (default: error)",
    )
    parser.add_argument(
        "--demo", action="store_true", help="inspect a temporary example ZIP with deliberate problems"
    )
    parser.add_argument("--version", action="version", version=f"zipflight {__version__}")
    args = parser.parse_args(argv)
    if bool(args.archive) == bool(args.demo):
        parser.error("provide a ZIP path or --demo, but not both")
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    try:
        if args.demo:
            with tempfile.TemporaryDirectory(prefix="zipflight-") as temporary:
                path = Path(temporary) / "demo.zip"
                create_demo(path)
                report = scan_archive(path, target=args.target, root_length=args.root_length)
        else:
            report = scan_archive(args.archive, target=args.target, root_length=args.root_length)
    except (ScanError, OSError) as exc:
        if args.format == "json":
            print(json.dumps({"schema_version": 1, "status": "error", "error": str(exc)}, ensure_ascii=True))
        else:
            print(f"zipflight: {display(exc)}", file=sys.stderr)
        return 2
    if args.format == "json":
        # ASCII escapes keep the report valid on legacy Windows code pages.
        print(json.dumps(report, indent=2, ensure_ascii=True))
    elif args.format == "markdown":
        print(render_markdown(report))
    else:
        print(render_text(report))
    return int(
        report["summary"]["errors"] > 0 or (args.fail_on == "warning" and report["summary"]["warnings"] > 0)
    )
