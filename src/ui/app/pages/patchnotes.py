"""
PatchnotesPage — scrollable list of release notes.

Reachable by clicking the version chip on the main menu.  Content
lives in the PATCHNOTES list below; each entry is a dict with a
`version`, `date`, and `notes` (a list of short strings).

To add a new release: prepend a new dict at the top of the list.
Keep the newest release first so users see current changes first.
"""

from __future__ import annotations

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.version import VERSION


# ---------------------------------------------------------------------------
# Release notes  (newest first)
# ---------------------------------------------------------------------------

PATCHNOTES: list[dict] = [
    {
        "version": "1.4",
        "date":    "2026-08-02",
        "notes": [
            "Improved bug reporting",
            "Added \"Show in folder\" button for simulation results",
            "Cleaned terminal screen printout in loading page",
            
            "Fixed various bugs (unsteady crash at fuel burnout while "
            "the tank still had liquid; sigmoid valve model rejecting "
            "configs that omitted an input it didn't actually use; "
            "division-by-zero crashes during the phase-1 ignition "
            "transient, especially with slow-opening linear valves; "
            "deleting a saved run left its PDF/PNG folder behind; "
            "\"Show in folder\" button opening Documents instead of the "
            "run's actual folder)",
        ],
    },
    {
        "version": "1.3",
        "date":    "2026-07-27",
        "notes": [
            "Added this patchnotes page. Click the version chip on the "
            "home screen at any time to see what changed in each release.",
            
            "Inputs now use diameters instead of radii and areas across "
            "the whole program",
            
            "Every unsteady physics model dropdown now shows a short description of the model",
            
            "Added hover tooltips everywhere",
        ],
    },
    {
        "version": "1.2",
        "date":    "2026-07-24",
        "notes": [
            "Fixed 'Simulation ran but produced no result file' error in "
            "the installed .exe. In frozen builds, the backend was "
            "writing results into the read-only install directory; the "
            "UI now reconciles files back into the writable per-user "
            "location automatically.",
            
            "Fixed missing rocketcea data-file error on first frozen run.",
            "Fixed missing pypropep data-file error (steady sims complaining "
            "about missing chamber temperature).",
            
            "Bug reports now include the app version at the top of the "
            "auto-filled body AND as a dedicated field in the email.",
            "Version footer added to the home screen so you can always "
            "see which build you're on.",
        ],
    },
    {
        "version": "1.1",
        "date":    "2026-07-22",
        "notes": [
            "First installer-based release. App now installs from a "
            "standard Windows setup .exe with an uninstaller entry in "
            "Add/Remove Programs, upgrades cleanly over previous "
            "versions, and preserves presets & past runs across "
            "reinstalls.",
        ],
    },
    {
        "version": "1.0",
        "date":    "2026-07-18",
        "notes": [
            "Initial release. Steady-state and unsteady simulations, "
            "browsable results page, "
            "parametric sweeps, presets, saved-runs browser, integrated "
            "bug reporting, keyboard shortcuts, (incomplete) French translation.",
        ],
    },
]


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class PatchnotesPage(ctk.CTkFrame):
    """A scrolling list of releases, newest first."""

    TITLE = "What's new"

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate
        self._build()

    def _build(self) -> None:
        # Header block
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=theme.PAD_L, pady=(theme.PAD_L, theme.PAD_S))
        ctk.CTkLabel(
            header,
            text=f"Release notes",
            font=ctk.CTkFont(size=theme.SIZE_HERO, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text=f"Currently on v{VERSION}",
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            text_color=theme.TEXT_MUTED,
        ).pack(anchor="w", pady=(theme.PAD_XS, 0))

        # Scrollable body
        body = ctk.CTkScrollableFrame(self, label_text="",
                                      fg_color="transparent")
        body.pack(fill="both", expand=True,
                  padx=theme.PAD_L, pady=(theme.PAD_S, theme.PAD_L))

        for entry in PATCHNOTES:
            self._render_entry(body, entry)

    def _render_entry(self, parent, entry: dict) -> None:
        # One card per release.
        card = ctk.CTkFrame(parent, fg_color=("gray92", "gray17"),
                            corner_radius=8)
        card.pack(fill="x", pady=theme.PAD_S)

        # Version + date row
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=theme.PAD_M, pady=(theme.PAD_M, theme.PAD_XS))
        ctk.CTkLabel(
            top, text=f"v{entry.get('version', '?')}",
            font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        ).pack(side="left")
        date = entry.get("date")
        if date:
            ctk.CTkLabel(
                top, text=date,
                font=ctk.CTkFont(size=theme.SIZE_BODY),
                text_color=theme.TEXT_MUTED,
            ).pack(side="right")

        # Bullet list
        notes = entry.get("notes") or []
        if not notes:
            ctk.CTkLabel(
                card, text="(no notes)",
                text_color=theme.TEXT_FAINT,
                font=ctk.CTkFont(size=theme.SIZE_BODY, slant="italic"),
            ).pack(anchor="w", padx=theme.PAD_L, pady=(0, theme.PAD_M))
            return

        for line in notes:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=theme.PAD_L, pady=1)
            ctk.CTkLabel(
                row, text="•",
                font=ctk.CTkFont(size=theme.SIZE_BODY),
                text_color=theme.TEXT_MUTED,
                width=14, anchor="nw",
            ).pack(side="left", padx=(0, theme.PAD_XS))
            ctk.CTkLabel(
                row, text=line,
                font=ctk.CTkFont(size=theme.SIZE_BODY),
                wraplength=760, justify="left", anchor="w",
            ).pack(side="left", fill="x", expand=True)

        # Bottom padding
        ctk.CTkFrame(card, height=theme.PAD_S, fg_color="transparent") \
            .pack(fill="x")

    # Standard reset hook (called by the shell on Home click)
    def reset_to_defaults(self) -> None:
        pass

    def on_show(self) -> None:
        pass
