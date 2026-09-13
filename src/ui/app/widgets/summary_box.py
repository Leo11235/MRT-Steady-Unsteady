"""The bordered card at the top of a results page.

The dozen numbers an engineer checks first, inside a thick accent border with
the team logo beside them. Both results pages use it: unsteady for the run as a
whole, steady for a convergence or a hotfire, and once per point in a
parametric sweep, where the logo is left off because fifteen of them would be
wallpaper rather than branding.

WHAT THE BOX IS AND IS NOT
--------------------------
It is a fixed layout. It is never collapsed, never filtered in place, and never
reordered: it answers "how did this run go", and a page whose one fixed point
moves around is a page you have to re-read every time. Its values ARE indexed
for search, because the search results are a separate view and finding apogee
there costs the box nothing.

It holds three kinds of row. A plain value, which is an ordinary KVRow and
therefore re-units with the page. A pair, "used / available", one label over
two numbers sharing a unit, because that is the comparison people actually
make; the export still carries the two numbers separately, since a spreadsheet
cell reading "14.3 / 15.5" is a string nobody can sum. And a verdict, a row
whose value is a word rather than a measurement.

The unit helpers live here too rather than on either page, because a number
shown inside the box and the same number shown in a section below it must not
be able to disagree about what it is.
"""

from __future__ import annotations

from typing import Any, Optional

import customtkinter as ctk

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:                               # noqa: BLE001
    _HAS_PIL = False

from src.common.unit_labels import pretty_unit
from src.ui.app import backend_bridge, theme
from src.ui.app.widgets import kv_row

# The border is heavy and its contents sit well inside it. 38 px is about a
# centimetre at the 96 dpi these screens report.
BORDER = 6
INSET = 38
# The logo sits in the right half of the card. The rows are given a matching
# right margin so text and logo never collide, however long a verdict runs,
# rather than relying on the two happening not to meet.
LOGO_H = 150
LOGO_GAP = 24

# Wide enough for the longest label either page puts in the box, so the values
# line up in a column instead of stepping in and out with the names.
NAME_WIDTH = 340


# =============================================================================
# Units
# =============================================================================

def convert(value, key: str, system: str, native_system: str = "SI"):
    """(number, unit label) for one value in a unit system.

    Goes through the same registry lookups a KVRow does, including the
    radius-to-diameter scale, so a number shown outside a KVRow cannot disagree
    with the same number shown inside one.
    """
    _label, si_unit = kv_row.describe(key)
    scaled = value
    scale = kv_row.display_scale_of(key)
    if scale != 1.0 and isinstance(value, (int, float)) and not isinstance(value, bool):
        scaled = value * scale
    return kv_row.value_for_display(scaled, si_unit, system,
                                    kv_row.category_of_key(key), native_system)


def unit_suffix(key: str, system: str, native_system: str = "SI") -> str:
    """The unit for a key as a trailing "  N", or "" when there is none.

    For row labels in a grid, where one unit is shared across every column and
    repeating it in eight cells is noise rather than clarity.
    """
    _value, unit = convert(1.0, key, system, native_system)
    shown = pretty_unit(unit)
    return f"  {shown}" if shown else ""


def add_text_row(parent, label: str, text: str, colour=None) -> None:
    """A row whose value is a word rather than a measurement."""
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", pady=1)
    ctk.CTkLabel(row, text=label, width=NAME_WIDTH, anchor="w").pack(
        side="left", padx=(0, theme.PAD_S))
    value = ctk.CTkLabel(row, text=text, anchor="w", justify="left",
                         wraplength=520)
    if colour is not None:
        value.configure(text_color=colour)
    value.pack(side="left", fill="x", expand=True)


# =============================================================================
# The box
# =============================================================================

