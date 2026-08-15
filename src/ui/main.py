"""
Entry point for the desktop app.

    python -m src.ui.main          from the project root
    python src/ui/main.py          also works; the path fix below handles it
"""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root_on_path() -> None:
    """Put the project root on sys.path before importing anything from src.

    Running `python src/ui/main.py` directly puts src/ui/ on the path rather
    than the project root, so `from src.backend...` would fail. Running it as
    `python -m src.ui.main` doesn't have that problem, but people do both.
    """
    root = str(Path(__file__).resolve().parents[2])
    if root not in sys.path:
        sys.path.insert(0, root)


_ensure_project_root_on_path()

# Has to come after the path fix above.
from src.ui.app.shell import AppShell        # noqa: E402


def main() -> None:
    AppShell().mainloop()


if __name__ == "__main__":
    main()
