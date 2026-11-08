"""Build a reproducible standard-library-only executable Python archive."""

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
output = ROOT / "dist" / "zipflight.pyz"
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    files = {"__main__.py": b"from zipflight.cli import main\nraise SystemExit(main())\n"}
    files.update(
        {p.relative_to(ROOT).as_posix(): p.read_bytes() for p in sorted((ROOT / "zipflight").glob("*.py"))}
    )
    files["LICENSE"] = (ROOT / "LICENSE").read_bytes()
    for name, data in sorted(files.items()):
        info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = 0o100644 << 16
        archive.writestr(info, data)
print(output)
