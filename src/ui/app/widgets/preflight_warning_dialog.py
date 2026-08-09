"""Modal shown when preflight checks flag input-range warnings.

Users see a scrollable list of the flagged warnings (severity + human
message + offending values) and choose whether to run the sim anyway
or cancel and go back to fix the inputs.

Usage:
    PreflightWarningDialog(
        parent=self,
        warnings=warnings_dict,     # {id: {severity, message, ...}}
        on_proceed=lambda: self._start_sim(cfg),
        on_cancel=lambda: None,
    )

on_proceed / on_cancel fire on the corresponding button.  The modal
uses grab_set so the main window is blocked while it's open.
"""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from src.ui.app import theme


# Colour hints per severity, matching the styling used on the results
# page's warnings tab.
_SEVERITY_COLOUR = {
    "advisory": ("#f4a261", "#f4a261"),
    "warning":  ("#e76f51", "#ff9e7a"),
    "critical": ("#b00020", "#ff6b6b"),
}


class PreflightWarningDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent,
        *,
        warnings: dict,
        on_proceed: Callable[[], None],
        on_cancel:  Callable[[], None] = lambda: None,
        title: str = "Input warnings",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("620x420")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.resizable(False, True)

        self._on_proceed = on_proceed
        self._on_cancel  = on_cancel
        self._decided    = False   # so window-close counts as Cancel

        # ---- footer FIRST so it always stays visible -----------------
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", side="bottom",
                    padx=theme.PAD_L, pady=theme.PAD_M)

        ctk.CTkButton(
            footer, text="Cancel", width=120,
            fg_color="transparent", border_width=1,
            text_color=("gray25", "gray75"),
            command=self._click_cancel,
        ).pack(side="right")

        # Run-anyway button uses the same red as the "Report a bug"
        # button to signal "you're proceeding with something risky".
        ctk.CTkButton(
            footer, text="Run anyway", width=140,
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
            fg_color=theme.MRT_RED_THEMED,
            hover_color=theme.MRT_RED_HOVER,
            command=self._click_proceed,
        ).pack(side="right", padx=(0, theme.PAD_S))

        # ---- header block --------------------------------------------
        n = len(warnings)
        head_text = (
            f"{n} input warning{'s' if n != 1 else ''} were flagged for "
            "this configuration. Review below, then either cancel and "
            "fix the inputs, or run anyway."
        )
        ctk.CTkLabel(
            self, text="Input warnings",
            font=ctk.CTkFont(size=theme.SIZE_H1, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        ).pack(pady=(theme.PAD_L, theme.PAD_XS), padx=theme.PAD_L,
               anchor="w")

        ctk.CTkLabel(
            self, text=head_text,
            font=ctk.CTkFont(size=theme.SIZE_BODY),
            text_color=theme.TEXT_MUTED,
            anchor="w", justify="left", wraplength=560,
        ).pack(fill="x", padx=theme.PAD_L, pady=(0, theme.PAD_M))

        # ---- scrollable warning body ---------------------------------
        body = ctk.CTkTextbox(
            self, wrap="word",
            font=ctk.CTkFont(family="Consolas", size=theme.SIZE_SMALL),
            fg_color=("gray92", "gray17"),
        )
        body.pack(fill="both", expand=True,
                  padx=theme.PAD_L, pady=(0, theme.PAD_M))
        body.insert("0.0", _format_warnings(warnings))
        body.configure(state="disabled")

        # Window-close ("X") counts as Cancel.
        self.protocol("WM_DELETE_WINDOW", self._click_cancel)

    # ------------------------------------------------------------------

    def _click_proceed(self) -> None:
        if self._decided:
            return
        self._decided = True
        self.destroy()
        try:
            self._on_proceed()
        except Exception:
            import traceback
            traceback.print_exc()

    def _click_cancel(self) -> None:
        if self._decided:
            return
        self._decided = True
        self.destroy()
        try:
            self._on_cancel()
        except Exception:
            import traceback
            traceback.print_exc()


def _format_warnings(warnings: dict) -> str:
    """Turn the warnings-dict into a readable multi-line block."""
    lines: list[str] = []
    for i, (key, entry) in enumerate(warnings.items(), start=1):
        if not isinstance(entry, dict):
            lines.append(f"[{i}] {key}: {entry}")
            continue
        severity = str(entry.get("severity", "?")).upper()
        message  = str(entry.get("message", "(no message)"))
        lines.append(f"[{severity}] {key}")
        lines.append(f"    {message}")
        for k, v in entry.items():
            if k in ("severity", "message"):
                continue
            lines.append(f"    {k}: {v}")
        lines.append("")
    return "\n".join(lines).rstrip()
