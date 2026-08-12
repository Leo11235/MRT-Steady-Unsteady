"""
AppShell — the one window the whole app lives in.

Owns the top bar and a stack of pages that swap in place. Nothing ever opens a
second window except modals.

ADDING A PAGE
-------------
Add a row to PAGES: a key, the module that holds it, and the class name. The
shell imports it the first time you navigate there. Nothing else to wire.

    "settings": PageRef("src.ui.app.pages.settings_page", "SettingsPage")

If the module doesn't exist yet, the shell shows a placeholder instead of
crashing. That's what lets the app run before every page is written: pages come
online one at a time as their modules appear.

PAGE CONTRACT
-------------
A page is a CTkFrame subclass taking (master, on_navigate). Everything below is
optional and probed with hasattr:

    TITLE               class attribute, shown in the top bar
    on_show()           called each time the page is raised
    handle_shortcut(a)  called when a keyboard action fires while visible
    is_dirty()          True if navigating home should ask first
    reset_to_defaults() called when the user goes home
"""

from __future__ import annotations

import importlib
import tkinter as tk
from dataclasses import dataclass
from typing import Callable, Optional

import customtkinter as ctk

from src.ui.app import settings as user_settings
from src.ui.app import theme
from src.ui.app.pages.placeholder import PlaceholderPage
from src.ui.app.services.shortcuts import ShortcutRouter, load_bindings
from src.ui.app.widgets.confirm_button import ConfirmButton


@dataclass(frozen=True)
class PageRef:
    """Where to find a page, resolved on first navigation."""
    module: str
    cls: str


