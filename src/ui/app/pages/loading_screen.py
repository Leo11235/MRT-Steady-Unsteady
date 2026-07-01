"""
LoadingScreen — shown while a simulation is running.

Architecture
------------
This page is generic.  Anything that wants a "do work + show progress"
flow calls:

    shell.start_loading_run(title, run_fn, on_complete, on_error=None)

`run_fn` is any callable that does the work and returns its result.
We:
  1. Navigate to this page (the shell handles that).
  2. Reset the terminal + rocket bar.
  3. Spawn a worker thread that runs `run_fn` and pipes its stdout
     into a thread-safe queue.
  4. Poll the queue from the Tk main thread and append every new chunk
     into the terminal widget.
  5. When the worker finishes, stop the animation and call `on_complete`
     with the worker's return value (so the caller can navigate next).

Thread-safety: the worker thread NEVER touches Tk widgets directly;
all updates are scheduled on the main thread via `self.after`.
"""

from __future__ import annotations

import ctypes
import queue
import sys
import threading
import traceback
from typing import Any, Callable, Optional

import customtkinter as ctk

from src.ui.app import theme
from src.ui.app.widgets.loading_bar import RocketLoadingBar


# ---------------------------------------------------------------------------
# Thread-kill helper.
#
# scipy's LSODA integrator is not reentrant and holds module-level state
# for the duration of a solve; if the worker thread is still running when
# the user clicks Run again we get `IntegratorConcurrencyError`.  A soft
# cancel isn't enough — we need the worker thread to ACTUALLY finish so
# scipy releases its handle before the next run starts.
#
# The cleanest way to do that from outside the thread in CPython is
# PyThreadState_SetAsyncExc, which raises an exception in the target
# thread at its next Python bytecode boundary.  We use SystemExit because
# it triggers Python's normal graceful thread-shutdown path (finally
# blocks run, refs get released, integrator __del__ removes the handle
# from scipy's active registry).
#
# This mechanism is unofficial but stable across all current CPython
# versions.  It's a no-op on other Python implementations.
# ---------------------------------------------------------------------------


def _kill_thread(thread: threading.Thread) -> bool:
    """Async-raise SystemExit in `thread`.  Returns True if the request
    was accepted (the thread WILL exit at its next Python bytecode)."""
    if thread is None or not thread.is_alive():
        return False
    tid = thread.ident
    if tid is None:
        return False
    try:
        api = ctypes.pythonapi.PyThreadState_SetAsyncExc
    except AttributeError:
        return False   # non-CPython
    res = api(ctypes.c_ulong(tid), ctypes.py_object(SystemExit))
    if res == 0:
        return False   # invalid thread id
    if res > 1:
        # Rolled back — shouldn't happen but be safe.
        api(ctypes.c_ulong(tid), None)
        return False
    return True


# ---------------------------------------------------------------------------
# Stream → Queue: tiny file-like that forwards writes into a Queue.
# ---------------------------------------------------------------------------

