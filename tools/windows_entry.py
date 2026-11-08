"""PyInstaller entry point; stays separate from the package's relative imports."""

from zipflight.cli import main

raise SystemExit(main())
