"""Render every page to PNG for visual review (development only).

Seeds SAMPLE data into a throwaway data folder — never into the user's data.

Usage:
    .venv/Scripts/python tools/ui_snapshots.py <output_dir> [--empty]
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def seed(ctx, workdir: Path) -> None:
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter

    from mla.automation.queue import QueueManager
    from mla.core.enums import ItemStatus, Marketplace
    from mla.core.models import Product, ProductGroup, ProductMarketplaceData

    def image(name: str, hue: int) -> Path:
        img = QImage(900, 900, QImage.Format.Format_RGB32)
        painter = QPainter(img)
        grad = QLinearGradient(QPointF(0, 0), QPointF(900, 900))
        grad.setColorAt(0, QColor.fromHsv(hue, 40, 235))
        grad.setColorAt(1, QColor.fromHsv(hue, 90, 160))
        painter.fillRect(img.rect(), grad)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor.fromHsv((hue + 180) % 360, 120, 90))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(250, 260, 400, 420, 40, 40)
        painter.end()
        path = workdir / f"{name}.png"
        img.save(str(path))
        return path

    rows = [
        ("Suporte articulado para monitor", "SUP-MON-27", "Informática", 18990, 12, 20),
        ("Organizador de cabos em silicone", "ORG-CAB-05", "Acessórios", 2990, 140, 140),
        ("Luminária LED de mesa", "LUM-LED-01", "Casa e decoração", 8990, 8, 45),
        ("Vaso geométrico impresso em 3D", "VASO-3D-02", "Casa e decoração", 5490, 25, 300),
        ("Suporte de headset em madeira", "SUP-HEAD-01", "Acessórios", 7900, 6, 30),
        ("Hub USB-C 7 em 1", "HUB-USBC-7", "Informática", 21900, 15, 210),
    ]
    ids = []
    for index, (name, sku, category, price, stock, hue) in enumerate(rows):
        p = Product(internal_name=name, sku=sku, title=name, category=category, brand="Oficina Norte",
                    description=f"{name}. Produto de demonstração para revisão visual da interface do MLA.",
                    price_cents=price, stock=stock, weight_g=600, length_mm=300, width_mm=200, height_mm=120)
        p.images.append(ctx.images.import_file(image(sku, hue)))
        p.marketplace_data[Marketplace.SIMULATED] = ProductMarketplaceData(Marketplace.SIMULATED, enabled=True,
                                                                           attributes={"Modelo": sku})
        if index % 2 == 0:
            p.marketplace_data[Marketplace.MERCADO_LIVRE] = ProductMarketplaceData(Marketplace.MERCADO_LIVRE,
                                                                                   enabled=True)
        ctx.catalog.save(p)
        ids.append(p.id)
    ctx.catalog.save(Product(internal_name="Kit chaveiros personalizados", sku="KIT-CHAV-10",
                             title="Kit 10 chaveiros", price_cents=3500))
    ctx.catalog.save(Product(internal_name="Capa de notebook (rascunho)", sku="CAPA-NB-15"))
    ctx.groups.save(ProductGroup(name="Produtos 3D", product_ids=[ids[3], ids[1]],
                                 marketplaces=[Marketplace.SIMULATED]))
    ctx.groups.save(ProductGroup(name="Escritório", product_ids=[ids[0], ids[2], ids[4], ids[5]],
                                 marketplaces=[Marketplace.SIMULATED, Marketplace.MERCADO_LIVRE]))
    queue = QueueManager(ctx.automation_repo, ctx.products, ctx.accounts)
    queue.enqueue(ids[:5], [Marketplace.SIMULATED], label="Grupo Escritório")
    outcomes = [(ItemStatus.PUBLISHED, "", "SIM-K3J9Q"), (ItemStatus.PUBLISHED, "", "SIM-K3JA2"),
                (ItemStatus.FAILED, "Etapa falhou após 3 tentativas: upload das fotos excedeu 30 s", ""),
                (ItemStatus.PUBLISHED, "", "SIM-K3JB7")]
    for status, error, ext in outcomes:
        item = ctx.automation_repo.next_queued_item()
        ctx.automation_repo.update_item(item.id, started_at="2026-10-12T14:02:10", step="done" if ext else "images")
        queue.finish_item(item, status, error, ext, f"file:///listing.html?id={ext}" if ext else "")
    time.sleep(0.01)


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "snapshots")
    out.mkdir(parents=True, exist_ok=True)
    empty = "--empty" in sys.argv
    data = Path(tempfile.mkdtemp(prefix="mla-snap-"))
    os.environ["MLA_DATA_DIR"] = str(data / "data")

    from PySide6.QtWidgets import QApplication

    from mla.config.paths import AppPaths
    from mla.services.context import AppContext
    from mla.ui.main_window import NAV, MainWindow
    from mla.ui.theme import apply_theme

    app = QApplication(sys.argv[:1])
    apply_theme(app)
    ctx = AppContext.open(AppPaths.default())
    if not empty:
        seed(ctx, data)
    window = MainWindow(ctx, start_executor=False)
    window.resize(1360, 860)
    window.show()

    def settle(ms: int = 900) -> None:
        end = time.time() + ms / 1000
        while time.time() < end:
            app.processEvents()
            time.sleep(0.02)

    suffix = "-empty" if empty else ""
    for key, _, _ in NAV:
        window.navigate(key)
        settle()
        window.grab().save(str(out / f"{key}{suffix}.png"))
    if not empty:
        from mla.ui.pages.product_editor import ProductEditor
        product = ctx.catalog.get(ctx.products.id_for_sku("SUP-MON-27"))
        for tab in (0, 2):
            editor = ProductEditor(ctx, product, window)
            editor.tabs.setCurrentIndex(tab)
            editor.show()
            settle(500)
            editor.grab().save(str(out / f"editor-tab{tab}.png"))
            editor.close()
    window.services.executor.stop(timeout=1)
    ctx.close()
    print(f"capturas em {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
