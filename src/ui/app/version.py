"""Single-source-of-truth for the app version string.

The version LIVES in the top-level `VERSION` file at the repo root
(one line, e.g. "1.4").  Both the Python code (via this module) and
the Inno Setup installer (via `installer.iss`) read from that file,
so bumping the version means editing exactly one file.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _read_version() -> str:
    """Read the VERSION file; fall back to 'unknown' if it isn't found."""
    candidates: list[Path] = []
    # Frozen build: PyInstaller unpacks bundled data into sys._MEIPASS.
    # We ship VERSION alongside the other read-only resources.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "VERSION")
    # Source layout: VERSION is at the repo root, three parents up from
    # this file  (src/ui/app/version.py -> repo root).
    candidates.append(Path(__file__).resolve().parents[3] / "VERSION")
    for p in candidates:
        try:
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        except OSError:
            pass
    return "unknown"


VERSION = _read_version()
