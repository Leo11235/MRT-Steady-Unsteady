"""Main menu — the landing page."""

from __future__ import annotations

import sys
from pathlib import Path

import customtkinter as ctk

from src.ui.app import theme

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


def _asset_path(name: str) -> Path:
    """Locate a bundled asset.  Handles both source and PyInstaller layouts."""
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "src" / "ui" / "assets" / name
    # source layout: src/ui/app/pages/main_menu.py  →  src/ui/assets/
    return Path(__file__).resolve().parents[2] / "assets" / name


# Render an emoji glyph at an arbitrary size as a MONOCHROME white
# silhouette (using the font's outline paths, not its color bitmaps),
# so it matches the button text's colour rather than showing the
# emoji's built-in colours.  Returns None if PIL isn't available or
# no suitable font is found on this platform.
def _make_emoji_image(char: str, size: int):
    if not _HAS_PIL:
        return None
    # Prefer monochrome symbol fonts first (they have proper outline
    # shapes that PIL can fill with an arbitrary colour); fall back to
    # color-emoji fonts (whose outline layer PIL will also fill mono).
    font_candidates = [
        "seguisym.ttf",                # Windows: Segoe UI Symbol (mono)
        r"C:\Windows\Fonts\seguisym.ttf",
        "Symbola.ttf",                 # Cross-platform mono symbol font
        "DejaVuSans.ttf",              # Linux mono fallback
        "seguiemj.ttf",                # Windows: Segoe UI Emoji (fallback)
        r"C:\Windows\Fonts\seguiemj.ttf",
        "AppleColorEmoji.ttc",         # macOS
        "/System/Library/Fonts/Apple Color Emoji.ttc",
        "NotoColorEmoji.ttf",          # Linux (Noto)
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
    ]
    font = None
    for name in font_candidates:
        try:
            font = ImageFont.truetype(name, size)
            break
        except (OSError, IOError):
            continue
    if font is None:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # NOT embedded_color — that would keep the emoji's native colours.
    # Plain fill uses the font's outline path filled solid white, so
    # the glyph blends into the button's text colour.
    d.text((0, 0), char, font=font, fill=(255, 255, 255, 255))
    return img


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
            text="Steady-Unsteady",
            font=ctk.CTkFont(size=theme.SIZE_HERO, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(theme.PAD_S, theme.PAD_XS))

        ctk.CTkLabel(
            wrap,
            text="Hybrid Rocket Engine Simulator",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(0, theme.PAD_XL))

        # ---- two big primary buttons -----------------------------------
        primary = ctk.CTkFrame(wrap, fg_color="transparent")
        primary.pack()

        ctk.CTkButton(
            primary, text="Steady",
            width=220, height=90,
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            command=lambda: self.on_navigate("steady"),
        ).pack(side="left", padx=theme.PAD_M)

        ctk.CTkButton(
            primary, text="Unsteady",
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
            secondary, text="Browse saved results…",
            width=SECONDARY_W, height=SECONDARY_H,
            command=lambda: self.on_navigate("results"),
        ).pack(pady=theme.PAD_XS)

        # Report-a-bug button: keep the button itself unchanged (same
        # width/height/font), but render the snail emoji at ~2x the
        # normal text size, coloured to match the button text.
        snail_px = 24
        snail_pil = _make_emoji_image("🐌", snail_px)
        if snail_pil is not None:
            snail_ctk = ctk.CTkImage(
                light_image=snail_pil, dark_image=snail_pil,
                size=(snail_px, snail_px),
            )
            ctk.CTkButton(
                secondary, text="Report a bug ",
                image=snail_ctk, compound="right",
                width=SECONDARY_W, height=SECONDARY_H,
                command=lambda: self.on_navigate("bug"),
            ).pack(pady=theme.PAD_XS)
        else:
            # PIL/emoji font unavailable — fall back to inline text emoji.
            ctk.CTkButton(
                secondary, text="Report a bug  🐌",
                width=SECONDARY_W, height=SECONDARY_H,
                command=lambda: self.on_navigate("bug"),
            ).pack(pady=theme.PAD_XS)

        ctk.CTkButton(
            secondary, text="Settings",
            width=SECONDARY_W, height=SECONDARY_H,
            command=lambda: self.on_navigate("settings"),
        ).pack(pady=theme.PAD_XS)

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
