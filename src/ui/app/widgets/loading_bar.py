"""
RocketLoadingBar — a horizontal pixel-art rocket inching across a night sky.

The bar represents progress as a rocket sprite (pointing right) that moves
from left to right.  Behind/in-front-of it sits a dark "cover" rectangle
representing the unrevealed sky; the cover's left edge sits INSIDE the
rocket's silhouette so the transition seam is hidden by the rocket body.

The canvas resizes with its parent — bind `<Configure>` on the frame and
update the underlying canvas + stars accordingly.

Public API:
    start()                begin indeterminate animation
    stop()                 jump to 100% and stop animating
    set_progress(0..1)     determinate progress (not used today)
"""

from __future__ import annotations

import random
import tkinter as tk
from math import exp

import customtkinter as ctk


# ---------------------------------------------------------------------------
# Pixel-art rocket (pointing RIGHT, flames trailing LEFT)
# "Chunky Racer" design — swept-back fins, diamond window with a K ring,
# bell nozzle, 5-row-tall flame.  Sprite is 36 columns × 15 rows.
#
#   ' '  transparent
#   'K'  dark outline
#   'R'  coral body accent (nose + fins)
#   'r'  darker orange shading
#   'W'  white body
#   'w'  subtle body shade
#   'B'  window blue
#   'L'  window highlight (lighter blue)
#   'G'  nozzle gray
#   'g'  nozzle highlight
#   'O'  flame edge (orange)
#   'Y'  flame core (yellow)
# ---------------------------------------------------------------------------

ROCKET_SPRITE = [
    "       KRRK                         ",   # 0  top fin tip
    "       KRRRK                        ",   # 1
    "       KRRRRK                       ",   # 2
    "       KRRRRRK            KK        ",   # 3  top fin base + nose tip
    "       KKKKKKKKKKKKKKKKKKKKRK       ",   # 4  body top edge
    "OO  KKKKWWWWWKBKWWWWWWWWRRKRRK      ",   # 5  nozzle top + flame + window ring
    "YYY KGGKWWWWKLLBKWWWWWWWRRKRRRK     ",   # 6
    "YYYYKgGKWWWKBBBBBKWWWWWWRRKRRRRK    ",   # 7  MIDDLE row — flame core
    "YYY KGGKWWWWKBBBKWWWWWWWRRKRRRK     ",   # 8
    "OO  KKKKWWWWWKBKWWWWWWWWRRKrrK      ",   # 9  nozzle bottom
    "       KwwwwwwwwwwwwwwwwRRKrK       ",   # 10 body shade + nose shading
    "       KRRRRRKKKKKKKKKKKKKKK        ",   # 11 body bottom edge + fin base
    "       KRRRRK                       ",   # 12
    "       KRRRK                        ",   # 13
    "       KRRK                         ",   # 14 bottom fin tip
]
# sanity: every row same width
_W = max(len(r) for r in ROCKET_SPRITE)
ROCKET_SPRITE = [r.ljust(_W) for r in ROCKET_SPRITE]
_ROCKET_W_CHARS = _W
_ROCKET_H_CHARS = len(ROCKET_SPRITE)

ROCKET_COLORS = {
    "K": "#1a1a1a",
    "R": "#e85d3a",
    "r": "#c94020",
    "W": "#f5f5f5",
    "w": "#d0d0d0",
    "B": "#3aa9e0",
    "L": "#a8d8ea",
    "G": "#5a5a5a",
    "g": "#8a8a8a",
    "O": "#ff8c00",
    "Y": "#ffd54a",
}


# ---------------------------------------------------------------------------
# RocketLoadingBar
# ---------------------------------------------------------------------------

