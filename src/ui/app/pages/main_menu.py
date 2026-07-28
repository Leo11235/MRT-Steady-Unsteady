"""Main menu — the landing page."""

from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.services.emoji_cache import render_emoji
from src.ui.app.services import i18n

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


def _asset_path(name: str) -> Path:
    """Locate a bundled asset.  Handles both source and PyInstaller layouts."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "src" / "ui" / "assets" / name
    # source layout: src/ui/app/pages/main_menu.py  →  src/ui/assets/
    return Path(__file__).resolve().parents[2] / "assets" / name


class MainMenuPage(ctk.CTkFrame):
    TITLE = ""   # main menu has its own hero text; no top-bar title

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._build()

    def _build(self) -> None:
        # One centered stack: logo → title → subtitle → buttons → side actions
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.place(relx=0.5, rely=0.5, anchor="center")

        # ---- logo (optional — silently skipped if PIL missing or file gone)
        self._add_logo(wrap)

        # ---- hero text -------------------------------------------------
        ctk.CTkLabel(
            wrap,
            text=i18n.t("menu.hero"),
            font=ctk.CTkFont(size=theme.SIZE_HERO, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(theme.PAD_S, theme.PAD_XS))

        ctk.CTkLabel(
            wrap,
            text=i18n.t("menu.subtitle"),
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(0, theme.PAD_XL))

        # ---- two big primary buttons -----------------------------------
        primary = ctk.CTkFrame(wrap, fg_color="transparent")
        primary.pack()

        ctk.CTkButton(
            primary, text=i18n.t("menu.steady"),
            width=220, height=90,
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            command=lambda: self.on_navigate("steady"),
        ).pack(side="left", padx=theme.PAD_M)

        ctk.CTkButton(
            primary, text=i18n.t("menu.unsteady"),
            width=220, height=90,
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            command=lambda: self.on_navigate("unsteady"),
        ).pack(side="left", padx=theme.PAD_M)

        # ---- secondary buttons (all same dimensions) -------------------
        SECONDARY_W = 220
        SECONDARY_H = 36
        secondary = ctk.CTkFrame(wrap, fg_color="transparent")
        secondary.pack(pady=(theme.PAD_XL, 0))

        ctk.CTkButton(
            secondary, text=i18n.t("menu.browse_results"),
            width=SECONDARY_W, height=SECONDARY_H,
            command=lambda: self.on_navigate("results"),
        ).pack(pady=theme.PAD_XS)

        # Report-a-bug button: keep the button itself unchanged (same
        # width/height/font), but render the snail emoji at ~2x the
        # normal text size, coloured to match the button text.  The
        # PIL image is cached in services.emoji_cache so re-entering
        # this page later doesn't re-run the font search.
        snail_px = 24
        snail_pil = render_emoji("🐌", snail_px)
        if snail_pil is not None:
            snail_ctk = ctk.CTkImage(
                light_image=snail_pil, dark_image=snail_pil,
                size=(snail_px, snail_px),
            )
            ctk.CTkButton(
                secondary, text=i18n.t("menu.report_bug") + " ",
                image=snail_ctk, compound="right",
                width=SECONDARY_W, height=SECONDARY_H,
                command=lambda: self.on_navigate("bug"),
            ).pack(pady=theme.PAD_XS)
        else:
            # PIL/emoji font unavailable — fall back to inline text emoji.
            ctk.CTkButton(
                secondary, text=i18n.t("menu.report_bug") + "  🐌",
                width=SECONDARY_W, height=SECONDARY_H,
                command=lambda: self.on_navigate("bug"),
            ).pack(pady=theme.PAD_XS)

        ctk.CTkButton(
            secondary, text=i18n.t("menu.settings"),
            width=SECONDARY_W, height=SECONDARY_H,
            command=lambda: self.on_navigate("settings"),
        ).pack(pady=theme.PAD_XS)

        # Small version chip so users know which release they're on.
        # Click opens the patchnotes page (release-notes browser).
        # Sits directly below the last secondary button so it's easy to
        # find but doesn't dominate the layout.
        try:
            from src.ui.app.version import VERSION as _APP_VERSION
        except Exception:
            _APP_VERSION = "unknown"
        ctk.CTkButton(
            secondary,
            text=f"v{_APP_VERSION}",
            width=80, height=24,
            corner_radius=12,
            fg_color="transparent",
            hover_color=theme.CARD_BG,
            text_color=theme.TEXT_MUTED,
            border_width=1,
            border_color=theme.TEXT_FAINT,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
            command=lambda: self.on_navigate("patchnotes"),
        ).pack(pady=(theme.PAD_S, 0))

    # ------------------------------------------------------------------

    def _add_logo(self, parent) -> None:
        path = _asset_path("MRT_logo.png")
        if not path.exists() or not _HAS_PIL:
            return
        try:
            img = Image.open(path)
            w, h = img.size
            target_h = 150
            target_w = int(round(target_h * (w / h))) if h else target_h
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                   size=(target_w, target_h))
            ctk.CTkLabel(parent, image=ctk_img, text="").pack(pady=(0, theme.PAD_S))
        except Exception:
            # Don't let a bad image take down the menu.
            pass
