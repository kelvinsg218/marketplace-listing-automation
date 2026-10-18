"""Technical files attached to products (manuals, datasheets, drawings).

Stored content-addressed under AppPaths.files, like images. Files are only
stored and opened by the user's own programs; MLA never executes them.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from mla.core.models import ProductFile

ALLOWED_FILE_EXTENSIONS = {
    ".pdf", ".txt", ".csv", ".xlsx", ".xls", ".ods", ".docx", ".doc", ".odt", ".rtf",
    ".dxf", ".dwg", ".step", ".stp", ".stl", ".jpg", ".jpeg", ".png", ".webp",
}
MAX_FILE_BYTES = 50 * 1024 * 1024


class FileStoreError(ValueError):
    pass


class FileStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, filename: str) -> Path:
        return self.root / filename

    def import_file(self, source: Path) -> ProductFile:
        source = Path(source)
        if not source.is_file():
            raise FileStoreError(f"Arquivo não encontrado: {source}")
        ext = source.suffix.lower()
        if ext not in ALLOWED_FILE_EXTENSIONS:
            raise FileStoreError(f"Tipo de arquivo não aceito: {source.name}")
        size = source.stat().st_size
        if size > MAX_FILE_BYTES:
            raise FileStoreError(f"Arquivo acima de 50 MB: {source.name}")
        digest = _sha256(source)
        filename = f"{digest[:20]}{ext}"
        target = self.root / filename
        if not target.exists():
            tmp = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, tmp)
            tmp.replace(target)
        return ProductFile(filename=filename, original_name=source.name, size_bytes=size, sha256=digest)

    def remove_orphans(self, in_use: set[str]) -> int:
        removed = 0
        for path in self.root.iterdir():
            if path.is_file() and path.name not in in_use and not path.name.endswith(".tmp"):
                path.unlink(missing_ok=True)
                removed += 1
        return removed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
