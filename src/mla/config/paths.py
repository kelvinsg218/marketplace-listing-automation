"""Where user data lives. Never inside the installation folder.

Default: %LOCALAPPDATA%\\MLA. Override with the MLA_DATA_DIR environment
variable (tests, portable installs).
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from mla import APP_NAME


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "mla.db"

    @property
    def images(self) -> Path:
        return self.root / "images"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def browser_profiles(self) -> Path:
        return self.root / "browser-profiles"

    @property
    def artifacts(self) -> Path:
        """Screenshots and HTML captured for diagnosing automation runs."""
        return self.root / "artifacts"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def files(self) -> Path:
        """Technical files attached to products (content-addressed)."""
        return self.root / "files"

    @property
    def imports(self) -> Path:
        """Staging area for archives being imported (one folder per batch)."""
        return self.root / "imports"

    def ensure(self) -> "AppPaths":
        for path in (self.root, self.images, self.logs, self.backups,
                     self.browser_profiles, self.artifacts, self.exports, self.files, self.imports):
            path.mkdir(parents=True, exist_ok=True)
        return self

    @classmethod
    def default(cls) -> "AppPaths":
        override = os.environ.get("MLA_DATA_DIR")
        if override:
            return cls(Path(override))
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return cls(Path(base) / APP_NAME)
        return cls(Path.home() / f".{APP_NAME.lower()}")


def resource_path(*parts: str) -> Path:
    """Path to a bundled resource, both from source and from a PyInstaller build."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    if getattr(sys, "_MEIPASS", None):
        base = base / "mla"
    return base.joinpath("resources", *parts)
