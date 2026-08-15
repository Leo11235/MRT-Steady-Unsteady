"""
Section furniture: titles, dividers, notes, and a collapsible panel.

The two input pages had identical private copies of the first three.  The
collapsible is new, and is what the unsteady page's six control-volume blocks
sit inside — six CVs of ten fields each is unreadable when all of it is open at
once.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.ui.app import theme


# =============================================================================
# Inline helpers
# =============================================================================
#
# These pack themselves and return the widget, so a caller that doesn't need a
# handle can ignore the return value.

def section_title(parent, text: str) -> ctk.CTkLabel:
    """A bold section heading."""
    label = ctk.CTkLabel(
        parent, text=text, anchor="w",
        font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
    )
    label.pack(fill="x", pady=(theme.PAD_S, theme.PAD_XS))
    return label


def divider(parent) -> ctk.CTkFrame:
    """A one-pixel horizontal rule."""
    rule = ctk.CTkFrame(parent, height=1, fg_color=theme.DIVIDER)
    rule.pack(fill="x", pady=theme.PAD_S)
    return rule


def note(parent, text: str, *, left_pad: int = 228) -> ctk.CTkLabel:
    """A grey italic aside.

    Left-padded by default so it lines up with the value column of a form
    rather than the label column, which reads as belonging to the fields above
    it rather than floating loose.
    """
    label = ctk.CTkLabel(
        parent, text=text, anchor="w", justify="left",
        text_color=theme.TEXT_MUTED,
        font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        wraplength=800,
    )
    label.pack(fill="x", padx=(left_pad, 0), pady=(theme.PAD_XS, theme.PAD_S))
    return label


# =============================================================================
# Collapsible
# =============================================================================

class CollapsibleSection(ctk.CTkFrame):
    """A clickable header with a body that folds away.

        section = CollapsibleSection(parent, "CV1 — Tank")
        LabeledField(section.body, spec).pack(fill="x")

    Put content in `.body`, never in the section itself.  Collapsing works by
    forgetting the body frame, so the widgets inside survive and keep their
    state — a folded section is hidden, not destroyed.
    """

    _ARROW_OPEN = "▾"      # down-pointing
    _ARROW_SHUT = "▸"      # right-pointing

    def __init__(self, master, title: str, *,
                 start_open: bool = True,
                 subtitle: str = "",
                 on_toggle: Optional[Callable[[bool], None]] = None) -> None:
        super().__init__(master, fg_color=theme.CARD_BG, corner_radius=8)

        self._open = start_open
        self._on_toggle = on_toggle

        # ---- header ---------------------------------------------------
        self._header = ctk.CTkFrame(self, fg_color="transparent", height=38)
        self._header.pack(fill="x", padx=theme.PAD_S, pady=(theme.PAD_S, 0))

        self._arrow = ctk.CTkLabel(
            self._header, text=self._ARROW_OPEN if start_open else self._ARROW_SHUT,
            width=18, anchor="w",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
        )
        self._arrow.pack(side="left")

        self._title = ctk.CTkLabel(
            self._header, text=title, anchor="w",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
        )
        self._title.pack(side="left")

        self._subtitle = ctk.CTkLabel(
            self._header, text=subtitle, anchor="w",
            text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self._subtitle.pack(side="left", padx=(theme.PAD_S, 0))

        # Built on demand by set_flagged(); most sections never need one.
        self._flag: Optional[ctk.CTkLabel] = None

        # The whole header is the hit target, not just the arrow — a 38-pixel
        # strip is far easier to hit than an 18-pixel glyph.
        for widget in (self._header, self._arrow, self._title, self._subtitle):
            widget.bind("<Button-1>", lambda _e: self.toggle())
            widget.configure(cursor="hand2")

        # ---- body -----------------------------------------------------
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        if start_open:
            self.body.pack(fill="x", padx=theme.PAD_M,
                           pady=(theme.PAD_XS, theme.PAD_M))

    # ------------------------------------------------------------------

    def toggle(self) -> None:
        self.set_open(not self._open)

    def set_open(self, is_open: bool) -> None:
        """Open or close, doing nothing if already in that state."""
        if is_open == self._open:
            return
        self._open = is_open
        if is_open:
            self.body.pack(fill="x", padx=theme.PAD_M,
                           pady=(theme.PAD_XS, theme.PAD_M))
        else:
            self.body.pack_forget()
        self._arrow.configure(text=self._ARROW_OPEN if is_open else self._ARROW_SHUT)
        if self._on_toggle is not None:
            self._on_toggle(is_open)

    @property
    def is_open(self) -> bool:
        return self._open

    def set_subtitle(self, text: str) -> None:
        """Update the grey text beside the title.

        The unsteady page uses this to show which physics model a CV has
        selected, so you can read the whole configuration with everything
        collapsed.
        """
        self._subtitle.configure(text=text)

    def set_flagged(self, text: str = "") -> None:
        """Mark this section as a problem: red title plus a short reason.

        The point is that it reads while COLLAPSED. A parametric sweep of
        fifteen points all looks identical from the outside, so the ones that
        failed have to announce themselves rather than waiting to be opened
        one by one.

        Passing "" clears the flag.
        """
        if text:
            self._title.configure(text_color=theme.ERROR)
            if self._flag is None:
                self._flag = ctk.CTkLabel(
                    self._header, text="", anchor="w",
                    text_color=theme.ERROR,
                    font=ctk.CTkFont(size=theme.SIZE_SMALL, weight="bold"),
                )
                self._flag.bind("<Button-1>", lambda _e: self.toggle())
                self._flag.configure(cursor="hand2")
            self._flag.configure(text=text)
            self._flag.pack(side="right", padx=(theme.PAD_S, theme.PAD_S))
        else:
            self._title.configure(text_color=theme.TEXT_NORMAL)
            if self._flag is not None:
                self._flag.pack_forget()
