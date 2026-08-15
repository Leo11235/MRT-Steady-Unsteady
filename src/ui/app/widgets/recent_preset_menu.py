"""
RecentPresetMenu — a dropdown of recently-loaded presets.

Sits under Load preset in the action sidebar. Loading a preset you were working
on yesterday is the single most common way a session starts, and going through
a file dialog for it every time is friction for no reason.

Shows file stems rather than full paths, since the folder is almost always the
same one. Duplicate stems from different folders get their parent appended so
they stay distinguishable.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.services import recent_presets

_PLACEHOLDER = "Recent presets…"
_EMPTY = "(nothing loaded yet)"


class RecentPresetMenu(ctk.CTkOptionMenu):
    """Pick a recent preset. Calls `on_pick(path)` with the chosen one."""

    def __init__(self, master, kind: str, on_pick: Callable[[Path], None],
                 *, width: int = 180) -> None:
        self._kind = kind
        self._on_pick = on_pick
        self._by_label: dict[str, Path] = {}
        self._var = ctk.StringVar(value=_PLACEHOLDER)

        super().__init__(
            master, variable=self._var, values=[_PLACEHOLDER],
            command=self._on_selected, width=width, dynamic_resizing=False,
            fg_color=theme.CARD_BG, button_color=theme.CARD_BG,
            button_hover_color=theme.CARD_HOVER,
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self.refresh()

    def refresh(self) -> None:
        """Re-read the list. Call after loading or saving a preset."""
        paths = recent_presets.recent(self._kind)
        self._by_label = {}

        # Disambiguate only where two files share a stem, so the common case
        # stays short.
        stems = Counter(p.stem for p in paths)
        for path in paths:
            label = path.stem if stems[path.stem] == 1 else f"{path.stem}  ({path.parent.name})"
            self._by_label[label] = path

        labels = list(self._by_label)
        self.configure(values=[_PLACEHOLDER] + labels if labels else [_EMPTY])
        self._var.set(_PLACEHOLDER if labels else _EMPTY)

    def _on_selected(self, label: str) -> None:
        path = self._by_label.get(label)
        # Snap back immediately: this is an action, not a persistent choice,
        # and leaving the last-loaded name in the box implies otherwise.
        self._var.set(_PLACEHOLDER if self._by_label else _EMPTY)
        if path is not None:
            self._on_pick(path)
