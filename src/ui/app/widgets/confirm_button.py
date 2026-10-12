"""
ConfirmButton — a button that needs two clicks, and forgets the first.

Used for the destructive actions in the top bar. Cancelling a run that's been
going for two minutes, or halting one to file a bug, are both things you want
to be deliberate about, but a modal dialog for them is heavy-handed.

First click swaps the label to a confirmation and starts a timer. A second
click inside the window fires. Otherwise the button quietly reverts, so a
mis-click costs nothing and leaves no dialog to dismiss.

    ConfirmButton(bar, text="Cancel", confirm_text="Confirm cancel",
                  command=stop_the_run)

The old shell carried two hand-rolled copies of this logic, one for cancel and
one for halt-and-report, which had already drifted apart in their timeout
handling.
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from src.ui.app import theme


# How long the armed state lasts before reverting. Long enough to move the
# mouse deliberately, short enough that a forgotten arm doesn't stay dangerous.
_CONFIRM_TIMEOUT_MS = 3000


class ConfirmButton(ctk.CTkButton):
    """A two-click button. `command` fires only on the second click."""

    def __init__(
        self,
        master,
        *,
        text: str,
        confirm_text: str,
        command: Callable[[], None],
        width: int = 140,
        confirm_width: Optional[int] = None,
        timeout_ms: int = _CONFIRM_TIMEOUT_MS,
        fg_color=None,
        hover_color=None,
        confirm_color=None,
        **kwargs,
    ) -> None:
        self._idle_text = text
        self._confirm_text = confirm_text
        self._idle_width = width
        # Confirmation labels are longer, so widen unless told otherwise.
        self._confirm_width = confirm_width or max(width, len(confirm_text) * 9 + 30)
        self._timeout_ms = timeout_ms
        self._real_command = command

        self._idle_color = fg_color if fg_color is not None else theme.MRT_RED_THEMED
        self._confirm_color = (confirm_color if confirm_color is not None
                               else theme.WARNING_STRONG)

        self._armed = False
        self._timer: Optional[str] = None

        super().__init__(
            master, text=text, width=width,
            fg_color=self._idle_color,
            hover_color=hover_color if hover_color is not None else theme.MRT_RED_HOVER,
            command=self._on_click,
            **kwargs,
        )

    # ------------------------------------------------------------------

    def _on_click(self) -> None:
        if not self._armed:
            self.arm()
            return
        self.disarm()
        self._real_command()

    def arm(self) -> None:
        """Enter the confirmation state and start the revert timer."""
        self._cancel_timer()
        self._armed = True
        self.configure(text=self._confirm_text, width=self._confirm_width,
                       fg_color=self._confirm_color)
        self._timer = self.after(self._timeout_ms, self.disarm)

    def disarm(self) -> None:
        """Back to the resting state.

        Called on timeout, after firing, and whenever the shell swaps pages —
        an armed button left over from a previous visit would be a trap.
        """
        self._cancel_timer()
        self._armed = False
        self.configure(text=self._idle_text, width=self._idle_width,
                       fg_color=self._idle_color)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            try:
                self.after_cancel(self._timer)
            except Exception:                   # noqa: BLE001
                pass
            self._timer = None

    @property
    def is_armed(self) -> bool:
        return self._armed
