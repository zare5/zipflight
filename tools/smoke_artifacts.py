"""Exercise built artifacts from an unrelated directory and an isolated venv."""

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path


class SmokeError(Exception):
    """A built artifact did not behave as expected."""


def source_version():
    source = Path(__file__).resolve().parents[1] / "zipflight" / "__init__.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise SmokeError("Cannot find __version__ in the source package; pass --expected-version.")


def run(command, *, cwd, env, expected_exit, timeout=60):
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if result.returncode != expected_exit:
        raise SmokeError(
            f"{command!r} exited {result.returncode}; expected {expected_exit}.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout


def scan(command, args, *, cwd, env, expected_exit, expected_status):
    output = run(command + args + ["--format", "json"], cwd=cwd, env=env, expected_exit=expected_exit)
    try:
        report = json.loads(output)
    except json.JSONDecodeError as exc:
        raise SmokeError(f"{command!r} did not produce a JSON report: {output!r}") from exc
    if report.get("schema_version") != 1 or report.get("status") != expected_status:
        raise SmokeError(f"Unexpected report schema or status from {command!r}: {report!r}")
    if not isinstance(report.get("issues"), list) or not isinstance(report.get("summary"), dict):
        raise SmokeError(f"Report from {command!r} has no findings or summary: {report!r}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--wheel", type=Path, help="Wheel to install into a fresh temporary virtual environment."
    )
    parser.add_argument("--zipapp", type=Path, help="Python zipapp to execute in isolated mode.")
    parser.add_argument("--exe", type=Path, help="Standalone executable to execute.")
    parser.add_argument(
        "--expected-version", help="Expected --version value; defaults to the source version."
    )
    args = parser.parse_args(argv)
    artifacts = {label: getattr(args, label) for label in ("wheel", "zipapp", "exe") if getattr(args, label)}
    if not artifacts:
        parser.error("supply at least one of --wheel, --zipapp, or --exe")
    artifacts = {label: path.resolve() for label, path in artifacts.items()}
    for label, path in artifacts.items():
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")
    expected_version = args.expected_version or source_version()
    env = os.environ.copy()
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        env.pop(name, None)
    env["PYTHONUTF8"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    with tempfile.TemporaryDirectory(prefix="zipflight-artifacts-") as temporary:
        base = Path(temporary)
        work = base / "unrelated working directory"
        work.mkdir()
        clean = work / "clean.zip"
        bad = work / "bad.zip"
        with zipfile.ZipFile(clean, "w") as archive:
            archive.writestr("docs/readme.txt", "Portable file")
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("notes/CON.txt", "Windows device name")
            archive.writestr("assets", "A file cannot also be a directory")
            archive.writestr("assets/icon.txt", "Conflicting descendant")
        before = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (clean, bad)}
        runners = []
        if "wheel" in artifacts:
            environment = base / "installed package"
            venv.EnvBuilder(with_pip=True).create(environment)
            binary = environment / ("Scripts" if os.name == "nt" else "bin")
            python = binary / ("python.exe" if os.name == "nt" else "python")
            run(
                [
                    str(python),
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--no-index",
                    "--no-deps",
                    str(artifacts["wheel"]),
                ],
                cwd=work,
                env=env,
                expected_exit=0,
                timeout=120,
            )
            runners.append(("wheel module", [str(python), "-I", "-m", "zipflight"]))
            runners.append(
                ("wheel command", [str(binary / ("zipflight.exe" if os.name == "nt" else "zipflight"))])
            )
        if "zipapp" in artifacts:
            runners.append(("zipapp", [sys.executable, "-I", str(artifacts["zipapp"])]))
        if "exe" in artifacts:
            runners.append(("executable", [str(artifacts["exe"])]))
        for label, command in runners:
            version = run(command + ["--version"], cwd=work, env=env, expected_exit=0).strip()
            if version != f"zipflight {expected_version}":
                raise SmokeError(f"{label} reports {version!r}; expected zipflight {expected_version}.")
            report = scan(command, [str(clean)], cwd=work, env=env, expected_exit=0, expected_status="pass")
            if report["entries"] != 1 or report["issues"] or report["summary"].get("errors") != 0:
                raise SmokeError(f"{label} failed the clean-archive check: {report!r}")
            report = scan(command, [str(bad)], cwd=work, env=env, expected_exit=1, expected_status="fail")
            codes = {issue.get("code") for issue in report["issues"]}
            if not {"windows-reserved-name", "file-directory-conflict"} <= codes:
                raise SmokeError(f"{label} missed the expected archive hazards: {report!r}")
            report = scan(command, ["--demo"], cwd=work, env=env, expected_exit=1, expected_status="fail")
            if report["summary"].get("errors", 0) < 1:
                raise SmokeError(f"{label} demo did not report an error: {report!r}")
            if sorted(path.name for path in work.iterdir()) != ["bad.zip", "clean.zip"]:
                raise SmokeError(f"{label} created unexpected files in the working directory.")
            after = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (clean, bad)}
            if after != before:
                raise SmokeError(f"{label} modified an input archive.")
            print(f"PASS {label}: version, clean ZIP, failing ZIP, demo, and unchanged inputs.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"Artifact smoke test failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
