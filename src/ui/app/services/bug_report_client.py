"""Thin transport layer for the bug-report page.

Doesn't depend on any UI code.  If you want to swap Web3Forms for another
provider, this is the only file that changes.

ONE-TIME SETUP — the access key below is what routes every submission
into the maintainer's inbox.  To rotate it:
  1. Sign up at https://web3forms.com
  2. Confirm the destination email via the link they send.
  3. Paste the resulting UUID into WEB3FORMS_ACCESS_KEY.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path


WEB3FORMS_ACCESS_KEY = "455cf761-6cfd-40a1-8efd-225140582053"
WEB3FORMS_ENDPOINT   = "https://api.web3forms.com/submit"


def is_configured() -> bool:
    """Format-check the access key.  Validates the SHAPE rather than
    comparing to a sentinel because a global find-and-replace on the
    placeholder would also rewrite the check."""
    k = WEB3FORMS_ACCESS_KEY
    if not k or "PASTE" in k.upper():
        return False
    if len(k) < 30 or k.count("-") != 4:
        return False
    return True


def submit_bug_report(
    title: str,
    description: str,
    *,
    name: str = "",
    email: str = "",
    diagnostics: str = "",
    config_json: str = "",
    env: dict | None = None,
    timeout_s: float = 15.0,
) -> str:
    """POST the report to Web3Forms.

    Extra kwargs let the UI supply the split-out fields collected on the
    new bug page (name, email, diagnostics blob, config JSON, and an
    environment metadata dict).  Everything is optional so this stays
    callable with the old two-arg signature if anything else in the
    codebase still uses it.

    Returns the server's own message, so the UI can show what actually came
    back rather than asserting success on the user's behalf.

    Raises RuntimeError on any non-success response; raises the
    underlying urllib exception on network failures.
    """
    if not is_configured():
        raise RuntimeError(
            "Bug-report Web3Forms access key is not configured.  Open "
            "src/ui/app/services/bug_report_client.py and paste your "
            "access key into WEB3FORMS_ACCESS_KEY at the top of the file."
        )

    env = env or {}

    payload: dict = {
        "access_key":  WEB3FORMS_ACCESS_KEY,
        "subject":     (title.strip() if title else "") or "Bug report (no title)",
        "from_name":   name.strip() or "MRT-Sim bug reporter",
        "message":     description.strip() or "(no description provided; see diagnostics field)",
        "botcheck":    "",
        "_source":     "mrt-sim-ui",
    }

    # `email` is a Web3Forms-reserved field that sets the Reply-To header.
    # Only include it if the user actually typed one.
    if email.strip():
        payload["email"] = email.strip()

    # Environment metadata — every report gets these so triage is fast.
    payload["app_version"]    = env.get("app_version", "unknown")
    payload["build"]          = env.get("build",       "unknown")
    payload["os"]             = env.get("os",          "unknown")
    payload["python_version"] = env.get("python",      "unknown")

    # Split-out fields.  Only sent if populated; keeps empty rows out of
    # the email for manually-filed reports.
    if diagnostics.strip():
        payload["diagnostics"] = diagnostics
    if config_json.strip():
        payload["config_json"] = config_json

    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(
        WEB3FORMS_ENDPOINT, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept":       "application/json",
            "User-Agent":   "Mozilla/5.0 (MRT-Sim bug-reporter)",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"success": False, "message": raw[:200]}
        if response.status != 200 or not body.get("success"):
            msg = body.get("message") or f"HTTP {response.status}"
            raise RuntimeError(f"Web3Forms rejected the report: {msg}")
        # Accepted. Note that Web3Forms accepting a submission is NOT proof of
        # delivery: it forwards to the address behind the access key, and its
        # own spam filtering sits between the two. Hand the message back so the
        # UI can show it verbatim instead of claiming more than we know.
        return str(body.get("message") or "accepted")


def friendly_network_error_hint(reason_text: str) -> str:
    """Given a stringified URLError reason, return a human-readable hint."""
    rl = reason_text.lower()
    if "certificate" in rl or "ssl" in rl:
        return ("SSL certificate verification failed.  On Windows the "
                "usual fix is:  pip install --upgrade certifi  "
                "(or, on macOS, run 'Install Certificates.command' from "
                "your Applications/Python folder).")
    if "getaddrinfo" in rl or "name or service not known" in rl:
        return ("DNS lookup failed. Confirm you can reach "
                "api.web3forms.com in a browser.")
    if "timed out" in rl or "timeout" in rl:
        return ("Connection timed out. A firewall or proxy may be "
                "blocking api.web3forms.com.")
    if "refused" in rl:
        return "Connection refused by api.web3forms.com."
    return "Network error."


# Web3Forms rejects oversized fields outright, and a halted unsteady run can
# produce megabytes of terminal output. Trim from the FRONT: the tail of a log
# is where the failure is, so the last lines are the ones worth keeping.
MAX_FIELD_LINES = 1000
MAX_FIELD_BYTES = 20_000


def cap_field(text: str, *, max_lines: int = MAX_FIELD_LINES,
              max_bytes: int = MAX_FIELD_BYTES) -> str:
    """Trim a field to Web3Forms' limits, keeping the end and saying so."""
    if not text:
        return ""

    lines = text.splitlines()
    dropped = 0
    if len(lines) > max_lines:
        dropped = len(lines) - max_lines
        lines = lines[-max_lines:]
    capped = "\n".join(lines)

    while len(capped.encode("utf-8")) > max_bytes and lines:
        # Drop from the front in chunks; one line at a time is slow on a
        # multi-megabyte log.
        chunk = max(1, len(lines) // 20)
        dropped += chunk
        lines = lines[chunk:]
        capped = "\n".join(lines)

    if dropped:
        capped = f"[... {dropped} earlier lines truncated ...]\n{capped}"
    return capped


def save_local_copy(root: Path, text: str) -> Path | None:
    """Write a report to user_data/bug_reports/ and return the path.

    Every report gets saved before it's sent. Web3Forms returning success is
    not proof of delivery — its spam filter sits between the accept and the
    inbox — so a local copy is the difference between "we'll never know what
    that bug was" and "attach this file to an email".
    """
    from datetime import datetime

    try:
        folder = root / "user_data" / "bug_reports"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}.txt"
        path.write_text(text, encoding="utf-8")
        return path
    except OSError:
        return None


def collect_environment() -> dict:
    """Auto-collected metadata that every bug report should carry.
    Runs entirely locally; no imports beyond the stdlib and version.py."""
    import sys, platform
    try:
        from src.ui.app.version import VERSION as _v
    except Exception:
        _v = "unknown"
    return {
        "app_version": _v,
        "build":       "installed exe" if getattr(sys, "frozen", False) else "source",
        "os":          platform.platform(),
        "python":      platform.python_version(),
    }
