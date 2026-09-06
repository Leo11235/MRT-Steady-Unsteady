"""
Main menu — the landing page.

One centred stack: logo, hero text, the two simulators, then the secondary
actions.  The version chip sits in the bottom-right corner rather than in the
stack, and opens the patch notes.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import backend_bridge, theme
from src.ui.app.services import os_utils
from src.ui.app.version import VERSION

try:
    from PIL import Image
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False


USER_MANUAL_URL = "https://github.com/Leo11235/MRT-Steady-Unsteady/blob/main/docs/user_manual.md"

_PRIMARY_W, _PRIMARY_H = 220, 90
_SECONDARY_W, _SECONDARY_H = 220, 36
_LOGO_HEIGHT = 150


class MainMenuPage(ctk.CTkFrame):
    """The landing page. Owns its own hero text, so the top bar stays empty."""

    TITLE = ""

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._build()

    def _build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        self._add_logo(wrap)

        ctk.CTkLabel(
            wrap, text="Steady-Unsteady",
            font=ctk.CTkFont(size=theme.SIZE_HERO, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(theme.PAD_S, theme.PAD_XS))

        ctk.CTkLabel(
            wrap, text="Hybrid Rocket Engine Simulator",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(0, theme.PAD_XL))

        # ---- the two simulators ---------------------------------------
        primary = ctk.CTkFrame(wrap, fg_color="transparent")
        primary.pack()

        for label, target in (("Steady", "steady"), ("Unsteady", "unsteady")):
            ctk.CTkButton(
                primary, text=label,
                width=_PRIMARY_W, height=_PRIMARY_H,
                font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
                command=lambda t=target: self.on_navigate(t),
            ).pack(side="left", padx=theme.PAD_M)

        # ---- everything else -------------------------------------------
        # The stack sits half a button higher than it used to, which is the room
        # the fourth button needed once the version chip left for the corner.
        secondary = ctk.CTkFrame(wrap, fg_color="transparent")
        secondary.pack(pady=(theme.PAD_XL - _SECONDARY_H // 2, 0))

        for label, target in (
            ("Browse saved results…", "results"),
            ("Report a bug  🐌", "bug"),
            ("Settings", "settings"),
        ):
            ctk.CTkButton(
                secondary, text=label,
                width=_SECONDARY_W, height=_SECONDARY_H,
                command=lambda t=target: self.on_navigate(t),
            ).pack(pady=theme.PAD_XS)

        # Leaves the app for the manual on GitHub, so it is the one button here
        # that doesn't navigate. Same size and colour as its neighbours.
        ctk.CTkButton(
            secondary, text="User manual",
            width=_SECONDARY_W, height=_SECONDARY_H,
            command=lambda: os_utils.open_url(USER_MANUAL_URL),
        ).pack(pady=theme.PAD_XS)

        self._add_version_chip()

    def _add_version_chip(self) -> None:
        """Version chip, pinned to the bottom-right corner.

        Quiet enough to ignore, obvious enough to find when someone asks which
        build you're on, and it opens the patch notes.  Placed on the page
        rather than packed into the centred stack so it stays in the corner
        whatever the stack does.
        """
        ctk.CTkButton(
            self, text=f"v{VERSION}",
            width=80, height=24, corner_radius=12,
            fg_color="transparent", hover_color=theme.CARD_BG,
            text_color=theme.TEXT_MUTED,
            border_width=1, border_color=theme.TEXT_FAINT,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            command=lambda: self.on_navigate("patchnotes"),
        ).place(relx=1.0, rely=1.0, anchor="se",
                x=-theme.PAD_L, y=-theme.PAD_M)

    # ------------------------------------------------------------------

    def _add_logo(self, parent) -> None:
        """Draw the MRT logo, or quietly skip it.

        A missing asset or a Pillow that won't load shouldn't cost the user
        their menu, so every failure here is non-fatal.
        """
        if not _HAS_PIL:
            return
        path = backend_bridge.assets_dir() / "MRT_logo.png"
        if not path.exists():
            return
        try:
            image = Image.open(path)
            width, height = image.size
            scaled_w = int(round(_LOGO_HEIGHT * (width / height))) if height else _LOGO_HEIGHT
            ctk.CTkLabel(
                parent, text="",
                image=ctk.CTkImage(light_image=image, dark_image=image,
                                   size=(scaled_w, _LOGO_HEIGHT)),
            ).pack(pady=(0, theme.PAD_S))
        except Exception:                       # noqa: BLE001
            pass
