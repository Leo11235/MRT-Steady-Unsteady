"""Sidebar recent-presets dropdown.

A wider-than-normal `CTkOptionMenu` that lists the last N loaded/saved
preset filenames, with a "More presets…" tail entry that falls back to
the OS file dialog.  Selecting a filename calls `on_pick(path)`;
selecting the tail entry calls `on_more()`.

Kept as a small reusable widget so both SteadyPage and UnsteadyPage
sidebars can drop it in with two lines of setup.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Literal

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.services import i18n
from src.ui.app.services import recent_presets


Kind = Literal["steady", "unsteady"]


class RecentPresetMenu(ctk.CTkOptionMenu):
    """Dropdown with recent presets + a 'More presets…' tail entry.

    The dropdown text always shows a static "Recent presets"
    placeholder — picking never leaves the variable set to a filename,
    so the widget is visually consistent between openings.
    """

    # Width tuned so long timestamped filenames fit without ellipsis.
    _WIDTH = 320

    def __init__(
        self,
        parent,
        *,
        kind: Kind,
        on_pick: Callable[[Path], None],
        on_more: Callable[[], None],
    ) -> None:
        # Initial values populated in _refresh(); ctor just needs
        # something non-empty to satisfy CTkOptionMenu.
        super().__init__(
            parent,
            values=[i18n.t("action.more_presets")],
            command=self._on_choice,
            dynamic_resizing=False,
            width=self._WIDTH,
        )
        self._kind    = kind
        self._on_pick = on_pick
        self._on_more = on_more
        # We map the pretty display string back to a Path here.
        self._label_to_path: dict[str, Path] = {}

        self._refresh()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Reload from disk.  Call after Load / Save preset so the new
        entry appears at the top of the menu."""
        self._refresh()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _placeholder(self) -> str:
        return i18n.t("action.recent_presets")

    def _more_label(self) -> str:
        return i18n.t("action.more_presets")

    def _refresh(self) -> None:
        recents = recent_presets.list_recent(self._kind)
        self._label_to_path = {}
        values: list[str] = []
        for p in recents:
            label = p.name
            # In the (rare) case two files share the same basename in
            # different folders, disambiguate with parent's name.
            if label in self._label_to_path:
                label = f"{p.parent.name}/{p.name}"
            self._label_to_path[label] = p
            values.append(label)
        # Tail entry — always present.
        values.append(self._more_label())
        self.configure(values=values)
        # Keep the placeholder visible so users always see the same text.
        self.set(self._placeholder())

    def _on_choice(self, chosen: str) -> None:
        if chosen == self._more_label():
            self.set(self._placeholder())
            try:
                self._on_more()
            except Exception:
                pass
            return
        path = self._label_to_path.get(chosen)
        self.set(self._placeholder())
        if path is None:
            return
        try:
            self._on_pick(path)
        except Exception:
            pass
