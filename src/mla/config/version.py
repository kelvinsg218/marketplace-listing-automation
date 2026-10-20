"""Version strings like "0.1.0", "0.1.0-beta", "0.1.0-beta.2", "v0.2.0-rc.1" and their ordering."""
from __future__ import annotations

import re

_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([a-z]+)(?:\.?(\d+))?)?$", re.IGNORECASE)
_STAGES = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2}


class VersionError(ValueError):
    pass


def parse_version(text: str) -> tuple[int, int, int, int, int]:
    """Sortable key: a final release sorts after its alpha/beta/rc (0.1.0-beta < 0.1.0)."""
    match = _VERSION.match((text or "").strip())
    if not match:
        raise VersionError(f"Versão em formato desconhecido: {text!r}")
    major, minor, patch, stage, number = match.groups()
    if stage is None:
        return int(major), int(minor), int(patch), 9, 0
    if stage.lower() not in _STAGES:
        raise VersionError(f"Estágio de versão desconhecido: {stage!r}")
    return int(major), int(minor), int(patch), _STAGES[stage.lower()], int(number or 0)


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)
