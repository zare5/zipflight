"""Build the Windows executable with notices from its actual bundled runtime."""

import importlib.metadata
import ssl
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1]
    dist = root / "dist"
    dist.mkdir(exist_ok=True)

    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    pyinstaller = importlib.metadata.distribution("pyinstaller")
    bootloader_license = next(
        (
            Path(pyinstaller.locate_file(path))
            for path in pyinstaller.files or ()
            if path.name == "COPYING.txt" and "licenses" in path.parts
        ),
        None,
    )
    if bootloader_license is None:
        raise RuntimeError("The installed PyInstaller distribution is missing its COPYING.txt license.")
    if ssl.OPENSSL_VERSION_INFO[0] < 3:
        raise RuntimeError("This build's OpenSSL notices require an OpenSSL 3 or newer Python runtime.")

    notices = dist / "THIRD_PARTY_NOTICES.txt"
    parts = [
        "Zipflight Windows executable: bundled third-party software notices.\n"
        "Zipflight itself is MIT licensed; its LICENSE is also included in the executable.\n"
        "The following notices are copied from the build runtime and installed PyInstaller distribution.\n"
        "CPython's license file also contains notices for its bundled components.\n",
        f"CPython {sys.version.split()[0]}\n" + python_license.read_text(encoding="utf-8"),
        f"PyInstaller {pyinstaller.version}\n" + bootloader_license.read_text(encoding="utf-8"),
        f"{ssl.OPENSSL_VERSION}\nhttps://www.openssl.org/\n"
        + (root / "docs" / "licenses" / "OpenSSL.txt").read_text(encoding="utf-8"),
    ]
    notices.write_text("\n\n".join(parts), encoding="utf-8", newline="\n")

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--onefile",
            "--clean",
            "--name",
            "zipflight-windows-x64",
            "--paths",
            str(root),
            "--add-data",
            "LICENSE;.",
            "--add-data",
            "dist/THIRD_PARTY_NOTICES.txt;.",
            "tools/windows_entry.py",
        ],
        cwd=root,
        check=True,
    )


if __name__ == "__main__":
    main()
