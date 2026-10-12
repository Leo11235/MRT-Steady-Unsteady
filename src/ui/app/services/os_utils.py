"""OS-level helpers that don't fit into any specific page.

Right now: opening a path in the native file browser, and opening a URL
in the default browser.  The three supported platforms use completely
different commands for the former, so this file paves over the
differences with one function the UI can call.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path


def reveal_in_file_explorer(path) -> None:
    """Open the OS file browser at `path`.

    - If `path` is a file:  open the containing folder, highlighting the
      file where the OS supports that (Windows Explorer, macOS Finder).
    - If `path` is a directory: open the directory itself.
    - If the path doesn't exist, this is a no-op.
    - Any OS-level failure is swallowed silently so a missing binary
      (like a headless Linux install without xdg-open) can't crash the
      UI thread.
    """
    p = Path(path).resolve()
    if not p.exists():
        return
    try:
        if sys.platform == "win32":
            if p.is_dir():
                os.startfile(str(p))
            else:
                # explorer.exe /select,<path> is quirky: the switch
                # must be its OWN argument (with trailing comma) and
                # the path must be the next argument.  Passing the
                # whole thing as one glued string ("/select,C:\...")
                # silently falls back to opening the user's Documents
                # folder, which is what was happening before.
                try:
                    subprocess.Popen(
                        ["explorer", "/select,", str(p)],
                        close_fds=True,
                    )
                except Exception:
                    # Belt-and-suspenders: if /select fails for any
                    # reason, at least open the containing folder.
                    os.startfile(str(p.parent))
        elif sys.platform == "darwin":
            if p.is_dir():
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["open", "-R", str(p)])
        else:
            # Linux / BSD / etc.  No universal "reveal a file with it
            # highlighted" command exists, so we fall back to opening
            # the containing folder.
            target = p if p.is_dir() else p.parent
            subprocess.Popen(["xdg-open", str(target)])
    except Exception:
        # Best-effort helper; never bring down the UI over this.
        pass


def open_url(url: str) -> None:
    """Open `url` in the user's default browser.

    Uses webbrowser rather than the per-platform commands above, since every
    supported OS already resolves http(s) through it.  Failures are swallowed
    the same way: a machine with no browser configured shouldn't take the UI
    down over a help link.
    """
    if not url:
        return
    try:
        webbrowser.open_new_tab(url)
    except Exception:
        pass