class _StreamToQueue:
    def __init__(self, q: "queue.Queue[str]") -> None:
        self.q = q

    def write(self, data: str) -> int:
        if data:
            self.q.put(data)
        return len(data)

    def flush(self) -> None:
        pass

    # tkinter occasionally checks for .isatty()
    def isatty(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

class LoadingScreen(ctk.CTkFrame):
    TITLE = "Running…"

    POLL_MS = 80   # how often we drain the stdout queue into the textbox

    def __init__(self, master, on_navigate) -> None:
        super().__init__(master, corner_radius=0, fg_color="transparent")
        self.on_navigate = on_navigate

        # state
        self._output_q: queue.Queue[str] = queue.Queue()
        # Result queue — the worker puts ('ok', result) or ('err', exc, tb)
        # here, and the main-thread polling loop picks it up.  This avoids
        # using self.after() from a worker thread, which is technically not
        # thread-safe in tkinter and (per Matplotlib's own thread check)
        # apparently doesn't reliably route callbacks back to the main thread
        # on every platform.
        self._result_q: queue.Queue = queue.Queue()
        self._poll_after_id: Optional[str] = None
        self._on_complete: Optional[Callable[[Any], None]] = None
        self._on_error:    Optional[Callable[[BaseException, str], None]] = None
        self._busy = False
        # Soft-cancel flag: when True, any result the worker eventually
        # produces is silently discarded (background thread finishes but
        # its output goes nowhere).
        self._cancelled = False
        # Reference to the current worker thread so cancel() can kill it.
        self._worker_thread: Optional[threading.Thread] = None
        self._saved_stdout = None
        self._saved_stderr = None

        self._build()

    # ===================================================================
    # Layout
    # ===================================================================

    def _build(self) -> None:
        # vertical stack: title (top) | terminal (fills) | rocket bar (bottom)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._title_label = ctk.CTkLabel(
            self,
            text="Running…",
            font=ctk.CTkFont(size=theme.SIZE_TITLE, weight="bold"),
            text_color=theme.MRT_RED_THEMED,
            anchor="center",
        )
        self._title_label.grid(row=0, column=0, sticky="ew",
                               padx=theme.PAD_L, pady=(theme.PAD_L, theme.PAD_S))

        # ---- terminal-style textbox ----------------------------------
        terminal_wrap = ctk.CTkFrame(self, fg_color="transparent")
        terminal_wrap.grid(row=1, column=0, sticky="nsew",
                           padx=theme.PAD_L, pady=theme.PAD_S)
        terminal_wrap.grid_columnconfigure(0, weight=1)
        terminal_wrap.grid_rowconfigure(0, weight=1)

        self._terminal = ctk.CTkTextbox(
            terminal_wrap,
            wrap="none",
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=("#101418", "#101418"),       # always-dark "terminal" look
            text_color=("#c5e1a5", "#c5e1a5"),     # soft phosphor green
            border_width=1,
            border_color=("gray30", "gray30"),
        )
        self._terminal.grid(row=0, column=0, sticky="nsew")
        self._terminal.configure(state="disabled")

        # ---- rocket loading bar --------------------------------------
        bar_wrap = ctk.CTkFrame(self, fg_color="transparent")
        bar_wrap.grid(row=2, column=0, sticky="ew",
                      padx=theme.PAD_L, pady=(theme.PAD_S, theme.PAD_L))
        bar_wrap.grid_columnconfigure(0, weight=1)

        # sticky="ew" + the bar's own <Configure> resize handler = full-width
        self._bar = RocketLoadingBar(bar_wrap, height=80, px=4)
        self._bar.grid(row=0, column=0, sticky="ew", pady=(0, theme.PAD_S))

        self._status_label = ctk.CTkLabel(
            bar_wrap,
            text="",
            text_color=("gray45", "gray60"),
            font=ctk.CTkFont(size=theme.SIZE_SMALL, slant="italic"),
        )
        self._status_label.grid(row=1, column=0, sticky="w", padx=4)

    # ===================================================================
    # Public API — called by AppShell.start_loading_run
    # ===================================================================

    def start_run(
        self,
        title: str,
        run_fn: Callable[[], Any],
        on_complete: Callable[[Any], None],
        on_error: Optional[Callable[[BaseException, str], None]] = None,
    ) -> None:
        """
        Begin a new run.  Resets the page, captures stdout, spawns a worker.

        Safe to call again later — it tears down any previous run state first.
        """
        if self._busy:
            # Refuse to start a second run while one is in progress.
            return
        self._busy = True

        self._on_complete = on_complete
        self._on_error    = on_error or self._default_on_error

        # reset the page
        self._title_label.configure(text=title)
        self._terminal.configure(state="normal")
        self._terminal.delete("0.0", "end")
        self._terminal.configure(state="disabled")
        self._status_label.configure(text="Starting …",
                                     text_color=("gray45", "gray60"))
        self._output_q = queue.Queue()
        self._result_q = queue.Queue()
        self._cancelled = False
        self._bar.start()
        self._start_polling()

        # divert stdout/stderr into the queue (process-global, but only the
        # worker thread is producing anything noisy right now).
        self._saved_stdout, self._saved_stderr = sys.stdout, sys.stderr
        sys.stdout = _StreamToQueue(self._output_q)
        sys.stderr = _StreamToQueue(self._output_q)

        # Keep a reference so cancel() can target this thread specifically.
        self._worker_thread = threading.Thread(
            target=self._worker,
            args=(run_fn,),
            daemon=True,
        )
        self._worker_thread.start()

    def get_terminal_text(self) -> str:
        """Return everything currently in the terminal widget."""
        return self._terminal.get("0.0", "end").rstrip()

    def cancel(self) -> None:
        """
        Cancel a running simulation.

        We do this in two moves:
          1. Async-raise SystemExit in the worker thread so scipy's LSODA
             integrator releases its non-reentrant lock and any other
             module-level state gets torn down cleanly (see the block
             comment above `_kill_thread`).
          2. Briefly join the thread with a timeout so the next Run can
             start with a clean scipy.

        We also flip flags so any result that DID sneak past step 1 is
        silently dropped by the poll loop.
        """
        if not self._busy:
            return
        self._cancelled = True
        self._busy = False
        self._teardown_capture()
        self._bar.stop()
        # Stop polling — we won't dispatch _finish_ok anymore.
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None
        # Null the callbacks so a race-condition result dispatch has
        # nowhere to go.
        self._on_complete = None
        self._on_error    = None

        # Actually kill the worker so scipy's LSODA integrator finishes
        # its current step, unwinds, and releases the handle.  If it's
        # not dead within 3 s we proceed anyway — the concurrency-error
        # is still possible in that pathological case, but rare.
        wt = self._worker_thread
        if wt is not None and wt.is_alive():
            _kill_thread(wt)
            try:
                wt.join(timeout=3.0)
            except Exception:
                pass
        self._worker_thread = None

    # ===================================================================
    # Internals
    # ===================================================================

    def _worker(self, run_fn: Callable[[], Any]) -> None:
        """
        Runs on a background thread.  We DON'T call self.after() from here —
        instead we drop the outcome into a thread-safe queue, and the
        main-thread polling loop (_poll) picks it up.  This guarantees
        _finish_ok / _finish_err run on the main thread, which matters for
        matplotlib (and for tk widget updates generally).
        """
        try:
            result = run_fn()
            self._result_q.put(("ok", result))
        except SystemExit:
            # Injected by cancel().  Let the thread exit silently — the
            # main thread already knows we're cancelling.
            return
        except BaseException as exc:
            tb = traceback.format_exc()
            self._result_q.put(("err", exc, tb))

    def _finish_ok(self, result: Any) -> None:
        self._teardown_capture()
        self._bar.stop()
        self._status_label.configure(
            text="Simulation complete.",
            text_color=("#2a9d8f", "#5eead4"),
        )
        self._drain_queue()
        self._busy = False
        if self._on_complete is not None:
            try:
                self._on_complete(result)
            except Exception:
                # don't let consumer errors break the loading screen
                traceback.print_exc()

    def _finish_err(self, exc: BaseException, tb: str) -> None:
        self._teardown_capture()
        self._bar.stop()
        self._status_label.configure(
            text=f"Failed: {type(exc).__name__}",
            text_color=("#b00020", "#ff6b6b"),
        )
        # show the traceback in the terminal too
        self._terminal.configure(state="normal")
        self._terminal.insert("end", "\n\n" + tb)
        self._terminal.see("end")
        self._terminal.configure(state="disabled")
        self._drain_queue()
        self._busy = False
        if self._on_error is not None:
            try:
                self._on_error(exc, tb)
            except Exception:
                traceback.print_exc()

    def _default_on_error(self, exc: BaseException, tb: str) -> None:
        # If the caller didn't supply one, do nothing — the traceback is
        # already on screen.  The user can hit the Home button to leave.
        pass

    def _teardown_capture(self) -> None:
        if self._saved_stdout is not None:
            sys.stdout = self._saved_stdout
            self._saved_stdout = None
        if self._saved_stderr is not None:
            sys.stderr = self._saved_stderr
            self._saved_stderr = None
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
            self._poll_after_id = None

    def _start_polling(self) -> None:
        if self._poll_after_id is not None:
            try:
                self.after_cancel(self._poll_after_id)
            except Exception:
                pass
        self._poll_after_id = self.after(self.POLL_MS, self._poll)

    def _poll(self) -> None:
        # If the user cancelled, we stop cold: no more terminal updates,
        # no result dispatch, no reschedule.
        if self._cancelled:
            return

        # Drain stdout/stderr chunks into the terminal
        self._drain_queue()

        # Drain the result queue — if the worker has finished, dispatch to
        # _finish_ok / _finish_err HERE on the main thread (not from inside
        # the worker via self.after(), which is what was breaking matplotlib).
        try:
            msg = self._result_q.get_nowait()
        except queue.Empty:
            msg = None
        if msg is not None:
            try:
                kind = msg[0]
                if kind == "ok":
                    self._finish_ok(msg[1])
                elif kind == "err":
                    self._finish_err(msg[1], msg[2])
            except Exception:
                traceback.print_exc()
            return   # don't reschedule; _teardown_capture already cancelled

        # Keep polling as long as the run is in progress.  Once finished,
        # _teardown_capture cancels this id and we stop scheduling.
        if self._busy:
            self._poll_after_id = self.after(self.POLL_MS, self._poll)

    def _drain_queue(self) -> None:
        """Append every queued chunk into the terminal in one Tk operation."""
        chunks: list[str] = []
        try:
            while True:
                chunks.append(self._output_q.get_nowait())
        except queue.Empty:
            pass
        if not chunks:
            return
        text = "".join(chunks)
        self._terminal.configure(state="normal")
        self._terminal.insert("end", text)
        self._terminal.see("end")
        self._terminal.configure(state="disabled")
