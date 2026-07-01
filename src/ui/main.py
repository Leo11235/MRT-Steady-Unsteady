"""
Entry point for the MRT Steady-Unsteady Simulator GUI.

Run from project root:
    python -m src.ui.main

Or with the convenience script:
    python src/ui/main.py
(both work; the second adds the project root to sys.path for you)
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root_on_path() -> None:
    """
    When `python src/ui/main.py` is invoked directly (instead of
    `python -m src.ui.main`), the project root isn't on sys.path,
    so absolute imports like `from src.backend...` would fail.
    Insert it before importing anything from src.*.
    """
    project_root = Path(__file__).resolve().parents[2]
    s = str(project_root)
    if s not in sys.path:
        sys.path.insert(0, s)


_ensure_project_root_on_path()

# Imports from src.ui.* go after the path tweak
from src.ui.app.shell import AppShell  # noqa: E402


def main() -> None:
    app = AppShell()
    app.mainloop()


if __name__ == "__main__":
    main()
