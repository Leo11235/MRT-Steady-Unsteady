"""
LoadingScreen — shown while a simulation runs.

Generic: anything wanting a "do slow work, show progress" flow calls

    shell.start_loading_run(title, run_fn, on_complete, on_error)

and this page handles the rest. It knows nothing about simulations.

HOW IT WORKS
------------
1. A daemon worker thread runs `run_fn`.
2. Process-wide stdout and stderr are redirected into a queue, so everything
   the backend prints lands in the terminal box live.
3. The worker drops its outcome into a SECOND queue rather than calling back.
4. The Tk main thread polls both queues every POLL_MS and does all the widget
   updates and callback dispatch.

The worker never touches a Tk widget, and never calls self.after(). That's not
paranoia: tkinter's after() from a non-main thread is not reliably routed on
every platform, and matplotlib refuses to build figures off the main thread. So
the finish callbacks — which may well draw plots — have to run on the main
thread, and the result queue is what guarantees that.
"""

from __future__ import annotations

import ctypes
import queue
import re
import sys
import threading
import time
import traceback
from typing import Any, Callable, Optional

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.widgets.loading_bar import RocketLoadingBar


# Phase markers the backend prints. phase_runner emits them upper-cased
# ("--- PHASE_2 ---"), so this has to be case-insensitive; a [Pp]hase pattern
# silently matches nothing against the real output.
_PHASE_RE = re.compile(r"\bphase[_\s]*([0-9]+[a-c]?)\b", re.IGNORECASE)


# =============================================================================
# Killing the worker
# =============================================================================
#
# A soft "please stop" flag isn't enough here. scipy's LSODA integrator is not
# reentrant and holds module-level state for the length of a solve, so if the
# worker is still integrating when the user starts a second run, the next
# solve_ivp raises IntegratorConcurrencyError. The thread has to ACTUALLY end
# and let scipy release its handle.
#
# CPython's PyThreadState_SetAsyncExc is the only way to do that from outside
# the thread. It schedules an exception to be raised at the target's next
# bytecode boundary. We use SystemExit rather than a custom exception because
# it takes Python's normal thread-shutdown path: finally blocks run, references
# drop, and the integrator's __del__ removes itself from scipy's registry.
#
# The API is unofficial but stable across every current CPython. On other
# implementations it simply isn't there and this degrades to a no-op.

def _kill_thread(thread: Optional[threading.Thread]) -> bool:
    """Async-raise SystemExit in a thread. True if the request was accepted."""
    if thread is None or not thread.is_alive() or thread.ident is None:
        return False
    try:
        raise_async = ctypes.pythonapi.PyThreadState_SetAsyncExc
    except AttributeError:
        return False                    # not CPython
    affected = raise_async(ctypes.c_ulong(thread.ident), ctypes.py_object(SystemExit))
    if affected > 1:
        # Hit more than one thread; undo it rather than leave the interpreter
        # with several pending async exceptions.
        raise_async(ctypes.c_ulong(thread.ident), None)
        return False
    return affected == 1


class _StreamToQueue:
    """A minimal file-like that forwards writes into a queue."""

    def __init__(self, sink: "queue.Queue[str]") -> None:
        self._sink = sink

    def write(self, data: str) -> int:
        if data:
            self._sink.put(data)
        return len(data)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        # Some libraries check this before deciding whether to emit colour.
        return False


# =============================================================================
# Friendlier failures
# =============================================================================
#
# Two backend exceptions are common enough, and cryptic enough on their own,
# to be worth translating before they reach the terminal.

def _friendly_hint(exc: BaseException) -> str:
    """A plain-English line to put above the traceback, or "" for none."""
    name = type(exc).__name__

    if isinstance(exc, KeyError):
        # The backend raises a bare KeyError naming the missing config key.
        # Without this you get a one-word traceback and no idea what to fix.
        field = str(exc).strip("'\"")
        try:
            from src.ui.app import field_registry as registry
            if registry.has(field):
                field = f"{registry.label(field)}  ({field})"
        except Exception:                       # noqa: BLE001
            pass
        return (f"[missing required input]  {field} was not set.\n"
                f"Go back, fill it in, and run again.")

    if name == "SolverStalledError":
        return ("[solver stalled]  The integrator stopped making progress, "
                "which usually means the operating point is physically "
                "unstable — chamber pressure very close to tank pressure, so "
                "the injector has almost no authority.\n"
                "Try a lower regression coefficient or a higher feed pressure "
                "loss.")

    return ""


# =============================================================================
# The page
# =============================================================================

