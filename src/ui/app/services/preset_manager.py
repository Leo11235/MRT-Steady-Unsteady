"""PresetManager — the "reuse loaded preset if unchanged, else auto-save
a friendly-named preset, else let the backend write a temp file" pattern.

Both SteadyPage and UnsteadyPage had this same logic inline; this module
holds it once.  Pages instantiate one PresetManager per page instance.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional


class PresetManager:
    """Tracks the "current preset" for a simulation page.

    Usage:
        pm = PresetManager(presets_dir_fn=backend_bridge.steady_presets_dir,
                           save_fn=backend_bridge.save_jsonc)
        # On Load / Save preset actions:
        pm.mark_loaded(path, cfg)
        # On Run:
        path = pm.pick_path_for_run(cfg, default_name, auto_save=True)
    """

    def __init__(
        self,
        *,
        presets_dir_fn: Callable[[], Path],
        save_fn: Callable[[Path, dict], None],
    ) -> None:
        self._presets_dir_fn = presets_dir_fn
        self._save_fn        = save_fn
        self._path: Optional[Path]     = None
        self._snapshot: Optional[dict] = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def mark_loaded(self, path: Path, cfg: dict) -> None:
        """Remember this path + config as the "current preset".  Call from
        Load preset… (with the loaded cfg) or Save preset… (with the
        cfg that was saved)."""
        self._path = Path(path)
        self._snapshot = cfg

    def clear(self) -> None:
        self._path = None
        self._snapshot = None

    @property
    def path(self) -> Optional[Path]:
        return self._path

    # ------------------------------------------------------------------
    # Decide what file the simulator should be given for a Run
    # ------------------------------------------------------------------

    def pick_path_for_run(
        self, cfg: dict, default_name: str, *, auto_save: bool
    ) -> tuple[Optional[Path], str]:
        """Decide what file the backend should read.

        Returns (path, source):
          - ("reuse")     : path == last loaded/saved preset, unchanged.
          - ("auto_save") : we just wrote a fresh preset to disk.
          - ("temp")      : path is None; the backend should write its own
                             _ui_run_<timestamp>.jsonc temp file.

        The caller uses `source` to decide what status-line message to
        show ("Auto-saved as X.jsonc" vs. nothing).
        """
        if (self._path is not None
                and self._snapshot == cfg
                and self._path.exists()):
            return self._path, "reuse"

        if not auto_save:
            return None, "temp"

        try:
            presets_dir = self._presets_dir_fn()
            presets_dir.mkdir(parents=True, exist_ok=True)
            path = presets_dir / default_name
            self._save_fn(path, cfg)
            self.mark_loaded(path, cfg)
            return path, "auto_save"
        except Exception:
            return None, "temp"
