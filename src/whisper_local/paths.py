"""Filesystem path helpers for the Whisper Local application.

Centralizing these paths keeps source/runtime boundaries explicit. In the
two-layer workspace layout, source lives in `codebase/` while local runtime data
such as caches, summaries, `.env`, and venvs can remain one level above it.
"""

from __future__ import annotations

import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
SRC_ROOT = PACKAGE_ROOT.parent
PROJECT_ROOT = SRC_ROOT.parent


def _default_runtime_root() -> Path:
    """Return the local runtime root for generated/private data."""

    configured = os.environ.get("WHISPER_LOCAL_RUNTIME_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    if PROJECT_ROOT.name == "codebase":
        return PROJECT_ROOT.parent

    return PROJECT_ROOT


RUNTIME_ROOT = _default_runtime_root()
DATA_DIR = RUNTIME_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
SUMMARIES_DIR = RUNTIME_ROOT / "summaries"
PARENT_ENV_ALLOWLIST = {
    "FLASK_SECRET_KEY",
    "HF_TOKEN",
    "WHISPER_LOCAL_AUTH_TOKEN",
    "WHISPER_LOCAL_HOST",
    "WHISPER_LOCAL_MAX_AUDIO_DURATION_SECONDS",
    "WHISPER_LOCAL_MAX_UPLOAD_MB",
    "WHISPER_LOCAL_RUNTIME_ROOT",
    "WHISPER_MODEL_NAME",
    "WHISPER_MODEL_PATH",
}


def load_env_file(env_file: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs from an ignored local .env file if present.

    Values already present in the process environment win. Secret values are not
    printed or returned.
    """

    candidate_paths = [env_file] if env_file else [PROJECT_ROOT / ".env"]

    # Preserve the approved two-layer local workspace layout: existing private
    # `.env` files stay outside `codebase/`, but local runs can still read them
    # without moving secrets into the repository.
    if env_file is None and PROJECT_ROOT.name == "codebase":
        candidate_paths.append(PROJECT_ROOT.parent / ".env")

    path = next((candidate for candidate in candidate_paths if candidate and candidate.exists()), None)
    if path is None:
        return

    parent_fallback = env_file is None and path == PROJECT_ROOT.parent / ".env"

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        clean_key = key.strip()
        if parent_fallback and clean_key not in PARENT_ENV_ALLOWLIST:
            continue

        os.environ.setdefault(clean_key, value.strip().strip('"').strip("'"))
