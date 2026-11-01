"""File storage owned by organizations. Keys always start with ``orgs/<org_id>/``; reads check the owner.

LocalStorage keeps files outside any public web directory; downloads go through authorized API routes.
An object-storage backend (S3-compatible) implements the same interface later.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Protocol

_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CATEGORIES = frozenset({"imports", "templates", "exports", "media", "files"})


class StorageError(Exception):
    pass


class Storage(Protocol):
    def put(self, org_id: uuid.UUID, category: str, name: str, data: bytes) -> str: ...
    def read(self, org_id: uuid.UUID, key: str) -> bytes: ...
    def delete(self, org_id: uuid.UUID, key: str) -> None: ...


def _check_segment(value: str) -> str:
    if not _SEGMENT.match(value) or ".." in value:
        raise StorageError(f"Nome de arquivo inválido: {value!r}")
    return value


def make_key(org_id: uuid.UUID, category: str, name: str) -> str:
    if category not in CATEGORIES:
        raise StorageError(f"Categoria de armazenamento inválida: {category!r}")
    return f"orgs/{uuid.UUID(str(org_id))}/{category}/{_check_segment(name)}"


class LocalStorage:
    def __init__(self, root: Path):
        self.root = root.resolve()

    def _path(self, org_id: uuid.UUID, key: str) -> Path:
        prefix = f"orgs/{uuid.UUID(str(org_id))}/"
        if not key.startswith(prefix):
            raise PermissionError("Arquivo pertence a outra organização.")
        parts = key.split("/")
        if len(parts) != 4 or parts[2] not in CATEGORIES:
            raise StorageError("Chave de armazenamento inválida.")
        _check_segment(parts[3])
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise StorageError("Chave fora do armazenamento.")
        return path

    def put(self, org_id: uuid.UUID, category: str, name: str, data: bytes) -> str:
        key = make_key(org_id, category, name)
        path = self._path(org_id, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        try:
            tmp.write_bytes(data)
            tmp.replace(path)
        except OSError as exc:
            tmp.unlink(missing_ok=True)
            raise StorageError(f"Falha ao gravar o arquivo: {exc}") from exc
        return key

    def read(self, org_id: uuid.UUID, key: str) -> bytes:
        path = self._path(org_id, key)
        if not path.is_file():
            raise FileNotFoundError(key)
        return path.read_bytes()

    def delete(self, org_id: uuid.UUID, key: str) -> None:
        self._path(org_id, key).unlink(missing_ok=True)
