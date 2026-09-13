"""Word-wise editing for every text field in the app.

Tk ships no Control-BackSpace binding at all. The keystroke falls through to
plain BackSpace, so a habit that deletes a word in every other program on the
machine deletes one letter here, and a long entry has to be cleared by holding
the key down. Control-Delete is the same story going forwards.

Bound once at class level, on "Entry" and on "Text", so a page never has to
remember to ask for it. CTkEntry and CTkTextbox both wrap those two widgets, so
this reaches the search bars, every input field and the bug report box.

WHERE THE WORD ENDS
-------------------
The rule is the one editors and browsers use, not the one Tk's own
Control-Left uses: skip the whitespace behind the cursor, then eat one run of
word characters, or one run of punctuation if that is what you are sitting
behind. "tank_volume " loses the whole name, not the space and four letters.
"""

from __future__ import annotations

import tkinter as tk

_WORD = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"


def _is_word(char: str) -> bool:
    # str.isalnum() rather than a fixed table, so accented characters and
    # anything else a person can type count as part of a word.
    return char in _WORD or char.isalnum()


def _word_start(text: str, end: int) -> int:
    """First index of the word ending at `end`. See the module docstring."""
    i = end
    while i > 0 and text[i - 1].isspace():
        i -= 1
    if i > 0:
        want = _is_word(text[i - 1])
        while i > 0 and not text[i - 1].isspace() and _is_word(text[i - 1]) == want:
            i -= 1
    return i


def _word_end(text: str, start: int) -> int:
    """Last index of the word beginning at `start`, whitespace included."""
    i = start
    n = len(text)
    if i < n and not text[i].isspace():
        want = _is_word(text[i])
        while i < n and not text[i].isspace() and _is_word(text[i]) == want:
            i += 1
    while i < n and text[i].isspace():
        i += 1
    return i


# ---------------------------------------------------------------- Entry


def _entry_delete_word(event, forward: bool):
    widget = event.widget
    try:
        if widget.selection_present():
            widget.delete("sel.first", "sel.last")
            return "break"
        text = widget.get()
        here = widget.index("insert")
    except Exception:                           # noqa: BLE001
        return None
    if forward:
        stop = _word_end(text, here)
        if stop > here:
            widget.delete(here, stop)
    else:
        start = _word_start(text, here)
        if start < here:
            widget.delete(start, here)
    return "break"


# ---------------------------------------------------------------- Text


def _text_delete_word(event, forward: bool):
    widget = event.widget
    try:
        if widget.tag_ranges("sel"):
            widget.delete("sel.first", "sel.last")
            return "break"
        line, column = (int(part) for part in str(widget.index("insert")).split("."))
    except Exception:                           # noqa: BLE001
        return None
    try:
        if forward:
            text = widget.get("insert", f"{line}.end")
            stop = _word_end(text, 0)
            # At the end of a line there is no word left to eat, so take the
            # newline instead and join with the line below.
            widget.delete("insert", f"{line}.{column + stop}" if stop else "insert+1c")
        else:
            text = widget.get(f"{line}.0", "insert")
            start = _word_start(text, len(text))
            widget.delete(f"{line}.{start}" if column else "insert-1c", "insert")
    except Exception:                           # noqa: BLE001
        return None
    return "break"


# ----------------------------------------------------------------------


def enable_word_editing(root: tk.Misc) -> None:
    """Teach every Entry and Text in this interpreter the two shortcuts.

    Called once, from the shell. Silent on failure: a missing shortcut is worth
    less than a window that will not open.
    """
    for widget_class, handler in (("Entry", _entry_delete_word),
                                  ("Text", _text_delete_word)):
        for sequence, forward in (("<Control-BackSpace>", False),
                                  ("<Control-Delete>", True)):
            try:
                root.bind_class(
                    widget_class, sequence,
                    lambda event, h=handler, f=forward: h(event, f))
            except Exception:                   # noqa: BLE001
                pass