class RocketLoadingBar(ctk.CTkFrame):
    SKY_COLOR   = "#0a1845"
    COVER_COLOR = "#202030"

    # The cover boundary is positioned this fraction across the rocket's
    # width — putting the seam INSIDE the tail-fin region (cols 7..10 of
    # the 36-wide sprite are fully opaque top-to-bottom), so the swept
    # fins mask the seam completely.  9 / 36 ≈ 0.25.
    COVER_INSET_FRAC = 0.25

    def __init__(self, master, *,
                 height: int = 80, px: int = 4,
                 min_width: int = 240) -> None:
        super().__init__(master, fg_color="transparent")

        self._ch  = int(height)
        self._px  = int(px)
        self._min_width = int(min_width)
        self._cw  = self._min_width    # will be updated on first <Configure>

        # rocket geometry in canvas pixels
        self._rocket_w = _ROCKET_W_CHARS * self._px
        self._rocket_h = _ROCKET_H_CHARS * self._px

        # animation state
        self._progress = 0.0
        self._running  = False
        self._stopped_done = False
        self._t_anim   = 0
        self._after_id = None

        # Star positions stored as normalized (0..1) coords so we can rescale
        # when the canvas resizes.
        self._stars = self._generate_stars(count=80)

        self._canvas = tk.Canvas(
            self,
            width=self._cw, height=self._ch,
            bg=self.SKY_COLOR,
            highlightthickness=0, borderwidth=0,
        )
        self._canvas.pack(fill="both", expand=True)

        # Re-render when our allocated size changes.  We watch our own
        # <Configure> rather than the canvas's so we react to the parent's
        # geometry decisions.
        self.bind("<Configure>", self._on_resize)

        self._render_static()
        self._render_rocket()

    # -----------------------------------------------------------------
    # Resize
    # -----------------------------------------------------------------

    def _on_resize(self, event) -> None:
        new_w = max(self._min_width, int(event.width))
        if new_w == self._cw:
            return
        self._cw = new_w
        self._canvas.configure(width=self._cw)
        self._render_static()
        self._render_rocket()

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._stopped_done = False
        self._t_anim = 0
        self._progress = 0.0
        self._tick()

    def stop(self) -> None:
        self._running = False
        self._stopped_done = True
        self._progress = 1.0
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._render_rocket()

    def set_progress(self, frac: float) -> None:
        self._progress = max(0.0, min(1.0, float(frac)))
        self._render_rocket()

    # -----------------------------------------------------------------
    # Animation
    # -----------------------------------------------------------------

    def _tick(self) -> None:
        if not self._running:
            return
        self._t_anim += 1
        # Indeterminate progress eases asymptotically toward ~0.94 so the
        # rocket never quite "completes" while the sim is still going.
        TIME_CONSTANT = 240.0
        ASYMPTOTE     = 0.94
        self._progress = ASYMPTOTE * (1.0 - exp(-self._t_anim / TIME_CONSTANT))
        self._render_rocket()
        self._after_id = self.after(50, self._tick)

    # -----------------------------------------------------------------
    # Drawing
    # -----------------------------------------------------------------

    def _generate_stars(self, *, count: int) -> list[tuple[float, float, str]]:
        rng = random.Random(20260630)
        stars: list[tuple[float, float, str]] = []
        for _ in range(count):
            nx = rng.uniform(0.01, 0.99)
            ny = rng.uniform(0.05, 0.95)
            color = "#ffe066" if rng.random() < 0.15 else "#f5f5f5"
            stars.append((nx, ny, color))
        return stars

    def _render_static(self) -> None:
        self._canvas.delete("static")
        # full-canvas sky
        self._canvas.create_rectangle(
            0, 0, self._cw, self._ch,
            fill=self.SKY_COLOR, outline="", tags="static",
        )
        # moon — small, top-right area
        moon_r = 8
        moon_x = self._cw - 28
        moon_y = 22
        self._canvas.create_oval(
            moon_x - moon_r, moon_y - moon_r,
            moon_x + moon_r, moon_y + moon_r,
            fill="#f1ecc7", outline="", tags="static",
        )
        # stars (positions denormalized to current canvas size)
        for (nx, ny, color) in self._stars:
            x = int(nx * self._cw)
            y = int(ny * self._ch)
            self._canvas.create_rectangle(
                x, y, x + 2, y + 2,
                fill=color, outline="", tags="static",
            )

    def _render_rocket(self) -> None:
        self._canvas.delete("dynamic")

        # The rocket's left edge sweeps from 0 to (W - rocket_w) as progress
        # goes from 0 to 1.  We clamp so the rocket stays fully on-screen.
        max_x = max(1, self._cw - self._rocket_w)
        rocket_x = int(self._progress * max_x)
        rocket_y = (self._ch - self._rocket_h) // 2

        # Cover boundary sits INSIDE the rocket's silhouette so the body
        # masks the seam.
        cover_left = rocket_x + int(self.COVER_INSET_FRAC * self._rocket_w)

        # 1) the unrevealed cover rectangle to the right of the boundary
        if cover_left < self._cw:
            self._canvas.create_rectangle(
                cover_left, 0, self._cw, self._ch,
                fill=self.COVER_COLOR, outline="", tags="dynamic",
            )

        # 2) flame flicker — a per-tick jitter on the trailing flame
        flicker = (self._t_anim // 2) % 3 if self._running else 0

        # 3) the rocket sprite (drawn ON TOP of the cover, so it occludes it)
        for r, row in enumerate(ROCKET_SPRITE):
            for c, ch in enumerate(row):
                if ch == " ":
                    continue
                color = ROCKET_COLORS.get(ch)
                if color is None:
                    continue
                x0 = rocket_x + c * self._px
                y0 = rocket_y + r * self._px
                # flame jitter on the leftmost columns (the trailing flame)
                if ch in ("O", "Y") and self._running:
                    x0 -= flicker
                self._canvas.create_rectangle(
                    x0, y0, x0 + self._px, y0 + self._px,
                    fill=color, outline="", tags="dynamic",
                )

        # 4) green check on the right edge when done
        if self._stopped_done:
            self._canvas.create_text(
                self._cw - 12, self._ch // 2,
                text="✓", fill="#5eead4",
                font=("TkDefaultFont", 14, "bold"),
                tags="dynamic", anchor="e",
            )
