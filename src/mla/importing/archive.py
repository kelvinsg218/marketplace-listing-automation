"""Safe extraction of ZIP archives into the import staging area.

Only data files are extracted (catalog tables, images, technical documents).
Executables, scripts, macro-enabled documents, nested archives, links and paths
leaving the staging folder are skipped and reported. Nothing extracted is ever
executed: MLA only reads tables and copies images/documents.
"""
from __future__ import annotations

import shutil
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from mla.core.validation import ALLOWED_IMAGE_EXTENSIONS
from mla.services.files import ALLOWED_FILE_EXTENSIONS

CATALOG_EXTENSIONS = {".csv", ".txt", ".tsv", ".xlsx", ".json", ".xml", ".pdf"}
BLOCKED_EXTENSIONS = {
    ".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".psm1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh",
    ".msi", ".msp", ".scr", ".lnk", ".hta", ".jar", ".py", ".pyw", ".sh", ".reg", ".cpl", ".sys",
    ".xlsm", ".xltm", ".docm", ".dotm", ".pptm", ".zip", ".rar", ".7z", ".gz", ".tar",
}
MAX_MEMBERS = 20_000
MAX_TOTAL_BYTES = 2 * 1024 ** 3
MAX_RATIO = 200  # uncompressed / compressed, per member (zip bombs)


class ArchiveError(ValueError):
    pass


@dataclass
class ArchiveContents:
    root: Path
    catalogs: list[Path] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    documents: list[Path] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (name in archive, reason)

    def relative(self, path: Path) -> str:
        return path.relative_to(self.root).as_posix()


def extract_archive(source: Path, destination: Path) -> ArchiveContents:
    try:
        archive = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise ArchiveError("O arquivo ZIP está corrompido ou não é um ZIP.") from exc
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    contents = ArchiveContents(root)
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_MEMBERS:
            raise ArchiveError(f"O ZIP tem mais de {MAX_MEMBERS} arquivos; divida em partes menores.")
        if sum(i.file_size for i in infos) > MAX_TOTAL_BYTES:
            raise ArchiveError("O conteúdo do ZIP passa de 2 GB descompactado; divida em partes menores.")
        for info in infos:
            if info.is_dir():
                continue
            name = info.filename
            reason = _refusal(info)
            if reason == "ignore":
                continue
            if reason:
                contents.skipped.append((name, reason))
                continue
            parts = [p for p in PurePosixPath(name.replace("\\", "/")).parts if p not in ("", ".")]
            target = root.joinpath(*parts).resolve()
            if root not in target.parents:
                contents.skipped.append((name, "caminho fora da pasta de importação"))
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                _copy_limited(archive, info, target)
            except (RuntimeError, ArchiveError, zipfile.BadZipFile) as exc:
                target.unlink(missing_ok=True)
                contents.skipped.append((name, str(exc) if isinstance(exc, ArchiveError) else
                                         "arquivo protegido por senha ou corrompido"))
                continue
            ext = target.suffix.lower()
            if ext in ALLOWED_IMAGE_EXTENSIONS:
                contents.images.append(target)
            elif ext in CATALOG_EXTENSIONS and not _is_document_only(target):
                contents.catalogs.append(target)
            else:
                contents.documents.append(target)
    return contents


def _refusal(info: zipfile.ZipInfo) -> str:
    name = info.filename.replace("\\", "/")
    parts = [p for p in name.split("/") if p]
    if not parts:
        return "ignore"
    if parts[0] == "__MACOSX" or parts[-1].startswith("._") or parts[-1].lower() in ("thumbs.db", "desktop.ini"):
        return "ignore"
    if name.startswith("/") or ".." in parts or ":" in parts[0]:
        return "caminho inseguro"
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        return "atalho/link simbólico"
    ext = PurePosixPath(parts[-1]).suffix.lower()
    if ext in BLOCKED_EXTENSIONS:
        return "tipo de arquivo bloqueado (executável, script, macro ou outro compactado)"
    if ext not in CATALOG_EXTENSIONS | ALLOWED_IMAGE_EXTENSIONS | ALLOWED_FILE_EXTENSIONS:
        return "tipo de arquivo não usado pelo MLA"
    if info.compress_size and info.file_size / info.compress_size > MAX_RATIO and info.file_size > 1024 * 1024:
        return "taxa de compressão suspeita"
    return ""


def _copy_limited(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    limit = info.file_size + 1024
    written = 0
    with archive.open(info) as src, target.open("wb") as dst:
        while chunk := src.read(1 << 20):
            written += len(chunk)
            if written > limit:
                raise ArchiveError("tamanho real maior que o declarado")
            dst.write(chunk)


def _is_document_only(path: Path) -> bool:
    """PDFs and text files inside a ZIP are usually manuals, not the catalog; the user can still pick them."""
    return path.suffix.lower() in (".pdf", ".txt")


def remove_staging(folder: Path, staging_root: Path) -> None:
    folder, staging_root = Path(folder).resolve(), Path(staging_root).resolve()
    if folder.exists() and staging_root in folder.parents:
        shutil.rmtree(folder, ignore_errors=True)