class AppShell(ctk.CTk):
    """The root window. One instance per run."""

    PAGES: dict[str, PageRef] = {
        "main":             PageRef("src.ui.app.pages.main_menu", "MainMenuPage"),
        "steady":           PageRef("src.ui.app.pages.steady_page", "SteadyPage"),
        "unsteady":         PageRef("src.ui.app.pages.unsteady_page", "UnsteadyPage"),
        "loading":          PageRef("src.ui.app.pages.loading_screen", "LoadingScreen"),
        "results":          PageRef("src.ui.app.pages.results_browser", "ResultsBrowserPage"),
        "steady_results":   PageRef("src.ui.app.pages.steady_results", "SteadyResultsPage"),
        "unsteady_results": PageRef("src.ui.app.pages.unsteady_results", "UnsteadyResultsPage"),
        "settings":         PageRef("src.ui.app.pages.settings_page", "SettingsPage"),
        "bug":              PageRef("src.ui.app.pages.bug_report", "BugReportPage"),
        "patchnotes":       PageRef("src.ui.app.pages.patchnotes", "PatchnotesPage"),
    }

    # Pages that suppress the Home button: main is home, loading shows Cancel
    # instead, and settings has its own Save/Cancel that own the navigation.
    _NO_HOME = ("main", "loading", "settings")

    def __init__(self) -> None:
        super().__init__()

        appearance = user_settings.get("theme_appearance", theme.APPEARANCE)
        ctk.set_appearance_mode(appearance)
        ctk.set_default_color_theme(theme.COLOR_THEME)

        self.title(f"{theme.APP_TITLE}")
        self.minsize(*theme.MIN_WINDOW)
        # Deliberately no geometry() call before maximising. An explicit
        # initial size gets remembered as the "restored" size, and on some
        # Windows setups Tk flashes it during startup — you see a full-screen
        # blank window snap down to 1100x720 and back.
        self._maximize()

        self._build_top_bar()

        self.body = ctk.CTkFrame(self, corner_radius=0, fg_color=("gray92", "gray14"))
        self.body.pack(side="top", fill="both", expand=True)

        self.pages: dict[str, ctk.CTkFrame] = {}
        self.current_page: Optional[str] = None
        # Where a run was launched from, so Cancel knows where to return.
        self._pre_loading_page: Optional[str] = None

        self.shortcut_router = ShortcutRouter(self, self._dispatch_shortcut)

        self.go("main")

        # Re-assert the maximised state after the first layout pass. Tk on
        # Windows sometimes drops it during initial geometry negotiation.
        self.after_idle(self._maximize)
        self.after(100, self._maximize)

    # ==================================================================
    # Window
    # ==================================================================

    def _maximize(self) -> None:
        """Fill the screen, by whichever mechanism this platform supports."""
        try:
            self.state("zoomed")               # Windows
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)   # some Linux window managers
            return
        except tk.TclError:
            pass
        try:
            # macOS and the rest: size to the screen rather than going true
            # fullscreen, so the title bar and menu bar stay reachable.
            self.geometry(f"{self.winfo_screenwidth()}x{self.winfo_screenheight()}+0+0")
        except Exception:                       # noqa: BLE001
            pass

    # ==================================================================
    # Top bar
    # ==================================================================

    def _build_top_bar(self) -> None:
        self.top_bar = ctk.CTkFrame(self, height=theme.TOP_BAR_HEIGHT, corner_radius=0)
        self.top_bar.pack(side="top", fill="x")
        self.top_bar.pack_propagate(False)

        self.home_btn = ctk.CTkButton(
            self.top_bar, text="Home", width=110,
            command=lambda: self.go("main"),
        )

        # Both destructive top-bar actions take two clicks. See ConfirmButton.
        self.cancel_btn = ConfirmButton(
            self.top_bar, text="Cancel run", confirm_text="Confirm cancel",
            command=self._do_cancel,
        )
        self.halt_btn = ConfirmButton(
            self.top_bar, text="Halt & report", confirm_text="Confirm halt & report",
            command=self._do_halt_and_report,
            fg_color=theme.WARNING_STRONG, hover_color=theme.WARNING,
            confirm_color=theme.ERROR,
        )

        self.page_title = ctk.CTkLabel(
            self.top_bar, text="",
            font=ctk.CTkFont(size=theme.SIZE_H2, weight="bold"),
        )
        self.page_title.pack(side="left", padx=theme.PAD_M)

    def _refresh_top_bar(self) -> None:
        """Show the buttons the current page calls for.

        Loading gets Cancel and Halt; most pages get Home; main and settings
        get neither.
        """
        on_loading = self.current_page == "loading"
        wants_home = self.current_page not in self._NO_HOME

        def show(widget, visible: bool, **pack_kwargs) -> None:
            if visible and not widget.winfo_ismapped():
                widget.pack(side="left", pady=theme.PAD_S,
                            before=self.page_title, **pack_kwargs)
            elif not visible and widget.winfo_ismapped():
                widget.pack_forget()

        show(self.home_btn, wants_home, padx=(theme.PAD_M, theme.PAD_S))
        show(self.cancel_btn, on_loading, padx=(theme.PAD_M, theme.PAD_S))
        show(self.halt_btn, on_loading, padx=(0, theme.PAD_S))

        # Never leave a confirm button armed across a page change.
        self.cancel_btn.disarm()
        self.halt_btn.disarm()

    # ==================================================================
    # Navigation
    # ==================================================================

    def _ensure_page(self, name: str) -> ctk.CTkFrame:
        """Get a page, building it on first use.

        A page whose module doesn't exist yet becomes a placeholder. Any other
        import error also becomes a placeholder, but one that shows the error —
        a typo in a page shouldn't take down the whole app, and it certainly
        shouldn't do so silently.
        """
        if name in self.pages:
            return self.pages[name]
        if name not in self.PAGES:
            raise ValueError(f"unknown page: {name!r}")

        ref = self.PAGES[name]
        try:
            module = importlib.import_module(ref.module)
            page_cls = getattr(module, ref.cls)
            page = page_cls(self.body, on_navigate=self.go)
        except ModuleNotFoundError as exc:
            # Distinguish "this page isn't written yet" from "this page exists
            # but imports something broken". Only the former is expected.
            not_written = ref.module in str(exc)
            page = PlaceholderPage(
                self.body, on_navigate=self.go, page_name=name,
                reason="" if not_written else f"{type(exc).__name__}: {exc}",
            )
        except Exception as exc:                # noqa: BLE001
            page = PlaceholderPage(
                self.body, on_navigate=self.go, page_name=name,
                reason=f"{type(exc).__name__}: {exc}",
            )

        page.place(relwidth=1, relheight=1)
        self.pages[name] = page
        return page

    def go(self, name: str) -> None:
        """Switch to a page by key."""
        # Going home discards in-progress edits, so ask first if anything is
        # dirty, then reset the pages that know how.
        if name == "main" and self.current_page not in (None, "main"):
            if not self._confirm_discard_if_dirty():
                return
            for page in self.pages.values():
                if hasattr(page, "reset_to_defaults"):
                    try:
                        page.reset_to_defaults()
                    except Exception:           # noqa: BLE001
                        pass

        page = self._ensure_page(name)
        page.tkraise()
        self.current_page = name

        # Main menu carries its own hero text, so the top bar stays empty.
        self.page_title.configure(
            text="" if name == "main" else getattr(page, "TITLE", ""))
        self._refresh_top_bar()

        if hasattr(page, "on_show"):
            try:
                page.on_show()
            except Exception:                   # noqa: BLE001
                pass

    def _confirm_discard_if_dirty(self) -> bool:
        """Ask before throwing away edits. True means go ahead."""
        for page in self.pages.values():
            if not hasattr(page, "is_dirty"):
                continue
            try:
                if page.is_dirty():
                    from tkinter import messagebox
                    return messagebox.askyesno(
                        "Discard changes?",
                        "You have unsaved changes on this page.\n\n"
                        "Going back to the menu will clear them. Continue?",
                    )
            except Exception:                   # noqa: BLE001
                pass
        return True

    # ==================================================================
    # Runs
    # ==================================================================

    def start_loading_run(self, title: str, run_fn: Callable,
                          on_complete: Callable, on_error: Optional[Callable] = None) -> None:
        """Switch to the loading page and start a simulation on a worker thread.

        Any page can reach this with self.winfo_toplevel().start_loading_run(...).
        Fully implemented once the loading screen lands; until then the
        placeholder simply has no start_run to call.
        """
        if self.current_page not in (None, "loading"):
            self._pre_loading_page = self.current_page

        loading = self._ensure_page("loading")
        self.go("loading")
        if hasattr(loading, "start_run"):
            loading.start_run(title, run_fn, on_complete, on_error)

    def _do_cancel(self) -> None:
        """Second click on Cancel: stop the run and go back where we came from."""
        loading = self.pages.get("loading")
        if loading is not None and hasattr(loading, "cancel"):
            try:
                loading.cancel()
            except Exception:                   # noqa: BLE001
                pass
        target = self._pre_loading_page or "main"
        self._pre_loading_page = None
        self.go(target)

    def _do_halt_and_report(self) -> None:
        """Second click on Halt & report: stop the run, then open the bug page
        pre-filled with whatever the loading screen captured."""
        loading = self.pages.get("loading")
        terminal = ""
        if loading is not None:
            if hasattr(loading, "get_terminal_text"):
                try:
                    terminal = loading.get_terminal_text()
                except Exception:               # noqa: BLE001
                    pass
            if hasattr(loading, "cancel"):
                try:
                    loading.cancel()
                except Exception:               # noqa: BLE001
                    pass

        bug_page = self._ensure_page("bug")
        if hasattr(bug_page, "prefill"):
            try:
                bug_page.prefill(
                    title="Halted a simulation to report a problem",
                    diagnostics=terminal or "(no terminal output captured)",
                )
            except Exception:                   # noqa: BLE001
                pass
        self._pre_loading_page = None
        self.go("bug")

    # ==================================================================
    # Keyboard
    # ==================================================================

    def _dispatch_shortcut(self, action: str) -> None:
        """Route a keyboard action to whoever should handle it.

        Escape on the loading page drives the same two-press confirm as the
        Cancel button, so the keyboard and the mouse can't disagree about
        whether cancelling is armed. Everything else goes to the current page.
        """
        if action == "cancel":
            if self.current_page == "loading":
                self.cancel_btn.invoke()
            return

        page = self.pages.get(self.current_page or "")
        if page is not None and hasattr(page, "handle_shortcut"):
            try:
                page.handle_shortcut(action)
            except Exception:                   # noqa: BLE001
                pass

    def refresh_shortcuts(self) -> None:
        """Re-read the bindings. Called by the settings page after a rebind."""
        self.shortcut_router.rebind(load_bindings())

    def refresh_appearance(self) -> None:
        """Re-apply the light/dark setting. Called by the settings page."""
        ctk.set_appearance_mode(user_settings.get("theme_appearance", "system"))
