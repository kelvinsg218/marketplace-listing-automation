"""CSV and JSON import/export of the catalog.

CSV: ';' separator and UTF-8 with BOM so Excel (pt-BR) opens it correctly.
Prices use Brazilian decimals ("129,90"); dimensions are in centimetres.
JSON: lossless (variants and marketplace data included), integer units.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from mla.core.enums import Condition, Marketplace
from mla.core.models import Product, ProductMarketplaceData, ProductVariant
from mla.core.units import ParseError, format_money, format_scaled, parse_money, parse_scaled
from mla.services.catalog import CatalogError, CatalogService
from mla.services.images import ImageError, ImageStore

log = logging.getLogger(__name__)
Mode = Literal["skip", "update"]

CSV_COLUMNS = [
    "sku", "internal_name", "title", "category", "subcategory", "brand", "model", "condition",
    "description", "features", "material", "package_contents", "warranty", "price", "stock",
    "weight_g", "length_cm", "width_cm", "height_cm", "package_type", "availability_days",
    "shipping_notes", "marketplaces", "images",
]
_TEXT_FIELDS = ["internal_name", "title", "category", "subcategory", "brand", "model", "description",
                "features", "material", "package_contents", "warranty", "package_type", "shipping_notes"]
_JSON_INT_FIELDS = ["price_cents", "stock", "weight_g", "length_mm", "width_mm", "height_mm", "availability_days"]


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        text = f"{self.created} criados, {self.updated} atualizados, {self.skipped} ignorados"
        if self.errors:
            text += f", {len(self.errors)} com erro"
        return text


class ImportExportService:
    def __init__(self, catalog: CatalogService, images: ImageStore):
        self.catalog = catalog
        self.images = images

    # ------------------------------------------------------------------ export
    def _load(self, product_ids: list[int] | None) -> list[Product]:
        ids = product_ids if product_ids is not None else self.catalog.products.all_ids()
        return [p for p in (self.catalog.get(pid) for pid in ids) if p is not None]

    def _copy_images(self, target: Path, products: list[Product]) -> dict[str, str]:
        """Copy images next to the export so it is portable. Returns filename -> relative path."""
        folder = target.parent / f"{target.stem}_imagens"
        mapping: dict[str, str] = {}
        for p in products:
            for image in p.images:
                if image.filename in mapping:
                    continue
                source = self.images.path_for(image.filename)
                if source.exists():
                    folder.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, folder / image.filename)
                    mapping[image.filename] = f"{folder.name}/{image.filename}"
        return mapping

    def export_json(self, target: Path, product_ids: list[int] | None = None) -> int:
        products = self._load(product_ids)
        files = self._copy_images(target, products)
        payload = {
            "format": "mla-catalog",
            "version": 1,
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "products": [self._product_to_dict(p, files) for p in products],
        }
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(products)

    def export_csv(self, target: Path, product_ids: list[int] | None = None) -> int:
        products = self._load(product_ids)
        files = self._copy_images(target, products)
        with target.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, delimiter=";")
            writer.writeheader()
            for p in products:
                row = {name: getattr(p, name) for name in _TEXT_FIELDS}
                row.update(
                    sku=p.sku, condition=p.condition.value, price=format_money(p.price_cents, symbol=False),
                    stock=p.stock, weight_g=p.weight_g if p.weight_g is not None else "",
                    length_cm=format_scaled(p.length_mm, 10), width_cm=format_scaled(p.width_mm, 10),
                    height_cm=format_scaled(p.height_mm, 10),
                    availability_days=p.availability_days if p.availability_days is not None else "",
                    marketplaces=",".join(m.value for m in p.enabled_marketplaces()),
                    images="|".join(files[i.filename] for i in p.images if i.filename in files),
                )
                writer.writerow(row)
        return len(products)

    def _product_to_dict(self, p: Product, files: dict[str, str]) -> dict[str, Any]:
        data: dict[str, Any] = {name: getattr(p, name) for name in _TEXT_FIELDS}
        data.update({name: getattr(p, name) for name in _JSON_INT_FIELDS})
        data["sku"] = p.sku
        data["condition"] = p.condition.value
        data["images"] = [{"file": files[i.filename], "main": i.is_main} for i in p.images if i.filename in files]
        data["variants"] = [{"name": v.name, "attributes": v.attributes, "sku": v.sku,
                             "price_cents": v.price_cents, "stock": v.stock} for v in p.variants]
        data["marketplaces"] = {
            m.value: {"enabled": d.enabled, "price_cents": d.price_cents, "category_id": d.category_id,
                      "listing_type": d.listing_type, "attributes": d.attributes}
            for m, d in p.marketplace_data.items()
        }
        return data

    # ------------------------------------------------------------------ import
    def import_json(self, source: Path, mode: Mode = "skip") -> ImportResult:
        result = ImportResult()
        try:
            payload = json.loads(source.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError) as exc:
            result.errors.append(f"Arquivo JSON inválido: {exc}")
            return result
        rows = payload.get("products") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            result.errors.append("O JSON não contém uma lista de produtos.")
            return result
        for index, row in enumerate(rows, start=1):
            try:
                product = self._dict_to_product(row)
            except (ValueError, TypeError, KeyError) as exc:
                result.errors.append(f"Produto {index}: {exc}")
                continue
            self._store(product, row.get("images", []), mode, result, f"Produto {index}", source.parent)
        return result

    def import_csv(self, source: Path, mode: Mode = "skip") -> ImportResult:
        result = ImportResult()
        try:
            text = source.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = source.read_text(encoding="cp1252")
        delimiter = ";" if text.split("\n", 1)[0].count(";") >= text.split("\n", 1)[0].count(",") else ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        missing = {"sku", "internal_name"} - set(reader.fieldnames or [])
        if missing:
            result.errors.append(f"Colunas obrigatórias ausentes: {', '.join(sorted(missing))}")
            return result
        for line, row in enumerate(reader, start=2):
            try:
                product = self._csv_row_to_product(row)
            except (ValueError, ParseError) as exc:
                result.errors.append(f"Linha {line}: {exc}")
                continue
            images = [{"file": f.strip()} for f in (row.get("images") or "").split("|") if f.strip()]
            self._store(product, images, mode, result, f"Linha {line}", source.parent)
        return result

    def _store(self, product: Product, images: list[dict], mode: Mode, result: ImportResult, where: str,
               base: Path) -> None:
        existing = self.catalog.products.id_for_sku(product.sku.strip())
        if existing and mode == "skip":
            result.skipped += 1
            return
        for spec in images:
            try:
                path = Path(spec["file"])
                image = self.images.import_file(path if path.is_absolute() else base / path)
            except (ImageError, OSError, KeyError) as exc:
                result.errors.append(f"{where}: imagem ignorada ({exc})")
                continue
            image.is_main = bool(spec.get("main"))
            product.images.append(image)
        if existing:
            product.id = existing
        try:
            self.catalog.save(product)
        except CatalogError as exc:
            result.errors.append(f"{where}: {exc}")
            return
        if existing:
            result.updated += 1
        else:
            result.created += 1

    @staticmethod
    def _dict_to_product(row: dict[str, Any]) -> Product:
        if not isinstance(row, dict):
            raise ValueError("registro não é um objeto")
        kwargs: dict[str, Any] = {name: str(row.get(name) or "") for name in _TEXT_FIELDS}
        for name in _JSON_INT_FIELDS:
            value = row.get(name)
            kwargs[name] = int(value) if value not in (None, "") else (0 if name == "stock" else None)
        product = Product(sku=str(row.get("sku") or ""), condition=Condition(row.get("condition") or "new"), **kwargs)
        for v in row.get("variants") or []:
            product.variants.append(ProductVariant(
                name=str(v.get("name") or ""), attributes=dict(v.get("attributes") or {}),
                sku=v.get("sku") or None, price_cents=v.get("price_cents"), stock=int(v.get("stock") or 0)))
        for key, d in (row.get("marketplaces") or {}).items():
            marketplace = Marketplace(key)
            product.marketplace_data[marketplace] = ProductMarketplaceData(
                marketplace=marketplace, enabled=bool(d.get("enabled")), price_cents=d.get("price_cents"),
                category_id=str(d.get("category_id") or ""), listing_type=str(d.get("listing_type") or ""),
                attributes=dict(d.get("attributes") or {}))
        return product

    @staticmethod
    def _csv_row_to_product(row: dict[str, str]) -> Product:
        def text(name: str) -> str:
            return (row.get(name) or "").strip()

        def integer(name: str) -> int | None:
            value = text(name)
            return int(parse_scaled(value, 1)) if value else None

        condition_raw = text("condition").lower() or "new"
        aliases = {"novo": "new", "usado": "used", "recondicionado": "refurbished"}
        product = Product(
            sku=text("sku"), condition=Condition(aliases.get(condition_raw, condition_raw)),
            price_cents=parse_money(text("price")), stock=integer("stock") or 0,
            weight_g=integer("weight_g"), length_mm=parse_scaled(text("length_cm"), 10),
            width_mm=parse_scaled(text("width_cm"), 10), height_mm=parse_scaled(text("height_cm"), 10),
            availability_days=integer("availability_days"),
            **{name: text(name) for name in _TEXT_FIELDS},
        )
        for key in text("marketplaces").replace(";", ",").split(","):
            key = key.strip().lower()
            if key:
                marketplace = Marketplace(key)
                product.marketplace_data[marketplace] = ProductMarketplaceData(marketplace=marketplace, enabled=True)
        return product
