"""Client companies (workspaces): one isolated data folder per company.

The first company is the existing data folder itself, so installations made before
this feature keep their data untouched. Other companies live in
``<base>/empresas/<slug>/`` with their own database, images, files, browser
profiles (marketplace sessions), backups and logs. Nothing is shared between them.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from mla.config.paths import AppPaths

REGISTRY_FILE = "workspaces.json"
COMPANIES_DIR = "empresas"
DEFAULT_SLUG = "principal"
MAX_NAME = 60


class WorkspaceError(ValueError):
    pass


@dataclass(frozen=True)
class Workspace:
    slug: str
    name: str
    root: Path
    created_at: str = ""

    @property
    def is_default(self) -> bool:
        return self.slug == DEFAULT_SLUG

    @property
    def paths(self) -> AppPaths:
        return AppPaths(self.root)


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:40].strip("-") or "empresa"


class WorkspaceRegistry:
    """List of companies stored in ``<base>/workspaces.json`` (written atomically)."""

    def __init__(self, base: Path):
        self.base = base
        self.file = base / REGISTRY_FILE

    # ------------------------------------------------------------------ storage
    def _load(self) -> dict:
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            data = {}
        except (OSError, ValueError) as exc:
            raise WorkspaceError(f"Não foi possível ler a lista de empresas ({self.file}): {exc}") from exc
        entries = [e for e in data.get("workspaces", []) if isinstance(e, dict) and e.get("slug")]
        if not any(e["slug"] == DEFAULT_SLUG for e in entries):
            entries.insert(0, {"slug": DEFAULT_SLUG, "name": "Empresa principal", "created_at": ""})
        return {"version": 1, "last": data.get("last") or DEFAULT_SLUG, "workspaces": entries}

    def _save(self, data: dict) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.file)

    def _workspace(self, entry: dict) -> Workspace:
        slug = entry["slug"]
        root = self.base if slug == DEFAULT_SLUG else self.base / COMPANIES_DIR / slug
        return Workspace(slug, entry.get("name") or slug, root, entry.get("created_at", ""))

    # ------------------------------------------------------------------ queries
    def list(self) -> list[Workspace]:
        return [self._workspace(e) for e in self._load()["workspaces"]]

    def get(self, slug: str) -> Workspace | None:
        return next((w for w in self.list() if w.slug == slug), None)

    def last(self) -> Workspace:
        data = self._load()
        return self.get(data["last"]) or self.get(DEFAULT_SLUG)  # type: ignore[return-value]

    # ------------------------------------------------------------------ changes
    def create(self, name: str) -> Workspace:
        name = self._valid_name(name)
        data = self._load()
        if any(e.get("name", "").casefold() == name.casefold() for e in data["workspaces"]):
            raise WorkspaceError(f"Já existe uma empresa chamada {name!r}.")
        taken = {e["slug"] for e in data["workspaces"]}
        base_slug = slugify(name)
        slug, n = base_slug, 2
        while slug in taken or slug == DEFAULT_SLUG or (self.base / COMPANIES_DIR / slug).exists():
            slug, n = f"{base_slug}-{n}", n + 1
        entry = {"slug": slug, "name": name, "created_at": datetime.now().isoformat(timespec="seconds")}
        data["workspaces"].append(entry)
        workspace = self._workspace(entry)
        workspace.paths.ensure()
        self._save(data)
        return workspace

    def rename(self, slug: str, name: str) -> Workspace:
        name = self._valid_name(name)
        data = self._load()
        entry = next((e for e in data["workspaces"] if e["slug"] == slug), None)
        if entry is None:
            raise WorkspaceError("Empresa não encontrada.")
        if any(e["slug"] != slug and e.get("name", "").casefold() == name.casefold() for e in data["workspaces"]):
            raise WorkspaceError(f"Já existe uma empresa chamada {name!r}.")
        entry["name"] = name
        self._save(data)
        return self._workspace(entry)

    def set_last(self, slug: str) -> None:
        data = self._load()
        if not any(e["slug"] == slug for e in data["workspaces"]):
            raise WorkspaceError("Empresa não encontrada.")
        data["last"] = slug
        self._save(data)

    @staticmethod
    def _valid_name(name: str) -> str:
        name = " ".join((name or "").split())
        if not name:
            raise WorkspaceError("Informe o nome da empresa.")
        if len(name) > MAX_NAME:
            raise WorkspaceError(f"Use no máximo {MAX_NAME} caracteres no nome da empresa.")
        return name
