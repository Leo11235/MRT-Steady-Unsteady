"""Turn Tk's C-level panic into a log line instead of a modal dialog.

WHAT THIS IS FOR
----------------
Tk allocates a Windows bitmap every time it has to draw an off-screen buffer:
a canvas redraw, a photo image, a resized image.  When that allocation fails,
tkWinPixmap.c does not return an error for Python to raise.  It calls
Tcl_Panic, and Tcl's default panic handler on Windows shows

    Tk_GetPixmap: Error from CreateDIBSection
    The parameter is incorrect.

in a message box and then aborts the process.  No Python frame ever runs, so
no try/except anywhere in this program can see it, and the modal box tells the
user nothing they can act on.

WHAT IT DOES
------------
Tcl lets a program replace that handler.  We install one that writes the
message, the time and a Python traceback to user_data/crash_log.txt, prints one
line to stderr, and exits immediately and quietly.

WHAT IT CANNOT DO
-----------------
It cannot keep the program running.  A panic means a Tk call returned something
Tk is not prepared to carry on with (here, a bitmap handle that is NULL), and
the panic handler is not allowed to return: Tk would use the NULL handle and
take an access violation a few instructions later.  Exiting on purpose, with a
log, is the best available outcome.  The real defence is not provoking the
allocation failure, which is a matter of not building and destroying thousands
of canvases and images; see the search code in results_page.py.
"""

from __future__ import annotations

import ctypes
import datetime as _datetime
import os
import sys
import traceback

# The installed callback must outlive this function call. If Python collects
# it, Tcl is left holding a pointer into freed memory, which converts a rare
# crash into a frequent one.
_PANIC_PROC = None
_INSTALLED = False
_LOG_PATH = None

# Tcl_PanicProc is (const char *format, ...). Varargs cannot be declared in
# ctypes, but on every platform Python runs on the first few arguments are
# passed the same way whether or not the callee knows there are more, so
# declaring a fixed handful reads the ones Tk actually passes and ignores the
# rest.
_PANIC_SIGNATURE = ctypes.CFUNCTYPE(
    None, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_char_p, ctypes.c_char_p)

_TCL_NAMES = ("tcl86t.dll", "tcl86.dll", "tcl90.dll",
              "libtcl8.6.so", "libtcl.so")


def _decode(value) -> str:
    if not value:
        return ""
    try:
        return value.decode("utf-8", "replace")
    except Exception:                           # noqa: BLE001
        return str(value)


def _tcl_candidates():
    """Every name worth trying, bare names first.

    A bare name matters: the library is already in the process, and asking for
    it by name hands back that same instance instead of loading a second copy
    whose panic handler nothing would ever call. The full paths are only a
    fallback for a frozen build that keeps its DLLs somewhere unusual.
    """
    for name in _TCL_NAMES:
        yield name
    roots = {getattr(sys, "base_prefix", ""), getattr(sys, "prefix", ""),
             getattr(sys, "_MEIPASS", "")}
    for root in roots:
        if not root:
            continue
        for name in _TCL_NAMES:
            for folder in ("DLLs", "", "lib"):
                candidate = os.path.join(root, folder, name) if folder else \
                    os.path.join(root, name)
                if os.path.exists(candidate):
                    yield candidate


def _load_tcl():
    """The already-loaded Tcl library, by whatever name it goes by here."""
    for name in _tcl_candidates():
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


def install(log_path=None) -> bool:
    """Replace Tcl's panic handler. Returns whether it took.

    Safe to call more than once, and safe to call on a build where none of
    this resolves: every failure leaves Tcl's own handler in place, which is
    exactly what we have today.
    """
    global _PANIC_PROC, _INSTALLED, _LOG_PATH

    if _INSTALLED:
        return True
    if log_path is not None:
        _LOG_PATH = log_path

    library = _load_tcl()
    if library is None:
        return False
    try:
        setter = library.Tcl_SetPanicProc
    except AttributeError:
        return False

    _PANIC_PROC = _PANIC_SIGNATURE(on_panic)
    try:
        setter.restype = None
        setter.argtypes = [_PANIC_SIGNATURE]
        setter(_PANIC_PROC)
    except Exception:                           # noqa: BLE001
        _PANIC_PROC = None
        return False

    _INSTALLED = True
    return True


def on_panic(fmt, arg1=None, arg2=None, arg3=None, arg4=None):
    """What Tcl calls instead of showing a message box. Never returns.

    Returning is not an option. Tk panics when a call gave it something it has
    no way to carry on with, here a null bitmap handle, and it would use that
    handle within a few instructions of us handing control back.
    """
    message = _decode(fmt)
    extra = [text for text in (_decode(arg1), _decode(arg2),
                               _decode(arg3), _decode(arg4)) if text]
    if extra:
        message = f"{message}  |  {'  '.join(extra)}"
    _write_log(_LOG_PATH, message)
    try:
        sys.stderr.write(f"\nTcl panic: {message}\n"
                         "The interface could not allocate a drawing buffer "
                         "and has to close.\n")
        sys.stderr.flush()
    except Exception:                           # noqa: BLE001
        pass
    # _exit, not sys.exit: a panic leaves the interpreter holding a Tk state
    # nobody should run destructors against, and an orderly shutdown would
    # walk straight back into it.
    os._exit(3)                                 # noqa: SLF001


def _write_log(log_path, message: str) -> None:
    """Append what happened, with the Python stack that was on the way in.

    The stack is usually the widget call that triggered the draw, which is the
    one thing worth having and the one thing the message box never showed.
    """
    try:
        if log_path is None:
            from src.ui.app import backend_bridge
            log_path = backend_bridge.project_root() / "user_data" / "crash_log.txt"
        stamp = _datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(f"\n===== {stamp}  Tcl panic =====\n")
            handle.write(message + "\n")
            handle.write("".join(traceback.format_stack()))
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:                           # noqa: BLE001
        pass