class LoadingScreen(ctk.CTkFrame):
    TITLE = "Running…"

    POLL_MS = 80        # how often the main thread drains the queues

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        self._output_q: "queue.Queue[str]" = queue.Queue()
        self._result_q: "queue.Queue[tuple]" = queue.Queue()
        self._poll_id: Optional[str] = None

        self._on_complete: Optional[Callable[[Any], None]] = None
        self._on_error: Optional[Callable[[BaseException, str], None]] = None

        self._busy = False
        self._cancelled = False
        self._worker: Optional[threading.Thread] = None
        self._saved_stdout = None
        self._saved_stderr = None
        self._started_at: Optional[float] = None
        self._phase: Optional[str] = None

        self._build()

    # ==================================================================
    # Layout
    # ==================================================================

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)      # the terminal takes the slack

        self._title = ctk.CTkLabel(
            self, text="Running…", anchor="center",
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
        )
        self._title.grid(row=0, column=0, sticky="ew",
                         padx=theme.PAD_L, pady=(theme.PAD_L, theme.PAD_S))

        terminal_wrap = ctk.CTkFrame(self, fg_color="transparent")
        terminal_wrap.grid(row=1, column=0, sticky="nsew",
                           padx=theme.PAD_L, pady=theme.PAD_S)
        terminal_wrap.grid_columnconfigure(0, weight=1)
        terminal_wrap.grid_rowconfigure(0, weight=1)

        # Always dark regardless of theme: it's a console, and the backend's
        # output is easier to scan in monospace on black.
        self._terminal = ctk.CTkTextbox(
            terminal_wrap, wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=theme.TERMINAL_BG, text_color=theme.TERMINAL_FG,
            border_width=1, border_color=("gray30", "gray30"),
        )
        self._terminal.grid(row=0, column=0, sticky="nsew")
        self._terminal.configure(state="disabled")

        bar_wrap = ctk.CTkFrame(self, fg_color="transparent")
        bar_wrap.grid(row=2, column=0, sticky="ew",
                      padx=theme.PAD_L, pady=(theme.PAD_S, theme.PAD_L))
        bar_wrap.grid_columnconfigure(0, weight=1)

        self._bar = RocketLoadingBar(bar_wrap, height=80, px=4)
        self._bar.grid(row=0, column=0, sticky="ew", pady=(0, theme.PAD_S))

        self._status = ctk.CTkLabel(
            bar_wrap, text="", text_color=theme.TEXT_FAINT,
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        )
        self._status.grid(row=1, column=0, sticky="w", padx=4)

        # "Phase 3 · 34s elapsed", opposite the status on the same row.
        self._elapsed = ctk.CTkLabel(
            bar_wrap, text="", text_color=theme.TEXT_MUTED,
            font=ctk.CTkFont(size=theme.SIZE_SMALL),
        )
        self._elapsed.grid(row=1, column=0, sticky="e", padx=4)

    # ==================================================================
    # Public API
    # ==================================================================

    def start_run(self, title: str, run_fn: Callable[[], Any],
                  on_complete: Callable[[Any], None],
                  on_error: Optional[Callable[[BaseException, str], None]] = None) -> None:
        """Reset the page, capture output, and start the worker.

        Refuses to start while another run is in flight, rather than stacking
        two solvers on top of each other.
        """
        if self._busy:
            return
        self._busy = True
        self._cancelled = False
        self._on_complete = on_complete
        self._on_error = on_error

        self._title.configure(text=title)
        self._set_terminal("")
        self._status.configure(text="Starting…", text_color=theme.TEXT_FAINT)
        self._elapsed.configure(text="")
        self._started_at = time.monotonic()
        self._phase = None

        self._output_q = queue.Queue()
        self._result_q = queue.Queue()
        self._bar.start()
        self._schedule_poll()

        # Redirect the process's streams. This is global, but the worker is
        # the only thing producing output while a run is in flight.
        self._saved_stdout, self._saved_stderr = sys.stdout, sys.stderr
        sys.stdout = _StreamToQueue(self._output_q)
        sys.stderr = _StreamToQueue(self._output_q)

        self._worker = threading.Thread(target=self._run_worker,
                                        args=(run_fn,), daemon=True)
        self._worker.start()

    def get_terminal_text(self) -> str:
        """Everything currently in the terminal, for the bug report."""
        return self._terminal.get("0.0", "end").rstrip()

    def cancel(self) -> None:
        """Stop a running simulation.

        Two moves. First flip the flags so any result that's already in flight
        gets dropped rather than navigating the user somewhere unexpected.
        Then actually kill the worker, and wait briefly for it, so scipy has
        released the integrator before the next run starts. If it hasn't died
        within a few seconds we carry on anyway — a concurrency error on the
        next run is possible but rare, and hanging the UI is worse.
        """
        if not self._busy:
            return
        self._cancelled = True
        self._busy = False
        self._on_complete = None
        self._on_error = None
        self._teardown()
        self._bar.stop()
        self._status.configure(text="Cancelled", text_color=theme.WARNING_STRONG)

        worker, self._worker = self._worker, None
        if worker is not None and worker.is_alive():
            _kill_thread(worker)
            try:
                worker.join(timeout=3.0)
            except Exception:                   # noqa: BLE001
                pass

    @property
    def is_running(self) -> bool:
        return self._busy

    # ==================================================================
    # Worker
    # ==================================================================

    def _run_worker(self, run_fn: Callable[[], Any]) -> None:
        """Runs off the main thread. Only ever touches the result queue."""
        try:
            self._result_q.put(("ok", run_fn()))
        except SystemExit:
            # Injected by cancel(). The main thread already knows; exit quietly
            # so the traceback doesn't land in a terminal nobody is reading.
            return
        except BaseException as exc:            # noqa: BLE001 - reported, not handled
            self._result_q.put(("err", exc, traceback.format_exc()))

    # ==================================================================
    # Main-thread polling
    # ==================================================================

    def _schedule_poll(self) -> None:
        self._cancel_poll()
        self._poll_id = self.after(self.POLL_MS, self._poll)

    def _cancel_poll(self) -> None:
        if self._poll_id is not None:
            try:
                self.after_cancel(self._poll_id)
            except Exception:                   # noqa: BLE001
                pass
            self._poll_id = None

    def _poll(self) -> None:
        if self._cancelled:
            return          # stop cold: no more output, no dispatch, no reschedule

        self._drain_output()

        try:
            message = self._result_q.get_nowait()
        except queue.Empty:
            message = None

        if message is not None:
            try:
                if message[0] == "ok":
                    self._finish_ok(message[1])
                else:
                    self._finish_err(message[1], message[2])
            except Exception:                   # noqa: BLE001
                traceback.print_exc()
            return          # _teardown already cancelled the poll

        self._refresh_elapsed()
        if self._busy:
            self._poll_id = self.after(self.POLL_MS, self._poll)

    def _drain_output(self) -> None:
        """Move everything queued into the terminal in one Tk operation.

        Batching matters: the backend can emit hundreds of lines in a burst,
        and inserting them one at a time makes the UI crawl.
        """
        chunks: list[str] = []
        try:
            while True:
                chunks.append(self._output_q.get_nowait())
        except queue.Empty:
            pass
        if not chunks:
            return

        text = "".join(chunks)

        # Take the LAST phase marker in the batch, not the first — a burst
        # often spans a transition and the newest one is what's current.
        found = _PHASE_RE.findall(text)
        if found:
            # Normalise the sub-phase letter: the backend shouts "PHASE_4A"
            # but the phase is written phase_4a everywhere else.
            latest = found[-1].lower()
            if latest != self._phase:
                self._phase = latest
                self._refresh_elapsed()

        self._terminal.configure(state="normal")
        self._terminal.insert("end", text)
        self._terminal.see("end")
        self._terminal.configure(state="disabled")

    def _refresh_elapsed(self) -> None:
        """Keep the timer ticking even while the backend is silent."""
        if self._started_at is None:
            return
        try:
            seconds = int(time.monotonic() - self._started_at)
            shown = (f"{seconds // 60}m {seconds % 60}s" if seconds >= 60
                     else f"{seconds}s")
            parts = ([f"Phase {self._phase}"] if self._phase else []) + [f"{shown} elapsed"]
            self._elapsed.configure(text="  ·  ".join(parts))
        except Exception:                       # noqa: BLE001
            pass

    # ==================================================================
    # Finishing
    # ==================================================================

    def _finish_ok(self, result: Any) -> None:
        self._teardown()
        self._bar.stop()
        self._status.configure(text="Complete", text_color=theme.SUCCESS)
        self._drain_output()
        # Freeze the timer on the total, so "took 47s" survives on screen.
        self._refresh_elapsed()
        self._busy = False
        if self._on_complete is not None:
            try:
                self._on_complete(result)
            except Exception:                   # noqa: BLE001
                # A broken consumer shouldn't leave the loading screen wedged.
                traceback.print_exc()

    def _finish_err(self, exc: BaseException, traceback_text: str) -> None:
        self._teardown()
        self._bar.stop()
        self._status.configure(text=f"Failed: {type(exc).__name__}",
                               text_color=theme.ERROR)
        self._drain_output()
        self._refresh_elapsed()

        # Hint first, traceback second: the useful part should be the thing
        # you see without scrolling.
        hint = _friendly_hint(exc)
        self._terminal.configure(state="normal")
        if hint:
            self._terminal.insert("end", f"\n\n{hint}\n")
        self._terminal.insert("end", f"\n{traceback_text}")
        self._terminal.see("end")
        self._terminal.configure(state="disabled")

        self._busy = False
        if self._on_error is not None:
            try:
                self._on_error(exc, traceback_text)
            except Exception:                   # noqa: BLE001
                traceback.print_exc()

    def _teardown(self) -> None:
        """Put stdout back and stop polling. Safe to call more than once."""
        if self._saved_stdout is not None:
            sys.stdout = self._saved_stdout
            self._saved_stdout = None
        if self._saved_stderr is not None:
            sys.stderr = self._saved_stderr
            self._saved_stderr = None
        self._cancel_poll()

    def _set_terminal(self, text: str) -> None:
        self._terminal.configure(state="normal")
        self._terminal.delete("0.0", "end")
        if text:
            self._terminal.insert("0.0", text)
        self._terminal.configure(state="disabled")
