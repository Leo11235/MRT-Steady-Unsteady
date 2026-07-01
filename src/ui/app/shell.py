"""
AppShell — the persistent application window.

Holds the top bar (with home button + page title) and a page stack
that lets us swap pages without ever opening a second window.

To add a new page:
  1. Write a new class in src/ui/app/pages/<name>.py with class-attribute TITLE.
  2. Import it here and add it to the PAGES dict below.
"""

from __future__ import annotations

import tkinter as tk

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.pages.main_menu import MainMenuPage
from src.ui.app.pages.steady_page import SteadyPage
from src.ui.app.pages.unsteady_page import UnsteadyPage
from src.ui.app.pages.results_browser import ResultsBrowserPage
from src.ui.app.pages.bug_report import BugReportPage
from src.ui.app.pages.settings_page import SettingsPage
from src.ui.app.pages.loading_screen import LoadingScreen
from src.ui.app.pages.steady_results import SteadyResultsPage
from src.ui.app.pages.unsteady_results import UnsteadyResultsPage


# How long (ms) the "Confirm cancel" state sticks around before reverting
# to plain "Cancel" if the user doesn't click a second time.
_CONFIRM_CANCEL_TIMEOUT_MS = 3000


class AppShell(ctk.CTk):
    """The root window.  One instance per application run."""

    # ordered so debugging dumps come out predictably
    PAGES = {
        "main":              MainMenuPage,
        "steady":            SteadyPage,
        "unsteady":          UnsteadyPage,
        "results":           ResultsBrowserPage,
        "bug":               BugReportPage,
        "settings":          SettingsPage,
        "loading":           LoadingScreen,
        "steady_results":    SteadyResultsPage,
        "unsteady_results":  UnsteadyResultsPage,
    }

    def __init__(self) -> None:
        super().__init__()

        # ---- global appearance -------------------------------------------
        ctk.set_appearance_mode(theme.APPEARANCE)
        ctk.set_default_color_theme(theme.COLOR_THEME)

        # ---- window chrome -----------------------------------------------
        self.title(theme.APP_TITLE)
        self.geometry(f"{theme.WINDOW_W}x{theme.WINDOW_H}")
        self.minsize(*theme.MIN_WINDOW)
        self._start_maximized()

        # ---- top bar -----------------------------------------------------
        self.top_bar = ctk.CTkFrame(self, height=theme.TOP_BAR_HEIGHT, corner_radius=0)
        self.top_bar.pack(side="top", fill="x")
        self.top_bar.pack_propagate(False)

        self.home_btn = ctk.CTkButton(
            self.top_bar,
            text="⌂  Home",
            width=110,
            command=lambda: self.go("main"),
        )
        # Cancel button — replaces Home while we're on the loading page.
        self.cancel_btn = ctk.CTkButton(
            self.top_bar,
            text="✕  Cancel",
            width=140,
            fg_color=theme.MRT_RED_THEMED,
            hover_color=("#7a131a", "#a01a26"),
            command=self._on_cancel_click,
        )
        # cancel-button state machine
        self._cancel_state: str = "cancel"           # 'cancel' | 'confirm'
        self._cancel_reset_after_id: str | None = None

        self.page_title = ctk.CTkLabel(
            self.top_bar,
            text="",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
        )
        self.page_title.pack(side="left", padx=theme.PAD_M)

        # ---- body / page stack -------------------------------------------
        self.body = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray14"))
        self.body.pack(side="top", fill="both", expand=True)

        # LAZY page-building: pages are built on first navigation.
        self.pages: dict[str, ctk.CTkFrame] = {}

        self.current_page: str | None = None
        # Remember which page started the current run — used by cancel to
        # know where to send the user back.
        self._pre_loading_page: str | None = None

        self.go("main")

    # ----------------------------------------------------------------------
    # Startup — maximize the window on every OS we ship for.
    # ----------------------------------------------------------------------

    def _start_maximized(self) -> None:
        try:
            # Windows path
            self.state("zoomed")
            return
        except tk.TclError:
            pass
        try:
            # Some Linux WMs support this attribute
            self.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        # Fallback (macOS, other Linux WMs): size the window to the screen
        # rather than going full "fullscreen" — that way title bars and
        # the OS menu bar stay visible.
        try:
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            self.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            pass

    # ----------------------------------------------------------------------
    # Navigation
    # ----------------------------------------------------------------------

    def _ensure_page(self, page_name: str) -> ctk.CTkFrame:
        """Get-or-build a page on demand."""
        if page_name not in self.PAGES:
            raise ValueError(f"unknown page: {page_name!r}")
        if page_name not in self.pages:
            page_cls = self.PAGES[page_name]
            page = page_cls(self.body, on_navigate=self.go)
            page.place(relwidth=1, relheight=1)
            self.pages[page_name] = page
        return self.pages[page_name]

    def go(self, page_name: str) -> None:
        """Switch to the named page (case-sensitive key in PAGES)."""
        # Navigating HOME wipes any editable state on the pages that
        # implement reset_to_defaults() — steady, unsteady, bug report.
        if page_name == "main" and self.current_page not in (None, "main"):
            for _name, _page in self.pages.items():
                if hasattr(_page, "reset_to_defaults"):
                    try:
                        _page.reset_to_defaults()
                    except Exception:
                        pass

        page = self._ensure_page(page_name)
        page.tkraise()
        self.current_page = page_name

        # update title
        title = getattr(page, "TITLE", "")
        self.page_title.configure(text=title)

        # ---- chrome: which top-bar button is shown? --------------------
        # On the loading page we show a red Cancel; on main we show
        # nothing; elsewhere we show Home.
        self._refresh_top_bar_button()

        if page_name == "main":
            self.page_title.configure(text="")

        # let the page do per-show work
        if hasattr(page, "on_show"):
            page.on_show()

    def _refresh_top_bar_button(self) -> None:
        """Swap between Home and Cancel based on the active page."""
        want_cancel = (self.current_page == "loading")
        want_home   = (self.current_page not in ("main", "loading"))

        if want_cancel:
            if self.home_btn.winfo_ismapped():
                self.home_btn.pack_forget()
            if not self.cancel_btn.winfo_ismapped():
                self.cancel_btn.pack(
                    side="left",
                    padx=(theme.PAD_M, theme.PAD_S),
                    pady=theme.PAD_S,
                    before=self.page_title,
                )
            # Whenever we (re-)enter the loading page, reset the state to
            # plain 'Cancel' — no lingering 'Confirm cancel' from a past run.
            self._set_cancel_state("cancel")
        else:
            if self.cancel_btn.winfo_ismapped():
                self.cancel_btn.pack_forget()
            self._clear_cancel_timeout()

            if want_home:
                if not self.home_btn.winfo_ismapped():
                    self.home_btn.pack(
                        side="left",
                        padx=(theme.PAD_M, theme.PAD_S),
                        pady=theme.PAD_S,
                        before=self.page_title,
                    )
            else:  # main
                if self.home_btn.winfo_ismapped():
                    self.home_btn.pack_forget()

    # ----------------------------------------------------------------------
    # Cancel button state machine
    # ----------------------------------------------------------------------

    def _set_cancel_state(self, state: str) -> None:
        """state ∈ {'cancel', 'confirm'}"""
        self._clear_cancel_timeout()
        if state == "cancel":
            self.cancel_btn.configure(text="✕  Cancel", width=140)
        elif state == "confirm":
            self.cancel_btn.configure(text="Confirm cancel", width=180)
            # Auto-revert after N seconds if the user doesn't click again.
            self._cancel_reset_after_id = self.after(
                _CONFIRM_CANCEL_TIMEOUT_MS,
                lambda: self._set_cancel_state("cancel"),
            )
        self._cancel_state = state

    def _clear_cancel_timeout(self) -> None:
        if self._cancel_reset_after_id is not None:
            try:
                self.after_cancel(self._cancel_reset_after_id)
            except Exception:
                pass
            self._cancel_reset_after_id = None

    def _on_cancel_click(self) -> None:
        if self._cancel_state == "cancel":
            # First click — arm the confirm state.
            self._set_cancel_state("confirm")
            return

        # Second click — actually cancel.
        loading = self.pages.get("loading")
        if loading is not None:
            try:
                loading.cancel()
            except Exception:
                pass
        target = self._pre_loading_page or "main"
        self._pre_loading_page = None
        self.go(target)

    # ----------------------------------------------------------------------
    # Loading-screen helper
    # ----------------------------------------------------------------------

    def start_loading_run(
        self,
        title: str,
        run_fn,
        on_complete,
        on_error=None,
    ) -> None:
        """
        Switch to the LoadingScreen page and kick off `run_fn`.

        Any page can call this via:
            self.winfo_toplevel().start_loading_run(...)
        """
        # Remember where we were so cancel can return the user here.
        if self.current_page not in (None, "loading"):
            self._pre_loading_page = self.current_page

        loading = self._ensure_page("loading")
        self.go("loading")
        loading.start_run(title, run_fn, on_complete, on_error)
