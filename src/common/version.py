"""
Reads the current app version from the VERSION file at the repo root; used by UI and backend. 
"""

from __future__ import annotations
from pathlib import Path

def _read_version() -> str:
    return (Path(__file__).resolve().parents[2] / "VERSION").read_text(encoding="utf-8").strip()

VERSION = _read_version()