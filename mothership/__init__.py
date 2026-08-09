"""Stable public package for the Mothership control plane."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path


_DISTRIBUTION = "mothership-control-plane"


def _package_version() -> str:
    try:
        return metadata.version(_DISTRIBUTION)
    except metadata.PackageNotFoundError:
        version_file = Path(__file__).resolve().parents[1] / "VERSION"
        return version_file.read_text(encoding="utf-8").strip()


__version__ = _package_version()

__all__ = ["__version__"]
