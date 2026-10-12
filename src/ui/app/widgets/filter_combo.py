"""
A text box you can type into, with a suggestion list that narrows as you type.

Matching is by PREFIX, not substring. With options 1, 12, 123, 1234, 12345:

    ""      -> all five
    "1"     -> all five
    "12"    -> 12, 123, 1234, 12345
    "1234"  -> 1234, 12345
    "23"    -> nothing

That's what you want for a list of numbers: you're narrowing a value you
half-remember from the left, not searching for a digit somewhere inside it.

WHY THIS ISN'T A CTkComboBox
----------------------------
It was, briefly, and it was miserable to type in. CTkComboBox's dropdown is a
Tk menu, and posting a menu grabs the keyboard — so every keystroke that
refreshed the list stole focus from the entry and the NEXT keystroke went
nowhere. You had to click back into the box between characters.

The suggestion list here is a borderless Toplevel holding a Listbox, and
nothing in it is ever given focus. The entry keeps the keyboard for the whole
interaction, which is the only way type-ahead feels right. Up/Down/Enter drive
the list from the entry's own bindings.

Used for the hold-constant values in the parametric graph dialog, where a
sweep can produce more options than a plain dropdown is pleasant to scroll.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional, Sequence

import customtkinter as ctk

from src.ui.app import theme

_MAX_VISIBLE_ROWS = 8
_ROW_H = 22


def prefix_matches(options: Sequence[str], typed: str) -> list[str]:
    """Options starting with `typed`, case-insensitively. Empty text matches
    everything. Module-level so it can be tested without a display."""
    if not typed:
        return list(options)
    lowered = typed.lower()
    return [o for o in options if o.lower().startswith(lowered)]


class FilterCombo(ctk.CTkFrame):
    """An entry with a filtered suggestion list."""

    def __init__(self, master, *, values: Sequence[str],
                 variable: Optional[ctk.StringVar] = None,
                 on_change: Optional[Callable[[str], None]] = None,
                 width: int = 190, font=None, **kwargs) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)

        self._all_values = list(values)
        self._on_change = on_change
        self._var = variable if variable is not None else ctk.StringVar()
        if not self._var.get() and self._all_values:
            self._var.set(self._all_values[0])

        self._popup: Optional[tk.Toplevel] = None
        self._list: Optional[tk.Listbox] = None
        self._font = font or ctk.CTkFont(size=theme.SIZE_SMALL)

        self._entry = ctk.CTkEntry(self, textvariable=self._var,
                                   width=width - 30, font=self._font)
        self._entry.pack(side="left")

        self._arrow = ctk.CTkButton(
            self, text="▾", width=26, height=28,
            fg_color=theme.CARD_HOVER, hover_color=theme.CARD_BG,
            text_color=theme.TEXT_MUTED,
            command=self._toggle_popup)
        self._arrow.pack(side="left", padx=(2, 0))

        self._entry.bind("<KeyRelease>", self._on_key)
        self._entry.bind("<Down>", self._on_down)
        self._entry.bind("<Up>", self._on_up)
        self._entry.bind("<Return>", self._on_return)
        self._entry.bind("<Escape>", lambda _e: self._close())
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Destroy>", lambda _e: self._close(), add="+")

    # ==================================================================
    # Public API
    # ==================================================================

    def get(self) -> str:
        return self._var.get()

    def set(self, value: str) -> None:
        self._var.set(value)

    def set_options(self, values: Sequence[str]) -> None:
        """Replace the option list, keeping the current text if it's still
        valid and falling back to the first option if it isn't."""
        self._all_values = list(values)
        if self._var.get() not in self._all_values:
            self._var.set(self._all_values[0] if self._all_values else "")

    def all_options(self) -> list[str]:
        return list(self._all_values)

    def is_valid(self) -> bool:
        """Whether the typed text is one of the options. The entry is free
        text, so the caller has to be able to ask."""
        return self._var.get() in self._all_values

    def configure(self, **kwargs):                  # noqa: D102
        # `state` is what the graph dialog uses to grey a whole card out.
        state = kwargs.pop("state", None)
        if state is not None:
            self._entry.configure(state=state)
            self._arrow.configure(state=state)
            if state == "disabled":
                self._close()
        if kwargs:
            super().configure(**kwargs)

    def cget(self, attribute_name: str):            # noqa: D102
        if attribute_name == "state":
            return self._entry.cget("state")
        return super().cget(attribute_name)

    # ==================================================================
    # Keyboard
    # ==================================================================

    def _on_key(self, event) -> None:
        # Navigation keys are handled by their own bindings; re-filtering on
        # them would fight the user mid-selection.
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        self._refresh(open_if_matches=True)

    def _on_down(self, _event) -> str:
        if self._popup is None:
            self._refresh(open_if_matches=True)
            return "break"
        self._move_selection(+1)
        return "break"                              # don't move the caret

    def _on_up(self, _event) -> str:
        if self._popup is not None:
            self._move_selection(-1)
        return "break"

    def _on_return(self, _event) -> str:
        if self._popup is not None and self._list is not None:
            selection = self._list.curselection()
            if selection:
                self._accept(self._list.get(selection[0]))
                return "break"
        self._close()
        return "break"

    def _on_focus_out(self, _event) -> None:
        # Delay: clicking a suggestion fires FocusOut before the click lands,
        # and closing immediately would destroy the row being clicked.
        self.after(150, self._close_if_unfocused)

    def _close_if_unfocused(self) -> None:
        try:
            if self.focus_get() is self._entry:
                return
        except Exception:                           # noqa: BLE001
            pass
        self._close()

    def _move_selection(self, delta: int) -> None:
        if self._list is None:
            return
        size = self._list.size()
        if not size:
            return
        current = self._list.curselection()
        index = (current[0] + delta) if current else (0 if delta > 0 else size - 1)
        index = max(0, min(size - 1, index))
        self._list.selection_clear(0, "end")
        self._list.selection_set(index)
        self._list.see(index)

    # ==================================================================
    # The suggestion popup
    # ==================================================================

    def _toggle_popup(self) -> None:
        if self._popup is not None:
            self._close()
        else:
            self._entry.focus_set()
            self._refresh(open_if_matches=True, show_all=True)

    def _refresh(self, *, open_if_matches: bool, show_all: bool = False) -> None:
        matches = (self._all_values if show_all
                   else prefix_matches(self._all_values, self._var.get()))
        if not matches:
            self._close()
            return
        if not open_if_matches and self._popup is None:
            return
        self._open(matches)

    def _open(self, matches: list[str]) -> None:
        if self._popup is None:
            popup = tk.Toplevel(self)
            popup.wm_overrideredirect(True)
            try:
                popup.attributes("-topmost", True)
            except Exception:                       # noqa: BLE001
                pass
            listbox = tk.Listbox(
                popup, activestyle="none", exportselection=False,
                borderwidth=1, relief="solid", highlightthickness=0,
                background="#232326", foreground="#f0f0f0",
                selectbackground=theme.ACCENT_SLATE[0], selectforeground="#ffffff",
                font=("TkDefaultFont", theme.SIZE_SMALL),
            )
            listbox.pack(fill="both", expand=True)
            # Button-1 on the list, not <<ListboxSelect>>: the latter also
            # fires for keyboard moves, which would accept on every arrow key.
            listbox.bind("<Button-1>", self._on_list_click)
            self._popup, self._list = popup, listbox

        self._list.delete(0, "end")
        for value in matches:
            self._list.insert("end", value)
        self._list.selection_clear(0, "end")
        self._list.selection_set(0)
        self._place(len(matches))

    def _place(self, row_count: int) -> None:
        """Position below the entry, flipping above and clamping sideways so
        the list never hangs off the screen."""
        if self._popup is None:
            return
        rows = max(1, min(row_count, _MAX_VISIBLE_ROWS))
        width = max(self._entry.winfo_width(), 120)
        height = rows * _ROW_H + 4
        if self._list is not None:
            self._list.configure(height=rows)

        x = self._entry.winfo_rootx()
        y = self._entry.winfo_rooty() + self._entry.winfo_height() + 2
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        if y + height > screen_h - 40:
            y = self._entry.winfo_rooty() - height - 2      # flip above
        x = max(0, min(x, screen_w - width))
        self._popup.wm_geometry(f"{width}x{height}+{x}+{y}")

    def _on_list_click(self, event) -> str:
        if self._list is None:
            return "break"
        index = self._list.nearest(event.y)
        if index >= 0:
            self._accept(self._list.get(index))
        return "break"

    def _accept(self, value: str) -> None:
        self._var.set(value)
        self._close()
        self._entry.focus_set()
        # Caret to the end, so typing after a pick appends instead of
        # landing wherever it was before.
        try:
            self._entry.icursor("end")
        except Exception:                           # noqa: BLE001
            pass
        if self._on_change is not None:
            self._on_change(value)

    def _close(self) -> None:
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:                       # noqa: BLE001
                pass
        self._popup, self._list = None, None
