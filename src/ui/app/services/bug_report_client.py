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


WEB3FORMS_ACCESS_KEY = "455cf761-6cfd-40a1-8efd-225140582053"
WEB3FORMS_ENDPOINT   = "https://api.web3forms.com/submit"


def is_configured() -> bool:
    """Format-check the access key.  We validate the SHAPE rather than
    compare against a sentinel because a global find-and-replace on the
    placeholder would also rewrite the check."""
    k = WEB3FORMS_ACCESS_KEY
    if not k or "PASTE" in k.upper():
        return False
    if len(k) < 30 or k.count("-") != 4:
        return False
    return True


def submit_bug_report(title: str, description: str,
                      timeout_s: float = 15.0) -> None:
    """POST the report to Web3Forms.  Raises RuntimeError on any
    non-success response; raises the underlying urllib exception on
    network failures (so the caller can pick a hint based on the
    reason string)."""
    if not is_configured():
        raise RuntimeError(
            "Bug-report Web3Forms access key is not configured.  Open "
            "src/ui/app/services/bug_report_client.py and paste your "
            "access key into WEB3FORMS_ACCESS_KEY at the top of the file."
        )

    # Look up the current app version so it lands in its own email
    # field (Web3Forms lets us include arbitrary extra keys).  Failing
    # gracefully to "unknown" so a missing version.py never blocks a
    # report going out.
    try:
        from src.ui.app.version import VERSION as _APP_VERSION
    except Exception:
        _APP_VERSION = "unknown"

    payload = {
        "access_key":  WEB3FORMS_ACCESS_KEY,
        "subject":     title or "Bug report (no title)",
        "from_name":   "MRT-Sim bug reporter",
        "message":     description,
        "app_version": _APP_VERSION,
        "botcheck":    "",
        "_source":     "mrt-sim-ui",
    }
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


def friendly_network_error_hint(reason_text: str) -> str:
    """Given a stringified URLError reason, return a human-readable hint."""
    rl = reason_text.lower()
    if "certificate" in rl or "ssl" in rl:
        return ("SSL certificate verification failed.  On Windows the "
                "usual fix is:  pip install --upgrade certifi  "
                "(or, on macOS, run 'Install Certificates.command' from your "
                "Applications/Python folder).")
    if "getaddrinfo" in rl or "name or service not known" in rl:
        return ("DNS lookup failed — confirm you can reach "
                "api.web3forms.com in a browser.")
    if "timed out" in rl or "timeout" in rl:
        return ("Connection timed out — a firewall or proxy may be "
                "blocking api.web3forms.com.")
    if "refused" in rl:
        return "Connection refused by api.web3forms.com."
    return "Network error."