class SummaryBox:
    """One bordered card. Build it, then add rows to it in reading order.

    `page` is the ResultsPage the rows belong to: the box borrows its add_row,
    its dynamic labels and its search index rather than keeping any of its own,
    so unit switching and search work here exactly as they do everywhere else.
    """

    def __init__(self, page, parent, *, logo: bool = True) -> None:
        self.page = page
        self.frame = ctk.CTkFrame(parent, fg_color=theme.CARD_BG,
                                  border_color=theme.ACCENT_SLATE,
                                  border_width=BORDER, corner_radius=8)
        self.frame.pack(fill="x", pady=(theme.PAD_M, theme.PAD_S))

        logo_width = self._add_logo() if logo else 0
        self.inner = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.inner.pack(fill="x", pady=theme.PAD_M,
                        padx=(INSET,
                              INSET + (logo_width + LOGO_GAP if logo_width else 0)))

    # ------------------------------------------------------------------

    def value(self, key: str, value: Any, *, label: Optional[str] = None) -> None:
        """An ordinary measurement, from the registry.

        filterable=False keeps it out of exports and out of the row list the
        unit toggle walks as ordinary rows; searchable=True still indexes it.
        """
        self.page.add_row(self.inner, key, value,
                          filterable=False, searchable=True, label=label)

    def pair(self, used_key: str, used: Any, total: Any, label: str) -> None:
        """ "used / available", one label and one unit over two numbers.

        With no second value the row degrades to an ordinary one, which is what
        steady needs: it has no tank, so there is nothing for its masses to be
        a fraction of.
        """
        if used is None:
            return
        if total is None:
            self.value(used_key, used, label=label)
            return

        row = ctk.CTkFrame(self.inner, fg_color="transparent")
        row.pack(fill="x", pady=1)
        name = ctk.CTkLabel(row, text=label, width=NAME_WIDTH, anchor="w")
        name.pack(side="left", padx=(0, theme.PAD_S))
        shown = ctk.CTkLabel(row, text="", anchor="w")
        shown.pack(side="left", fill="x", expand=True)

        page = self.page
        builder = (lambda system, u=used, v=total, k=used_key:
                   pair_text(u, v, k, system, page.native_system))
        page.add_dynamic_label(shown, builder)
        page.add_searchable_text(label, builder, key=used_key)

    def text(self, label: str, text: str, colour=None) -> None:
        """A verdict. Searchable, since it is as much a result as a number."""
        add_text_row(self.inner, label, text, colour)
        self.page.add_searchable_text(label, lambda _system, t=text: t)

    # ------------------------------------------------------------------

    def _add_logo(self) -> int:
        """The team logo, right-aligned inside the card.

        Returns the width it occupies, or 0 when there is none, so the rows can
        reserve exactly that much margin.

        Placed rather than packed: it sits beside the rows without joining
        their layout. Every failure is silent and returns 0, because a missing
        asset or a Pillow that will not import should cost the user a
        decoration, not the results next to it.
        """
        if not _HAS_PIL:
            return 0
        try:
            path = backend_bridge.assets_dir() / "MRT_logo.png"
            if not path.exists():
                return 0
            image = Image.open(path)
            width, height = image.size
            scaled = int(round(LOGO_H * (width / height))) if height else LOGO_H
            ctk.CTkLabel(
                self.frame, text="",
                image=ctk.CTkImage(light_image=image, dark_image=image,
                                   size=(scaled, LOGO_H)),
            ).place(relx=1.0, rely=0.5, anchor="e", x=-INSET)
            return scaled
        except Exception:                       # noqa: BLE001
            return 0


def pair_text(used, total, key: str, system: str, native_system: str) -> str:
    """ "14.3 / 15.5 kg". One unit, since both halves share it."""
    shown_used, unit = convert(used, key, system, native_system)
    shown_total, _ = convert(total, key, system, native_system)
    unit = pretty_unit(unit)
    text = (f"{kv_row.format_scalar(shown_used)} / "
            f"{kv_row.format_scalar(shown_total)}")
    return f"{text} {unit}" if unit else text
