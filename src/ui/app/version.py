"""The app version.

The reader moved to src/common/version.py, because the backends stamp the
version into every results file and importing a UI module to do that would be
the wrong way round. This re-export exists so the UI keeps saying
`from src.ui.app.version import VERSION`.
"""

from __future__ import annotations

from src.common.version import VERSION

__all__ = ["VERSION"]
