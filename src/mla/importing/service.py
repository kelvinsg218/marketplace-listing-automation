"""Import orchestration: analyze → plan → (user decisions) → commit → report.

Safety rules:
- nothing touches the catalog before `commit`; a plan lives in import_rows and survives restarts;
- updates only change fields that the file fills and that differ, each listed as a change (old → new);
  a field edited by the user after the analysis is kept, not overwritten;
- images and files are only ever added (deduplicated by content), never removed;
- commit runs in ONE transaction (a savepoint per row isolates row errors); cancelling or a crash
  leaves the catalog exactly as before;
- archives are extracted by `archive.extract_archive`, which never extracts executables or macros.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import logging
import os
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mla.core.enums import CommercialStatus, Condition, DataSource, ImportAction, ImportStatus
from mla.core.models import (
    Compatibility, ImportBatch, ImportRow, ImportTemplate, MissingMedia, Product, ProductFile, ProductImage,
    ProductVariant,
)
from mla.core.units import format_money, format_scaled
from mla.core.validation import ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_BYTES
from mla.importing.archive import ArchiveContents, ArchiveError, extract_archive, remove_staging
from mla.importing.mapping import (
    ColumnSuggestion, field_by_key, mapping_problems, normalize_key, suggest_mapping,
)
from mla.importing.readers import SourceError, SourceInfo, SourceRow, detect_format, open_source
from mla.importing.values import ParsedRow, parse_compat_row, parse_product_row
from mla.persistence.db import now_iso
from mla.persistence.imports import ImportRepository
from mla.services.catalog import CatalogError
from mla.services.compatibility import CompatibilityError, default_verification
from mla.services.files import ALLOWED_FILE_EXTENSIONS, FileStoreError
from mla.services.images import ImageError, read_image_info

log = logging.getLogger(__name__)
Progress = Callable[[int, "int | None", str], None]
CHUNK = 500
PREVIEW_ROWS = 50
_NUMBERED = re.compile(r"^(?P<base>.+?)[ _-]\(?(?P<n>\d{1,3})\)?$")


class ImportProblem(ValueError):
    pass


class ImportCancelled(Exception):
    pass


@dataclass
class ImportOptions:
    update_existing: bool = True        # existing SKUs: update the fields the file fills (else ignore them)
    media_folder: str = ""              # extra folder to look for images/files referenced by the base
    match_images_by_sku: bool = True    # also attach images named like the SKU (ABC-1.jpg, ABC-1_2.jpg)
    source: str = DataSource.CLIENT.value  # provenance of imported compatibilities

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ImportOptions":
        names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in (data or {}).items() if k in names})


@dataclass
class Analysis:
    path: Path
    format: str
    target: str
    table_path: Path | None = None
    info: SourceInfo | None = None
    preview: list[SourceRow] = field(default_factory=list)
    suggestions: list[ColumnSuggestion] = field(default_factory=list)
    template: ImportTemplate | None = None
    archive: ArchiveContents | None = None
    staging_dir: Path | None = None
    image_folder: Path | None = None  # images-only association from a folder
    sha256: str = ""

    @property
    def headers(self) -> list[str]:
        return self.info.headers if self.info else []

    @property
    def images_only(self) -> bool:
        if self.image_folder is not None:
            return True
        return self.archive is not None and self.table_path is None and bool(self.archive.images) \
            and not self.table_candidates

    @property
    def table_candidates(self) -> list[Path]:
        if self.archive is None:
            return []
        return [*self.archive.catalogs, *(d for d in self.archive.documents if d.suffix.lower() == ".pdf")]

    @property
    def needs_table_choice(self) -> bool:
        return self.archive is not None and self.table_path is None and bool(self.table_candidates)

    def mapping(self) -> dict[str, str]:
        return {s.column: s.field for s in self.suggestions}


@dataclass
class CommitReport:
    batch_id: int
    counts: dict[str, int]
    message: str


# ---------------------------------------------------------------------------- media lookup
class MediaIndex:
    """Finds files referenced by a base: by relative path, by file name, or by SKU-like name."""

    def __init__(self, roots: list[tuple[Path, int]], limit: int = 100_000):
        self.roots = [r for r, _ in roots]
        self.by_name: dict[str, list[Path]] = {}
        self.by_stem: dict[str, list[Path]] = {}
        count = 0
        for root, depth in roots:
            for path in _walk(root, depth):
                if count >= limit:
                    break
                ext = path.suffix.lower()
                if ext not in ALLOWED_IMAGE_EXTENSIONS and ext not in ALLOWED_FILE_EXTENSIONS:
                    continue
                count += 1
                self.by_name.setdefault(path.name.lower(), []).append(path)
                if ext in ALLOWED_IMAGE_EXTENSIONS:
                    stem = path.stem.lower()
                    self.by_stem.setdefault(stem, []).append(path)
                    match = _NUMBERED.match(stem)
                    if match:
                        self.by_stem.setdefault(match.group("base"), []).append(path)

    def resolve(self, ref: str) -> tuple[str, Path | None]:
        """-> (status, path); status: found | missing | external | ambiguous."""
        if ref.lower().startswith(("http://", "https://")):
            return "external", None
        candidate = Path(ref)
        if candidate.is_absolute():
            return ("found", candidate) if candidate.is_file() else ("missing", None)
        relative = ref.replace("\\", "/").lstrip("./")
        for root in self.roots:
            path = root / relative
            if path.is_file():
                return "found", path
        matches = self.by_name.get(Path(relative).name.lower(), [])
        unique = list(dict.fromkeys(matches))
        if len(unique) == 1:
            return "found", unique[0]
        return ("ambiguous", None) if unique else ("missing", None)

    def for_sku(self, sku: str) -> list[Path]:
        found = list(dict.fromkeys(self.by_stem.get(sku.lower(), [])))
        return sorted(found, key=lambda p: _image_order(p.stem))


def _image_order(stem: str) -> tuple[int, str]:
    match = _NUMBERED.match(stem.lower())
    return (int(match.group("n")) if match else 0, stem.lower())


def _walk(root: Path, max_depth: int):
    if not root or not root.is_dir():
        return
    base_depth = len(root.parts)
    for current, dirs, files in os.walk(root):
        depth = len(Path(current).parts) - base_depth
        if depth >= max_depth:
            dirs[:] = []
        for name in files:
            yield Path(current) / name


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------- display helpers
def _display(key: str, value: Any) -> str:
    if value is None or value == "":
        return "—"
    if key.endswith("_cents"):
        return format_money(value)
    if key == "weight_g":
        return f"{value} g"
    if key.endswith("_mm"):
        return f"{format_scaled(value, 10)} cm"
    if key == "condition":
        return Condition(value).label
    if key == "commercial_status":
        return CommercialStatus(value).label
    text = str(value)
    return text if len(text) <= 120 else text[:117] + "…"


_LABELS = {"weight_g": "Peso", "length_mm": "Comprimento", "width_mm": "Largura", "height_mm": "Altura",
           "original_description": "Descrição original (preservada)", "name": "Nome da variação"}


def _label(key: str) -> str:
    if key.startswith("spec:"):
        return f"Especificação: {key[5:]}"
    if key.startswith("attr:"):
        return f"Atributo: {key[5:]}"
    if key in _LABELS:
        return _LABELS[key]
    spec = field_by_key("products", key)
    return spec.label if spec else key


def _change(key: str, old: Any, new: Any) -> dict[str, Any]:
    return {"field": key, "label": _label(key), "old": _display(key.split(":")[0], old),
            "new": _display(key.split(":")[0], new), "raw_old": old, "raw_new": new}


# ---------------------------------------------------------------------------- service
class ImportService:
    def __init__(self, repo: ImportRepository, ctx):
        self.repo = repo
        self.ctx = ctx  # AppContext: products, catalog, images, files, compatibility, paths, db

    # ------------------------------------------------------------------ analysis (steps 1-5)
    def analyze(self, path: Path, target: str = "products", sheet: str | None = None) -> Analysis:
        path = Path(path)
        if path.is_dir():
            return self.analyze_image_folder(path)
        try:
            fmt = detect_format(path)
        except SourceError as exc:  # empty, damaged or unsupported file: a message for the user, not a crash
            raise ImportProblem(str(exc)) from exc
        analysis = Analysis(path=path, format=fmt, target=target, sha256=_sha256(path))
        if fmt == "zip":
            staging = self.ctx.paths.imports / f"zip-{uuid.uuid4().hex[:12]}"
            try:
                analysis.archive = extract_archive(path, staging)
            except ArchiveError as exc:
                remove_staging(staging, self.ctx.paths.imports)
                raise ImportProblem(str(exc)) from exc
            analysis.staging_dir = staging
            if len(analysis.archive.catalogs) == 1:
                return self.choose_table(analysis, analysis.archive.catalogs[0], sheet)
            if not analysis.table_candidates and not analysis.archive.images:
                raise ImportProblem("O ZIP não tem planilha, catálogo nem imagens que o MLA possa usar.")
            return analysis
        return self.choose_table(analysis, path, sheet)

    def analyze_image_folder(self, folder: Path) -> Analysis:
        return Analysis(path=folder, format="folder", target="images", image_folder=folder)

    def choose_table(self, analysis: Analysis, table: Path, sheet: str | None = None) -> Analysis:
        try:
            source = open_source(table, sheet=sheet)
            preview = source.preview(PREVIEW_ROWS)
            if not preview and sheet is None and source.info.sheets:
                # a cover sheet (title only) before the data: use the first sheet that has rows
                for name in source.info.sheets[1:]:
                    try:
                        candidate = open_source(table, sheet=name)
                    except SourceError:
                        continue
                    preview = candidate.preview(PREVIEW_ROWS)
                    if preview:
                        source = candidate
                        break
        except SourceError as exc:
            raise ImportProblem(str(exc)) from exc
        analysis.table_path = table
        analysis.info = source.info
        analysis.preview = preview
        if not analysis.preview:
            raise ImportProblem("O arquivo tem cabeçalho, mas nenhuma linha de dados.")
        analysis.suggestions = suggest_mapping(source.info.headers, [r.values for r in analysis.preview],
                                               analysis.target)
        analysis.template = self.find_template(source.info.headers, analysis.target)
        if analysis.template is not None:
            self.apply_template(analysis, analysis.template)
        return analysis

    def retarget(self, analysis: Analysis, target: str) -> Analysis:
        analysis.target = target
        if analysis.info:
            analysis.suggestions = suggest_mapping(analysis.info.headers, [r.values for r in analysis.preview], target)
            analysis.template = self.find_template(analysis.info.headers, target)
            if analysis.template:
                self.apply_template(analysis, analysis.template)
        return analysis

    def discard_analysis(self, analysis: Analysis) -> None:
        if analysis.staging_dir is not None:
            remove_staging(analysis.staging_dir, self.ctx.paths.imports)

    # ------------------------------------------------------------------ templates
    def save_template(self, name: str, analysis: Analysis, mapping: dict[str, str],
                      options: ImportOptions | None = None) -> ImportTemplate:
        name = name.strip()
        if not name:
            raise ImportProblem("Dê um nome ao modelo de importação.")
        template = ImportTemplate(name=name, target=analysis.target, headers=list(analysis.headers),
                                  mapping={k: v for k, v in mapping.items() if v},
                                  options=(options or ImportOptions()).to_dict())
        self.repo.save_template(template)
        return template

    def templates(self, target: str | None = None) -> list[ImportTemplate]:
        return self.repo.templates(target)

    def find_template(self, headers: list[str], target: str) -> ImportTemplate | None:
        keys = {normalize_key(h) for h in headers}
        best, best_score = None, 0.0
        for template in self.repo.templates(target):
            stored = {normalize_key(h) for h in template.headers}
            if not stored or not keys:
                continue
            score = len(keys & stored) / len(keys | stored)
            if score > best_score:
                best, best_score = template, score
        return best if best_score >= 0.8 else None

    @staticmethod
    def apply_template(analysis: Analysis, template: ImportTemplate) -> None:
        by_key = {normalize_key(c): f for c, f in template.mapping.items()}
        for suggestion in analysis.suggestions:
            key = normalize_key(suggestion.column)
            if key in by_key:
                suggestion.field = by_key[key]
                suggestion.confidence = "template"
                suggestion.reason = f"Do modelo “{template.name}”."
            elif suggestion.confidence != "none":
                suggestion.field, suggestion.confidence = "", "none"
                suggestion.reason = f"O modelo “{template.name}” ignora esta coluna."

    # ------------------------------------------------------------------ planning (steps 6-9)
    def plan(self, analysis: Analysis, mapping: dict[str, str], options: ImportOptions | None = None,
             progress: Progress | None = None, cancel: threading.Event | None = None) -> ImportBatch:
        options = options or ImportOptions()
        target = "images" if analysis.images_only else analysis.target
        if analysis.needs_table_choice:
            raise ImportProblem("Escolha qual arquivo do ZIP é o catálogo.")
        if target != "images":
            problems = mapping_problems(mapping, target)
            if problems:
                raise ImportProblem("\n".join(problems))
        batch = ImportBatch(
            source_name=analysis.path.name, format=analysis.format, target=target, source_path=str(analysis.path),
            source_sha256=analysis.sha256, mapping={k: v for k, v in mapping.items() if v},
            options=options.to_dict() | ({"table": str(analysis.table_path), "sheet": analysis.info.sheet}
                                         if analysis.info else {}),
            staging_dir=str(analysis.staging_dir or ""))
        self.repo.create_batch(batch)
        progress = progress or (lambda *_: None)
        try:
            if target == "images":
                self._plan_images(batch, analysis, options, progress, cancel)
            elif target == "compatibility":
                self._plan_compat(batch, analysis, mapping, options, progress, cancel)
            else:
                self._plan_products(batch, analysis, mapping, options, progress, cancel)
        except ImportCancelled:
            self.repo.delete_rows(batch.id)
            self.repo.update_batch(batch.id, status=ImportStatus.CANCELLED, finished_at=now_iso(),
                                   message="Análise cancelada; nada foi gravado no catálogo.")
            raise
        except (SourceError, OSError) as exc:
            self.repo.delete_rows(batch.id)
            self.repo.update_batch(batch.id, status=ImportStatus.FAILED, finished_at=now_iso(),
                                   message=f"Falha ao ler o arquivo: {exc}")
            raise ImportProblem(f"Falha ao ler o arquivo: {exc}") from exc
        counts = self.repo.counts_by_action(batch.id)
        self.repo.update_batch(batch.id, status=ImportStatus.PLANNED, planned_at=now_iso(), counts={"planned": counts})
        log.info("importação %s planejada: %s", batch.id, counts)
        return self.repo.get_batch(batch.id)  # type: ignore[return-value]

    def _media_index(self, analysis: Analysis, options: ImportOptions) -> MediaIndex:
        roots: list[tuple[Path, int]] = []
        if analysis.staging_dir is not None:
            roots.append((analysis.staging_dir, 8))
        if analysis.table_path is not None and analysis.staging_dir is None:
            roots.append((analysis.table_path.parent, 2))  # source folder and its sub-folders (fotos/, imagens/)
        if options.media_folder:
            roots.append((Path(options.media_folder), 8))
        if analysis.image_folder is not None:
            roots.append((analysis.image_folder, 8))
        return MediaIndex(roots)

    def _media(self, refs: list[str], kind: str, index: MediaIndex, cache: dict[str, str],
               origin: str = "coluna") -> list[dict[str, str]]:
        result = []
        for ref in dict.fromkeys(refs):
            status, path = index.resolve(ref)
            entry = {"ref": ref, "kind": kind, "status": status, "path": str(path or ""), "sha256": "",
                     "origin": origin}
            if status == "found" and path is not None:
                problem = _media_problem(path, kind)
                if problem:
                    entry["status"], entry["note"] = "invalid", problem
                else:
                    key = str(path)
                    if key not in cache:
                        cache[key] = _sha256(path)
                    entry["sha256"] = cache[key]
            result.append(entry)
        return result

    def _source_rows(self, analysis: Analysis):
        source = open_source(analysis.table_path, sheet=analysis.info.sheet or None)  # type: ignore[arg-type]
        return source.rows()

    def _plan_products(self, batch: ImportBatch, analysis: Analysis, mapping: dict[str, str],
                       options: ImportOptions, progress: Progress, cancel) -> None:
        index = self._media_index(analysis, options)
        state = _PlanState()
        buffer: list[tuple[SourceRow, ParsedRow]] = []
        total = analysis.info.total_rows if analysis.info else None
        done = 0
        for srow in self._source_rows(analysis):
            _check(cancel)
            buffer.append((srow, parse_product_row(srow.values, mapping)))
            if len(buffer) >= CHUNK:
                self.repo.add_rows(self._product_rows(batch, buffer, options, index, state))
                done += len(buffer)
                buffer.clear()
                progress(done, total, f"{done} linha(s) analisadas")
        if buffer:
            self.repo.add_rows(self._product_rows(batch, buffer, options, index, state))
            done += len(buffer)
        if done == 0:
            raise ImportProblem("O arquivo não tem linhas de dados.")
        self._check_parents(batch, state)
        progress(done, done, f"{done} linha(s) analisadas")

    def _product_rows(self, batch: ImportBatch, chunk, options: ImportOptions, index: MediaIndex,
                      state: "_PlanState") -> list[ImportRow]:
        products = self.ctx.products
        skus = [p.data["sku"] for _, p in chunk if p.data.get("sku")]
        parents = [p.data["parent_sku"] for _, p in chunk if p.data.get("parent_sku")]
        existing = products.ids_for_skus(list(dict.fromkeys(skus + parents)))
        rows = []
        for srow, parsed in chunk:
            row = ImportRow(batch_id=batch.id, row_no=srow.number, action=ImportAction.CREATE)  # type: ignore[arg-type]
            issues = list(parsed.issues)
            sku = parsed.data.get("sku", "")
            row.sku = sku
            values = {k: v for k, v in parsed.data.items()}
            row.data = {"values": values, "specs": parsed.specs, "attributes": parsed.attributes,
                        "where": srow.where}
            owner = products.variant_owner(sku) if sku and sku.lower() not in existing else None
            parent = parsed.data.get("parent_sku", "") or (_sku_of(products, owner[0]) if owner else "")
            if not sku:
                issues.append({"severity": "error", "message": "Linha sem SKU."})
            elif parent:
                self._plan_variant(row, parsed, parent, owner, existing, index, state, issues)
            else:
                self._plan_product(row, parsed, existing, options, index, state, issues)
            if srow.review and row.action in (ImportAction.CREATE, ImportAction.UPDATE):
                issues.append({"severity": "review", "message": srow.review})
                row.data["intended"] = row.action.value
                row.action = ImportAction.REVIEW
            if any(i["severity"] == "error" for i in issues):
                row.action = ImportAction.ERROR
            row.issues = issues
            row.decision = {ImportAction.CREATE: "create",
                            ImportAction.UPDATE: "update" if options.update_existing else "skip"}.get(row.action, "skip")
            if not parent and sku and sku.lower() not in state.file_skus:
                state.file_skus[sku.lower()] = (row.row_no, row.action is not ImportAction.ERROR, srow.where)
            rows.append(row)
        return rows

    def _plan_product(self, row: ImportRow, parsed: ParsedRow, existing: dict[str, int], options: ImportOptions,
                      index: MediaIndex, state: "_PlanState", issues: list[dict[str, str]]) -> None:
        data, sku = parsed.data, row.sku
        first = state.file_skus.get(sku.lower())
        if first is not None:
            issues.append({"severity": "error",
                           "message": f"SKU repetido no arquivo (já aparece na {first[2]})."})
        refs = parsed.images
        media = self._media(refs, "image", index, state.sha_cache)
        if options.match_images_by_sku:
            named = [p for p in index.for_sku(sku) if str(p) not in {m["path"] for m in media}]
            media += self._media([str(p) for p in named], "image", index, state.sha_cache, origin="sku")
        media += self._media(parsed.files, "file", index, state.sha_cache)
        row.media = media
        _media_issues(media, issues)
        gtin = data.get("gtin", "")
        pid = existing.get(sku.lower())
        if gtin:
            others = [i for i in self.ctx.products.ids_for_gtin(gtin) if i != pid]
            if others:
                issues.append({"severity": "warning", "message": f"GTIN {gtin} já usado por outro produto do "
                                                                 f"catálogo (SKU {_sku_of(self.ctx.products, others[0])})."})
            if gtin in state.file_gtins and state.file_gtins[gtin] != sku.lower():
                issues.append({"severity": "warning", "message": f"GTIN {gtin} repetido no arquivo."})
            state.file_gtins.setdefault(gtin, sku.lower())
        if pid is None:
            row.action = ImportAction.CREATE
            name = data.get("internal_name") or data.get("commercial_name") or data.get("title") or ""
            row.name = name
            if not name:
                issues.append({"severity": "error", "message": "Produto novo sem nome: mapeie a coluna de nome ou "
                                                               "preencha na origem."})
            return
        product = self.ctx.products.get(pid)
        row.product_id = pid
        row.name = data.get("internal_name") or (product.internal_name if product else "")
        changes = _diff_product(product, parsed) if product else []
        known = {i.sha256 for i in product.images} | {f.sha256 for f in product.files} if product else set()
        missing_known = {m.reference.lower() for m in product.missing_media} if product else set()
        new_media = [m for m in media if (m["status"] == "found" and m["sha256"] not in known)
                     or (m["status"] != "found" and m["ref"].lower() not in missing_known)]
        row.changes = changes
        row.action = ImportAction.UPDATE if changes or new_media else ImportAction.UNCHANGED

    def _plan_variant(self, row: ImportRow, parsed: ParsedRow, parent: str, owner, existing: dict[str, int],
                      index: MediaIndex, state: "_PlanState", issues: list[dict[str, str]]) -> None:
        data, sku = parsed.data, row.sku
        row.parent_sku = parent
        if sku.lower() in existing:
            issues.append({"severity": "error", "message": f"O SKU {sku} já é de um produto; uma variação precisa "
                                                           "de SKU próprio."})
            return
        if sku.lower() in state.variant_skus:
            issues.append({"severity": "error", "message": f"SKU de variação repetido no arquivo "
                                                           f"(já na {state.variant_skus[sku.lower()]})."})
            return
        state.variant_skus[sku.lower()] = row.data.get("where") or f"linha {row.row_no}"
        name = data.get("variant_name", "")
        parent_id = existing.get(parent.lower()) or self.ctx.products.id_for_sku(parent)
        if owner is not None and parent_id is not None and owner[0] != parent_id:
            issues.append({"severity": "error", "message": f"A variação {sku} pertence a outro produto do catálogo."})
            return
        row.media = self._media(parsed.images, "image", index, state.sha_cache)
        _media_issues(row.media, issues)
        if owner is not None:
            product = self.ctx.products.get(owner[0])
            variant = next((v for v in product.variants if (v.sku or "").lower() == sku.lower()), None) \
                if product else None
            row.product_id = owner[0]
            row.name = name or (variant.name if variant else "")
            changes = []
            if variant is not None:
                if name and name != variant.name:
                    changes.append(_change("name", variant.name, name))
                for key in ("price_cents", "stock"):
                    if key in data and data[key] != getattr(variant, key):
                        changes.append(_change(key, getattr(variant, key), data[key]))
                for key, value in parsed.attributes.items():
                    if variant.attributes.get(key) != value:
                        changes.append(_change(f"attr:{key}", variant.attributes.get(key), value))
            known = {i.sha256 for i in product.images} if product else set()
            new_media = [m for m in row.media if m["status"] == "found" and m["sha256"] not in known]
            row.changes = changes
            row.action = ImportAction.UPDATE if changes or new_media else ImportAction.UNCHANGED
            return
        row.name = name
        if not name:
            issues.append({"severity": "error", "message": "Variação sem nome: mapeie a coluna “Nome da variação” "
                                                           "(ex.: Cor: Azul)."})
        row.action = ImportAction.CREATE
        if parent_id is None:
            state.pending_parents.add(parent.lower())

    def _check_parents(self, batch: ImportBatch, state: "_PlanState") -> None:
        if not state.pending_parents:
            return
        # collected first: updating rows while paging over the same filter would skip some of them
        variants = [r for r in self.repo.rows(batch.id, actions=[ImportAction.CREATE, ImportAction.REVIEW],
                                              variants_last=True, limit=10**9) if r.parent_sku]
        for row in variants:
            key = row.parent_sku.lower()
            if key not in state.pending_parents:
                continue
            found = state.file_skus.get(key)
            if found is not None and found[1]:
                continue
            message = (f"O produto pai {row.parent_sku} tem erro na {found[2]}." if found is not None else
                       f"Produto pai {row.parent_sku} não está no arquivo nem no catálogo.")
            row.issues.append({"severity": "error", "message": message})
            row.action, row.decision = ImportAction.ERROR, "skip"
            self.repo.update_row(row)

    def _plan_compat(self, batch: ImportBatch, analysis: Analysis, mapping: dict[str, str], options: ImportOptions,
                     progress: Progress, cancel) -> None:
        source = DataSource(options.source)
        seen: dict[tuple, str] = {}
        buffer: list[tuple[SourceRow, ParsedRow]] = []
        done = 0
        total = analysis.info.total_rows if analysis.info else None

        def flush() -> None:
            skus = list(dict.fromkeys(p.data["sku"] for _, p in buffer if p.data.get("sku")))
            existing = self.ctx.products.ids_for_skus(skus)
            rows = []
            for srow, parsed in buffer:
                data = parsed.data
                row = ImportRow(batch_id=batch.id, row_no=srow.number, action=ImportAction.CREATE,  # type: ignore[arg-type]
                                sku=data.get("sku", ""), name=f"{data.get('brand', '')} {data.get('model', '')}".strip())
                issues = list(parsed.issues)
                row.data = {"values": data, "where": srow.where, "source": source.value}
                pid = existing.get(row.sku.lower()) if row.sku else None
                if row.sku and pid is None:
                    issues.append({"severity": "error", "message": f"SKU {row.sku} não está no catálogo; importe o "
                                                                   "produto antes da compatibilidade."})
                row.product_id = pid
                if pid is not None and not parsed.has_errors:
                    probe = Compatibility(pid, data.get("model", ""), brand=data.get("brand", ""),
                                          version=data.get("version", ""), year_from=data.get("year_from"),
                                          year_to=data.get("year_to"))
                    key = (pid, probe.brand.lower(), probe.model.lower(), probe.version.lower(), probe.year_from or 0,
                           probe.year_to or 0)
                    if key in seen:
                        row.action = ImportAction.UNCHANGED
                        issues.append({"severity": "warning", "message": f"Repetida no arquivo ({seen[key]})."})
                    elif self.ctx.compatibility.repo.find_duplicate(probe):
                        row.action = ImportAction.UNCHANGED
                        issues.append({"severity": "warning", "message": "Já cadastrada no catálogo."})
                    seen.setdefault(key, srow.where)
                if srow.review and row.action is ImportAction.CREATE:
                    issues.append({"severity": "review", "message": srow.review})
                    row.data["intended"] = "create"
                    row.action = ImportAction.REVIEW
                if any(i["severity"] == "error" for i in issues):
                    row.action = ImportAction.ERROR
                row.issues = issues
                row.decision = "create" if row.action is ImportAction.CREATE else "skip"
                rows.append(row)
            self.repo.add_rows(rows)

        for srow in self._source_rows(analysis):
            _check(cancel)
            buffer.append((srow, parse_compat_row(srow.values, mapping)))
            if len(buffer) >= CHUNK:
                flush()
                done += len(buffer)
                buffer.clear()
                progress(done, total, f"{done} linha(s) analisadas")
        if buffer:
            flush()
            done += len(buffer)
        progress(done, done, f"{done} linha(s) analisadas")

    def _plan_images(self, batch: ImportBatch, analysis: Analysis, options: ImportOptions, progress: Progress,
                     cancel) -> None:
        if analysis.image_folder is not None:
            files = [p for p in _walk(analysis.image_folder, 8) if p.suffix.lower() in ALLOWED_IMAGE_EXTENSIONS]
        else:
            files = list(analysis.archive.images) if analysis.archive else []
        if not files:
            raise ImportProblem("Nenhuma imagem JPG, PNG ou WEBP encontrada.")
        stems: dict[str, list[Path]] = {}
        for path in files:
            stem = path.stem.lower()
            match = _NUMBERED.match(stem)
            stems.setdefault(stem, []).append(path)
            if match:
                stems.setdefault(match.group("base"), []).append(path)
        by_sku = self.ctx.products.ids_for_skus(list(stems))
        waiting = self.ctx.products.products_missing({p.name.lower() for p in files})
        per_product: dict[int, list[tuple[Path, str]]] = {}
        matched: set[Path] = set()
        for stem, paths in stems.items():
            pid = by_sku.get(stem)
            if pid is None:
                continue
            for path in sorted(paths, key=lambda p: _image_order(p.stem)):
                if path not in matched:
                    per_product.setdefault(pid, []).append((path, "sku"))
                    matched.add(path)
        for name, pids in waiting.items():
            for path in (p for p in files if p.name.lower() == name):
                for pid in pids:
                    if all(path != existing for existing, _ in per_product.get(pid, [])):
                        per_product.setdefault(pid, []).append((path, "pendente"))
                matched.add(path)
        cache: dict[str, str] = {}
        rows: list[ImportRow] = []
        number = 0
        for pid, entries in per_product.items():
            _check(cancel)
            product = self.ctx.products.get(pid)
            if product is None:
                continue
            number += 1
            media = []
            for path, origin in entries:
                entry = {"ref": path.name, "kind": "image", "status": "found", "path": str(path), "sha256": "",
                         "origin": origin}
                problem = _media_problem(path, "image")
                if problem:
                    entry["status"], entry["note"] = "invalid", problem
                else:
                    entry["sha256"] = cache.setdefault(str(path), _sha256(path))
                media.append(entry)
            known = {i.sha256 for i in product.images}
            new = [m for m in media if m["status"] == "found" and m["sha256"] not in known]
            # a damaged file must still be recorded as pending media (the client has to send it again)
            pending = {_media_name(m.reference) for m in product.missing_media}
            new += [m for m in media if m["status"] == "invalid" and _media_name(m["ref"]) not in pending]
            issues: list[dict[str, str]] = []
            _media_issues(media, issues)
            action = ImportAction.UPDATE if new else ImportAction.UNCHANGED
            rows.append(ImportRow(batch_id=batch.id, row_no=number, action=action,  # type: ignore[arg-type]
                                  decision="update" if new else "skip", sku=product.sku, name=product.internal_name,
                                  product_id=pid, media=media, issues=issues,
                                  data={"where": ", ".join(m["ref"] for m in media[:3]) + ("…" if len(media) > 3 else "")}))
            if len(rows) >= CHUNK:
                self.repo.add_rows(rows)
                rows = []
            progress(number, len(per_product), f"{number} produto(s) com imagens")
        for path in files:
            if path in matched:
                continue
            number += 1
            rows.append(ImportRow(batch_id=batch.id, row_no=number, action=ImportAction.SKIP,  # type: ignore[arg-type]
                                  decision="skip", name=path.name, data={"where": path.name},
                                  issues=[{"severity": "warning", "message": "Nenhum produto com SKU igual ao nome do "
                                                                             "arquivo."}]))
        self.repo.add_rows(rows)

    # ------------------------------------------------------------------ decisions
    def set_decision(self, batch_id: int, row_ids: list[int], decision: str) -> None:
        if decision not in ("create", "update", "skip"):
            raise ImportProblem("Decisão inválida.")
        self._ensure_status(batch_id, ImportStatus.PLANNED)
        if decision == "skip":
            self.repo.set_decision(batch_id, row_ids, "skip")
            return
        for row in self.repo.rows_by_ids(batch_id, row_ids):
            allowed = _allowed_decision(row)
            if allowed is None:
                continue  # errors / unchanged rows cannot be included
            self.repo.set_decision(batch_id, [row.id], allowed)  # type: ignore[list-item]

    def set_decision_for_action(self, batch_id: int, action: ImportAction, decision: str) -> None:
        self._ensure_status(batch_id, ImportStatus.PLANNED)
        if action in (ImportAction.ERROR, ImportAction.UNCHANGED, ImportAction.SKIP) and decision != "skip":
            raise ImportProblem("Linhas com erro ou sem mudanças não podem ser incluídas.")
        if action is ImportAction.REVIEW and decision != "skip":
            for row in self.repo.rows(batch_id, actions=[ImportAction.REVIEW], limit=10**9):
                allowed = _allowed_decision(row)
                if allowed:
                    self.repo.set_decision(batch_id, [row.id], allowed)  # type: ignore[list-item]
            return
        self.repo.set_decision_for_action(batch_id, action, decision)

    def _ensure_status(self, batch_id: int, status: ImportStatus) -> ImportBatch:
        batch = self.repo.get_batch(batch_id)
        if batch is None:
            raise ImportProblem("Importação não encontrada.")
        if batch.status is not status:
            raise ImportProblem(f"Esta importação está {batch.status.label.lower()}.")
        return batch

    # ------------------------------------------------------------------ commit (steps 10-11)
    def commit(self, batch_id: int, progress: Progress | None = None,
               cancel: threading.Event | None = None) -> CommitReport:
        batch = self._ensure_status(batch_id, ImportStatus.PLANNED)
        progress = progress or (lambda *_: None)
        decisions = ["create", "update"]
        total = self.repo.count_rows(batch_id, decisions=decisions)
        self.repo.update_batch(batch_id, status=ImportStatus.COMMITTING, message="")
        try:
            stored = self._store_media(batch_id, decisions, total, progress, cancel)
            counts = {"created": 0, "updated": 0, "unchanged": 0, "errors": 0, "images": 0, "missing_media": 0}
            db = self.ctx.db
            with db.transaction() as conn:
                self.repo.clear_outcomes(batch_id)
                done, offset = 0, 0
                while True:
                    rows = self.repo.rows(batch_id, decisions=decisions, variants_last=True, limit=CHUNK,
                                          offset=offset)
                    if not rows:
                        break
                    for row in rows:
                        _check(cancel)
                        conn.execute("SAVEPOINT import_row")
                        try:
                            outcome, pid = self._apply(batch, row, stored, counts)
                            conn.execute("RELEASE import_row")
                        except (CatalogError, CompatibilityError, ImageError, FileStoreError, ValueError) as exc:
                            conn.execute("ROLLBACK TO import_row")
                            conn.execute("RELEASE import_row")
                            outcome, pid = f"Erro: {exc}", None
                            counts["errors"] += 1
                        self.repo.set_outcome(row.id, outcome, pid)  # type: ignore[arg-type]
                        done += 1
                        if done % 50 == 0 or done == total:
                            progress(done, total, f"Gravando: {done} de {total}")
                    offset += CHUNK
                conn.execute("UPDATE import_rows SET outcome = CASE WHEN action = 'error' THEN"
                             " 'Recusado: erro na análise' ELSE 'Ignorado' END WHERE batch_id = ? AND decision = 'skip'",
                             (batch_id,))
                counts["skipped"] = self.repo.count_rows(batch_id, decisions=["skip"])
                # rows refused by the analysis are not "ignored": the client must fix them at the source
                counts["rejected"] = self.repo.count_rows(batch_id, actions=[ImportAction.ERROR], decisions=["skip"])
                message = _commit_message(counts)
                self.repo.update_batch(batch_id, status=ImportStatus.COMPLETED, finished_at=now_iso(),
                                       message=message, counts=batch.counts | {"result": counts})
        except ImportCancelled:
            self.repo.update_batch(batch_id, status=ImportStatus.PLANNED,
                                   message="Gravação cancelada: nenhuma alteração foi feita no catálogo.")
            raise
        except Exception as exc:
            self.repo.update_batch(batch_id, status=ImportStatus.PLANNED,
                                   message=f"Falha ao gravar ({exc}); nenhuma alteração foi feita no catálogo.")
            raise
        if batch.staging_dir:
            remove_staging(Path(batch.staging_dir), self.ctx.paths.imports)
        log.info("importação %s concluída: %s", batch_id, counts)
        return CommitReport(batch_id, counts, message)

    def _store_media(self, batch_id: int, decisions: list[str], total: int, progress: Progress,
                     cancel) -> dict[str, ProductImage | ProductFile]:
        """Copy referenced files into the stores before the transaction (content-addressed, idempotent)."""
        stored: dict[str, ProductImage | ProductFile] = {}
        offset = 0
        done = 0
        while True:
            rows = self.repo.rows(batch_id, decisions=decisions, limit=CHUNK, offset=offset)
            if not rows:
                break
            for row in rows:
                _check(cancel)
                for media in row.media:
                    if media.get("status") != "found" or media["path"] in stored:
                        continue
                    try:
                        if media["kind"] == "image":
                            stored[media["path"]] = self.ctx.images.import_file(Path(media["path"]))
                        else:
                            stored[media["path"]] = self.ctx.files.import_file(Path(media["path"]))
                    except (ImageError, FileStoreError, OSError) as exc:
                        log.warning("mídia não copiada %s: %s", media["path"], exc)
                done += 1
                if done % 50 == 0:
                    progress(done, total, f"Copiando imagens e arquivos: {done} de {total} linha(s)")
            offset += CHUNK
        return stored

    def _apply(self, batch: ImportBatch, row: ImportRow, stored, counts: dict[str, int]) -> tuple[str, int | None]:
        origin = f"Importação #{batch.id}"
        if batch.target == "compatibility":
            return self._apply_compat(batch, row, counts)
        if batch.target == "images" or row.parent_sku:
            if row.parent_sku:
                return self._apply_variant(row, stored, origin, counts)
            product = self.ctx.products.get(row.product_id) if row.product_id else None
            if product is None:
                raise ValueError("o produto não existe mais no catálogo.")
            added = _attach_media(product, row.media, stored, origin, counts)
            self.ctx.catalog.save(product, source=origin)
            counts["updated"] += 1
            return f"Atualizado: {added} imagem(ns) adicionada(s)", product.id
        values = row.data.get("values", {})
        if row.decision == "create":
            if self.ctx.products.sku_exists(row.sku):
                raise ValueError(f"o SKU {row.sku} passou a existir no catálogo depois da análise.")
            product = Product(internal_name=values.get("internal_name") or values.get("commercial_name")
                              or values.get("title") or "", sku=row.sku)
            for key, value in values.items():
                if key in ("sku", "parent_sku", "variant_name"):
                    continue
                _set(product, key, value)
            product.specs = dict(row.data.get("specs") or {})
            product.custom_attributes = dict(row.data.get("attributes") or {})
            product.original_description = values.get("description", "")
            product.source = f"{origin} ({batch.source_name})"
            _attach_media(product, row.media, stored, origin, counts)
            self.ctx.catalog.save(product, source=origin)
            counts["created"] += 1
            return "Criado", product.id
        product = self.ctx.products.get(row.product_id) if row.product_id else None
        if product is None:
            raise ValueError("o produto não existe mais no catálogo.")
        kept = 0
        for change in row.changes:
            key = change["field"]
            current = _get(product, key)
            if current != change["raw_old"]:
                kept += 1  # edited after the analysis: the user's newer value wins
                continue
            _set(product, key, change["raw_new"])
        added = _attach_media(product, row.media, stored, origin, counts)
        self.ctx.catalog.save(product, source=origin)
        counts["updated"] += 1
        text = "Atualizado"
        if added:
            text += f", {added} imagem(ns)/arquivo(s) adicionado(s)"
        if kept:
            text += f"; {kept} campo(s) mantido(s) porque mudaram depois da análise"
        return text, product.id

    def _apply_variant(self, row: ImportRow, stored, origin: str, counts: dict[str, int]) -> tuple[str, int | None]:
        values = row.data.get("values", {})
        parent_id = row.product_id or self.ctx.products.id_for_sku(row.parent_sku)
        product = self.ctx.products.get(parent_id) if parent_id else None
        if product is None:
            raise ValueError(f"o produto pai {row.parent_sku} não foi importado nem existe no catálogo.")
        variant = next((v for v in product.variants if (v.sku or "").lower() == row.sku.lower()), None)
        if variant is None:
            variant = ProductVariant(name=values.get("variant_name", ""), sku=row.sku,
                                     price_cents=values.get("price_cents"), stock=values.get("stock") or 0,
                                     attributes=dict(row.data.get("attributes") or {}))
            product.variants.append(variant)
            result = "Variação criada"
            counts["created"] += 1
        else:
            for change in row.changes:
                key = change["field"]
                if key == "name":
                    variant.name = change["raw_new"]
                elif key.startswith("attr:"):
                    variant.attributes[key[5:]] = change["raw_new"]
                else:
                    setattr(variant, key, change["raw_new"])
            result = "Variação atualizada"
            counts["updated"] += 1
        _attach_media(product, row.media, stored, origin, counts, variant=variant.name)
        self.ctx.catalog.save(product, source=origin)
        return result, product.id

    def _apply_compat(self, batch: ImportBatch, row: ImportRow, counts: dict[str, int]) -> tuple[str, int | None]:
        values = row.data.get("values", {})
        if row.product_id is None or self.ctx.products.get(row.product_id) is None:
            raise ValueError("o produto não existe mais no catálogo.")
        source = DataSource(row.data.get("source") or DataSource.CLIENT.value)
        detail = values.get("source_detail") or f"Importação #{batch.id} ({batch.source_name})"
        item = Compatibility(row.product_id, values.get("model", ""), brand=values.get("brand", ""),
                             version=values.get("version", ""), year_from=values.get("year_from"),
                             year_to=values.get("year_to"), reference_code=values.get("reference_code", ""),
                             notes=values.get("notes", ""), source=source, source_detail=detail,
                             verification=default_verification(source))
        self.ctx.compatibility.save(item)
        counts["created"] += 1
        return "Compatibilidade criada", row.product_id

    # ------------------------------------------------------------------ history / recovery / report
    def history(self, limit: int = 100) -> list[ImportBatch]:
        return self.repo.list_batches(limit)

    def get(self, batch_id: int) -> ImportBatch | None:
        return self.repo.get_batch(batch_id)

    def rows(self, batch_id: int, **filters) -> list[ImportRow]:
        return self.repo.rows(batch_id, **filters)

    def count_rows(self, batch_id: int, **filters) -> int:
        return self.repo.count_rows(batch_id, **filters)

    def discard(self, batch_id: int) -> None:
        batch = self.repo.get_batch(batch_id)
        if batch is None:
            return
        if batch.status in (ImportStatus.COMPLETED, ImportStatus.COMMITTING):
            raise ImportProblem("Importações gravadas ficam no histórico e não podem ser descartadas.")
        self.repo.delete_rows(batch_id)
        self.repo.update_batch(batch_id, status=ImportStatus.DISCARDED, finished_at=now_iso(),
                               message="Descartada antes da confirmação; nada foi gravado.")
        if batch.staging_dir:
            remove_staging(Path(batch.staging_dir), self.ctx.paths.imports)

    def recover_interrupted(self) -> int:
        """After a crash: a plan in progress is lost; a commit in progress was rolled back by SQLite."""
        count = 0
        for batch in self.repo.batches_with_status([ImportStatus.PLANNING, ImportStatus.COMMITTING]):
            if batch.status is ImportStatus.PLANNING:
                self.repo.delete_rows(batch.id)  # type: ignore[arg-type]
                self.repo.update_batch(batch.id, status=ImportStatus.FAILED, finished_at=now_iso(),
                                       message="Análise interrompida (o MLA foi fechado); importe de novo.")
            else:
                self.repo.update_batch(batch.id, status=ImportStatus.PLANNED,
                                       message="A gravação foi interrompida e desfeita; nada foi alterado. "
                                               "Revise e confirme de novo.")
            count += 1
        return count

    def export_report(self, batch_id: int, target: Path) -> int:
        batch = self.repo.get_batch(batch_id)
        if batch is None:
            raise ImportProblem("Importação não encontrada.")
        written = 0
        with Path(target).open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.writer(fh, delimiter=";")
            writer.writerow(["Linha", "Onde", "SKU", "Nome", "Análise", "Decisão", "Resultado", "Alterações",
                             "Problemas"])
            offset = 0
            while True:
                rows = self.repo.rows(batch_id, limit=CHUNK, offset=offset)
                if not rows:
                    break
                for row in rows:
                    writer.writerow([
                        row.row_no, row.data.get("where", ""), row.sku, row.name, row.action.label,
                        {"create": "Criar", "update": "Atualizar", "skip": "Ignorar"}[row.decision], row.outcome,
                        "; ".join(f"{c['label']}: {c['old']} → {c['new']}" for c in row.changes),
                        "; ".join(i["message"] for i in row.issues)])
                    written += 1
                offset += CHUNK
        return written


@dataclass
class _PlanState:
    file_skus: dict[str, tuple[int, bool, str]] = field(default_factory=dict)  # sku -> (row, ok, where)
    variant_skus: dict[str, str] = field(default_factory=dict)
    file_gtins: dict[str, str] = field(default_factory=dict)
    pending_parents: set[str] = field(default_factory=set)
    sha_cache: dict[str, str] = field(default_factory=dict)


def _check(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise ImportCancelled()


def _sku_of(products, product_id: int) -> str:
    product = products.get(product_id)
    return product.sku if product else ""


def _media_problem(path: Path, kind: str) -> str:
    ext = path.suffix.lower()
    if kind == "image":
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            return f"formato não aceito ({ext or 'sem extensão'})"
        try:
            if path.stat().st_size > MAX_IMAGE_BYTES:
                return "imagem acima de 10 MB"
            read_image_info(path)
        except (ImageError, OSError) as exc:
            return str(exc)
        return ""
    return "" if ext in ALLOWED_FILE_EXTENSIONS else f"tipo de arquivo não aceito ({ext})"


def _media_issues(media: list[dict[str, str]], issues: list[dict[str, str]]) -> None:
    labels = {"missing": "não encontrada", "external": "é um link externo (não é baixado)",
              "ambiguous": "tem mais de um arquivo com esse nome", "invalid": "inválida"}
    for m in media:
        if m["status"] in labels:
            what = "Imagem" if m["kind"] == "image" else "Arquivo"
            note = f" ({m['note']})" if m.get("note") else ""
            issues.append({"severity": "warning", "message": f"{what} {m['ref']} {labels[m['status']]}{note}; fica "
                                                             "registrada como pendente."})


def _allowed_decision(row: ImportRow) -> str | None:
    if row.action is ImportAction.CREATE:
        return "create"
    if row.action is ImportAction.UPDATE:
        return "update"
    if row.action is ImportAction.REVIEW:
        return row.data.get("intended") or None
    return None


_ENUMS = {"condition": Condition, "commercial_status": CommercialStatus}


def _get(product: Product, key: str) -> Any:
    if key.startswith("spec:"):
        return product.specs.get(key[5:])
    if key.startswith("attr:"):
        return product.custom_attributes.get(key[5:])
    value = getattr(product, key)
    return value.value if hasattr(value, "value") else value


def _set(product: Product, key: str, value: Any) -> None:
    if key.startswith("spec:"):
        product.specs[key[5:]] = value
    elif key.startswith("attr:"):
        product.custom_attributes[key[5:]] = value
    elif key in _ENUMS:
        setattr(product, key, _ENUMS[key](value))
    elif hasattr(product, key):
        setattr(product, key, value)


def _diff_product(product: Product, parsed: ParsedRow) -> list[dict[str, Any]]:
    changes = []
    for key, new in parsed.data.items():
        if key in ("sku", "parent_sku", "variant_name") or not hasattr(product, key):
            continue
        old = _get(product, key)
        if new != old:
            changes.append(_change(key, old, new))
    for key, value in parsed.specs.items():
        if product.specs.get(key) != value:
            changes.append(_change(f"spec:{key}", product.specs.get(key), value))
    for key, value in parsed.attributes.items():
        if product.custom_attributes.get(key) != value:
            changes.append(_change(f"attr:{key}", product.custom_attributes.get(key), value))
    if parsed.data.get("description") and not product.original_description:
        changes.append(_change("original_description", "", parsed.data["description"]))
    return changes


def _attach_media(product: Product, media: list[dict[str, str]], stored, origin: str, counts: dict[str, int],
                  variant: str = "") -> int:
    known_images = {i.sha256 for i in product.images}
    known_files = {f.sha256 for f in product.files}
    pending = {_media_name(m.reference) for m in product.missing_media}
    added = 0
    for m in media:
        ref_name = _media_name(m["ref"])
        item = stored.get(m["path"]) if m.get("status") == "found" else None
        if item is not None:
            if m["kind"] == "image" and item.sha256 not in known_images:
                product.images.append(dataclasses.replace(item, original_name=Path(m["ref"]).name, variant=variant,
                                                          id=None, product_id=None, is_main=False))
                known_images.add(item.sha256)
                added += 1
                counts["images"] += 1
            elif m["kind"] == "file" and item.sha256 not in known_files:
                product.files.append(dataclasses.replace(item, original_name=Path(m["ref"]).name, id=None,
                                                         product_id=None))
                known_files.add(item.sha256)
                added += 1
            product.missing_media = [x for x in product.missing_media
                                     if Path(x.reference.replace("\\", "/")).name.lower() != ref_name]
        elif ref_name not in pending:
            # the same file may be cited by name in one import and by full path in another: one pending entry,
            # and never a local absolute path in the product (reports go to clients)
            reference = Path(m["ref"].replace("\\", "/")).name if _local_absolute(m["ref"]) else m["ref"]
            product.missing_media.append(MissingMedia(reference, "image" if m["kind"] == "image" else "file", origin))
            pending.add(ref_name)
            counts["missing_media"] += 1
    return added


def _media_name(reference: str) -> str:
    return Path(reference.replace("\\", "/")).name.lower()


def _local_absolute(reference: str) -> bool:
    text = reference.replace("\\", "/")
    return bool(re.match(r"^[a-zA-Z]:/", text)) or text.startswith("//") or (text.startswith("/") and "://" not in text)


def _commit_message(counts: dict[str, int]) -> str:
    """Short summary for the history list; zero counts are left out (except "criado(s)")."""
    rejected = counts.get("rejected", 0)
    pairs = ((counts["created"], "criado(s)"), (counts["updated"], "atualizado(s)"),
             (rejected, "recusado(s) por erro na análise"), (counts["errors"], "com erro na gravação"),
             (counts.get("skipped", 0) - rejected, "ignorado(s) ou sem mudanças"),
             (counts["images"], "imagem(ns) adicionada(s)"), (counts["missing_media"], "mídia(s) pendente(s)"))
    parts = [f"{n} {text}" for index, (n, text) in enumerate(pairs) if n or index == 0]
    return ", ".join(parts) + "."
