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
from src.ui.app.services import i18n
from src.ui.app.services.shortcuts import ShortcutRouter
from src.ui.app.pages.main_menu import MainMenuPage
from src.ui.app.pages.steady_page import SteadyPage
from src.ui.app.pages.unsteady_page import UnsteadyPage
from src.ui.app.pages.results_browser import ResultsBrowserPage
from src.ui.app.pages.bug_report import BugReportPage
from src.ui.app.pages.settings_page import SettingsPage
from src.ui.app.pages.loading_screen import LoadingScreen
from src.ui.app.pages.steady_results import SteadyResultsPage
from src.ui.app.pages.unsteady_results import UnsteadyResultsPage
from src.ui.app.pages.patchnotes import PatchnotesPage


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
        "patchnotes":        PatchnotesPage,
    }

    def __init__(self) -> None:
        super().__init__()

        # ---- global appearance -------------------------------------------
        ctk.set_appearance_mode(theme.APPEARANCE)
        ctk.set_default_color_theme(theme.COLOR_THEME)

        # ---- window chrome -----------------------------------------------
        self.title(theme.APP_TITLE)
        # NOTE: we deliberately DON'T call self.geometry(...) before the
        # zoom attempt below.  Setting an explicit initial geometry gets
        # baked in as the "unzoomed" size, and on some Windows setups Tk
        # briefly falls back to it during startup — which produces the
        # "blank fullscreen for a second, then shrinks" flicker.
        self.minsize(*theme.MIN_WINDOW)
        self._start_maximized()

        # ---- top bar -----------------------------------------------------
        self.top_bar = ctk.CTkFrame(self, height=theme.TOP_BAR_HEIGHT, corner_radius=0)
        self.top_bar.pack(side="top", fill="x")
        self.top_bar.pack_propagate(False)

        self.home_btn = ctk.CTkButton(
            self.top_bar,
            text=i18n.t("topbar.home"),
            width=110,
            command=lambda: self.go("main"),
        )
        # Cancel button — replaces Home while we're on the loading page.
        self.cancel_btn = ctk.CTkButton(
            self.top_bar,
            text=i18n.t("topbar.cancel"),
            width=140,
            fg_color=theme.MRT_RED_THEMED,
            hover_color=theme.MRT_RED_HOVER,
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

        # Global keyboard shortcuts.  The router owns the bind_all calls;
        # we forward every fire event to _dispatch_shortcut which then
        # delegates to the current page (if it implements handle_shortcut)
        # or handles it centrally (Esc while on the loading page).
        self.shortcut_router = ShortcutRouter(self, self._dispatch_shortcut)

        self.go("main")

        # Re-apply zoom after the first widget-build pass.  On Windows,
        # Tk sometimes drops the zoomed state during initial geometry
        # negotiation; re-asserting it here (once idle, and again 100ms
        # later) removes the "blank fullscreen → shrink to default" flash.
        self.after_idle(self._start_maximized)
        self.after(100, self._start_maximized)

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
        # First, check if any dirty page objects to the reset.
        if page_name == "main" and self.current_page not in (None, "main"):
            if not self._confirm_discard_if_dirty():
                return   # user cancelled — stay on the current page
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
        # Prefer a translated title if one exists; fall back to the page's
        # TITLE class attribute otherwise.  Translation key convention:
        # "page.<key>", where <key> is the shell's PAGES dict key.
        i18n_key = f"page.{page_name}"
        translated = i18n.t(i18n_key)
        title = translated if translated != i18n_key else getattr(page, "TITLE", "")
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
        """Swap between Home and Cancel based on the active page.

        Home is suppressed on `settings` because that page owns its own
        Cancel / Save buttons that already handle navigation.
        """
        want_cancel = (self.current_page == "loading")
        want_home   = (self.current_page not in ("main", "loading", "settings"))

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
            self.cancel_btn.configure(text=i18n.t("topbar.cancel"), width=140)
        elif state == "confirm":
            self.cancel_btn.configure(text=i18n.t("topbar.confirm_cancel"), width=200)
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
    # Keyboard-shortcut dispatch
    # ----------------------------------------------------------------------

    def _dispatch_shortcut(self, action: str) -> None:
        """Called by ShortcutRouter whenever a bound key is pressed.

        - "cancel" while on the loading screen: reuses the Cancel-button
          state machine.  First press arms the confirm state; second press
          within the timeout window actually cancels.  Everywhere else
          Esc is ignored.
        - Anything else: forward to the current page's handle_shortcut()
          if it defines one.
        """
        if action == "cancel":
            if self.current_page == "loading":
                self._on_cancel_click()
            return

        page = self.pages.get(self.current_page or "")
        if page is not None and hasattr(page, "handle_shortcut"):
            try:
                page.handle_shortcut(action)
            except Exception:
                pass

    def refresh_shortcuts(self) -> None:
        """Called by the Settings page after the user rebinds actions."""
        from src.ui.app.services.shortcuts import load_bindings
        self.shortcut_router.rebind(load_bindings())

    def rebuild_all_pages(self) -> None:
        """Nuke every cached page and rebuild the current one.  Used by
        the language switcher — CustomTkinter has no live-retranslate,
        so the only reliable way to get every label / button / tab
        header into the new language is to rebuild them from scratch.

        Front-end top-bar buttons get their text refreshed here too so
        Home / Cancel switch language without a page navigation."""
        current = self.current_page or "main"

        # Refresh top-bar chrome that lives outside the page stack.
        try:
            self.home_btn.configure(text=i18n.t("topbar.home"))
        except Exception:
            pass
        try:
            self.cancel_btn.configure(text=i18n.t("topbar.cancel"))
        except Exception:
            pass

        # Destroy every cached page.
        for _name, page in list(self.pages.items()):
            try:
                page.destroy()
            except Exception:
                pass
        self.pages.clear()

        # Rebuild the page the user was on.  If we were on "loading" or
        # some transient page, drop back to "main" — safer than trying
        # to re-enter a mid-run state.
        target = current if current not in ("loading",) else "main"
        self.current_page = None
        self.go(target)

    # ----------------------------------------------------------------------
    # Dirty-check on Home
    # ----------------------------------------------------------------------

    def _confirm_discard_if_dirty(self) -> bool:
        """If any cached page reports is_dirty(), pop a confirm dialog.
        Returns True if the user chose to discard (or nothing was dirty)."""
        dirty = False
        for _name, page in self.pages.items():
            if hasattr(page, "is_dirty"):
                try:
                    if page.is_dirty():
                        dirty = True
                        break
                except Exception:
                    pass
        if not dirty:
            return True
        from tkinter import messagebox
        return messagebox.askyesno(
            i18n.t("confirm.discard_title"),
            i18n.t("confirm.discard_body"),
        )

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
