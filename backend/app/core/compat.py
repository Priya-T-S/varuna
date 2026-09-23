"""
Cross-platform pickle compatibility shim.

The VARUNA AI model artifacts (rainfall_model_v1.pkl,
varuna_fusion_model_v1.pkl) were serialised on Linux/macOS, which embeds
``pathlib.PosixPath`` objects in the pickle stream.  On Windows, Python
3.12+ defines ``pathlib.PosixPath`` as a stub class whose ``__new__``
raises ``UnsupportedOperation``, so ``joblib.load()`` crashes before it
can even read the model data.

The fix: replace ``pathlib.PosixPath`` with a subclass of
``PurePosixPath`` (which *is* instantiable everywhere) **before** any
joblib / pickle call runs.  The shim must be applied once, at process
startup, before the model packages are imported.

Call ``apply()`` from ``app.main`` inside the lifespan hook (or at
module level, as long as it runs before ``PredictionService.__init__``).
"""

from __future__ import annotations

import logging
import pathlib
import sys

logger = logging.getLogger(__name__)

_applied: bool = False


class _PortablePosixPath(pathlib.PurePosixPath):
    """
    Drop-in replacement for ``pathlib.PosixPath`` on Windows.

    Pickle/joblib stores the class by (module, qualname); when loading on
    Windows, Python calls ``pathlib.PosixPath(parts…)``.  Routing that
    call here gives us a ``PurePosixPath``, which carries the path string
    without attempting any OS-level file operations.

    The only place the path value is used after deserialisation is to
    produce human-readable metadata strings (e.g. ``str(path)``); the
    actual file look-ups in ``HybridPredictor._weather_probabilities`` and
    ``_satellite_probabilities`` use ``Path(artifact_dir) / filename``,
    which resolves against Windows conventions at runtime.
    """


def apply() -> None:
    """
    Apply all startup compatibility patches.

    1. Injects the repository root onto ``sys.path`` so that ``ai_models/``
       and ``explainability/`` are importable regardless of the working
       directory the server process was launched from.

    2. Patches ``pathlib.PosixPath`` on Windows so that Linux-serialised
       joblib/pickle model artifacts load without raising
       ``UnsupportedOperation``.

    Idempotent — safe to call multiple times.
    """
    global _applied
    if _applied:
        return

    # ------------------------------------------------------------------
    # 1. Add repo root to sys.path
    # ------------------------------------------------------------------
    # compat.py lives at  <repo>/backend/app/core/compat.py
    # Repo root is three levels up: core -> app -> backend -> repo
    repo_root = pathlib.Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
        logger.info("Added repo root to sys.path: %s", repo_root)

    # ------------------------------------------------------------------
    # 2. Patch pathlib.PosixPath on Windows
    # ------------------------------------------------------------------
    if sys.platform != "win32":
        # Nothing to patch on Linux/macOS; PosixPath works natively there.
        _applied = True
        return

    # On Windows, pathlib.PosixPath exists but its __new__ raises
    # UnsupportedOperation.  We replace it with our portable subclass so
    # that pickle.Unpickler.find_class("pathlib", "PosixPath") returns
    # something that can actually be instantiated.
    pathlib.PosixPath = _PortablePosixPath  # type: ignore[attr-defined]
    logger.info(
        "Applied cross-platform pathlib.PosixPath shim for Windows "
        "(Linux-serialised model artifacts will now load correctly)."
    )
    _applied = True

