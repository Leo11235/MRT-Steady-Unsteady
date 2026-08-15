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
        "version": "1.5",
        "date":    "2026-08-15",
        "notes": [
            "Every input now carries its own unit. Pick the unit you have "
            "the number in from the dropdown next to each field and the "
            "program converts it; nothing has to be entered in SI any more.",

            "Results pages have an SI / IMP / MRT toggle that reformats "
            "every number on the page at once, graphs included.",

            "Steady parametric studies graph from a dialog that lets you "
            "pick the axes and hold the other swept variables at a chosen "
            "value, in 2D or 3D.",

            "Unsteady graphs are now chosen from a searchable list of all "
            "28 figures and drawn inline on the results page. They're the "
            "same figures that go into graphs.pdf, so the two can't drift.",

            "Added an 'instant' valve model, and removed the NHNE "
            "injector model, which was never implemented.",

            "Propellant chemistry and regression-law defaults now come "
            "from a documented file instead of being blank.",

            "The loading screen can halt a stuck run and take you straight "
            "to a bug report with the terminal output already attached.",

            "Backend test suite added under tests/, and the build files "
            "moved into build_tools/.",

            "Removed the incomplete French translation.",

            "Fixed various bugs (launch angle being converted from degrees "
            "twice, so trajectories ran nearly vertical; the main "
            "parachute's area being computed from the drogue's diameter; "
            "the 'one or the other' fields always picking the first option "
            "regardless of which one you filled in; the phase-6 duration "
            "setting being ignored and capped at 60 s; unit dropdowns "
            "drifting by a rounding error each time you switched them)",
        ],
    },
    {
        "version": "1.4",
        "date":    "2026-08-02",
        "notes": [
            "Improved bug reporting to collect more diagnostic information.",
            "Added \"Show in folder\" button for simulation results.",
            "Cleaned terminal screen printout in loading page.",
            "Added steady parametric study graphing feature. You can now build 2D and 3D graphs from any parametric study.",
            "Added parametric study input units for swept variables.",
            "Error popup: long exception messages are now in a scrollable popup so Back/Report buttons always stay visible.",
            
            "Fixed various bugs (unsteady crash at fuel burnout while "
            "the tank still had liquid; sigmoid valve model rejecting "
            "configs that omitted an input it didn't actually use; "
            "division-by-zero crashes during the phase-1 ignition "
            "transient, especially with slow-opening linear valves; "
            "deleting a saved run left its PDF/PNG folder behind; "
            "\"Show in folder\" button opening Documents instead of the "
            "run's actual folder; steady mode keys not getting validated properly for hotfire and parametric study)",
        ],
    },
    {
        "version": "1.3",
        "date":    "2026-07-27",
        "notes": [
            "Inputs now use diameters instead of radii and areas across "
            "the whole program.",
            
            "Every unsteady physics model dropdown now shows a short description of the model.",
            
            "Added hover tooltips everywhere.",
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
            text="Release notes",
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
