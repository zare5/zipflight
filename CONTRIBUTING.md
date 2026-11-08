# Contributing

Zipflight focuses on local ZIP metadata checks before sharing or releasing an archive.
Small, reproducible fixes are welcome, especially cases where extractors disagree.

```sh
git clone https://github.com/zare5/zipflight.git
cd zipflight
python -m pip install -e .
python -m unittest discover -s tests -v
```

Runtime code uses only the Python standard library and supports Python 3.10+.
Tests generate small archives in temporary directories. Never extract dangerous
test entries or commit private archives. A good bug report includes a minimal
archive-generating script, the command, output, and target OS/extractor.

When changing a check, add a behavioral regression test and update
`docs/checks.md`. Keep check codes and JSON fields stable within a schema version.
Distinguish an observed metadata hazard from a prediction about a particular
filesystem. A filename collision warning must show the relevant names.

To build release artifacts:

```sh
python -m pip install build twine
python -m build
python -m twine check dist/*
python tools/build_zipapp.py
```

Verify a built wheel and zipapp from a temporary directory, without importing
the source checkout:

```sh
python tools/smoke_artifacts.py --wheel dist/zipflight-0.1.1-py3-none-any.whl --zipapp dist/zipflight.pyz
```

CI tests Linux, Windows, and macOS, then builds the distributions and Windows
console executable. CI also runs these artifact checks. Release files are
attached to GitHub Releases; the project does not currently publish to PyPI.

On Windows, `python -m pip install pyinstaller` followed by
`python tools/build_windows.py` builds the console executable and copies the
actual runtime/bootloader notices to `dist/THIRD_PARTY_NOTICES.txt`. Ship that
notice file alongside the executable; it is also embedded in the executable.
