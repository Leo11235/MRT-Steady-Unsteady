"""Render an emoji glyph to a small PIL image, once, and cache it.

Used by the main-menu Report-a-bug button so subsequent navigations back
to the main menu don't re-run the font search + text draw.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False


# Ordered by preference: monochrome-outline fonts first (they let us
# tint the glyph white to match the button text), then colour-emoji
# fonts as a fallback.
_EMOJI_FONT_CANDIDATES: tuple[str, ...] = (
    "seguisym.ttf",                                       # Windows: Segoe UI Symbol (mono)
    r"C:\Windows\Fonts\seguisym.ttf",
    "Symbola.ttf",                                        # Cross-platform mono symbol
    "DejaVuSans.ttf",                                     # Linux mono fallback
    "seguiemj.ttf",                                       # Windows: Segoe UI Emoji
    r"C:\Windows\Fonts\seguiemj.ttf",
    "AppleColorEmoji.ttc",                                # macOS
    "/System/Library/Fonts/Apple Color Emoji.ttc",
    "NotoColorEmoji.ttf",                                 # Linux (Noto)
    "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
)


def _resolve_font(size: int):
    if not _HAS_PIL:
        return None
    for name in _EMOJI_FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return None


@lru_cache(maxsize=32)
def render_emoji(char: str, size: int, rgba: tuple[int, int, int, int] = (255, 255, 255, 255)):
    """Return a PIL RGBA image of `char` at `size` px, filled `rgba`.

    None if PIL isn't installed or no emoji-capable font is found on
    this platform.  Result is cached — you can call this in a page
    build path without paying the font-lookup cost twice.
    """
    if not _HAS_PIL:
        return None
    font = _resolve_font(size)
    if font is None:
        return None
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # No embedded_color=True — we want a monochrome silhouette tinted `rgba`,
    # not the font's built-in colours.
    d.text((0, 0), char, font=font, fill=rgba)
    return img
