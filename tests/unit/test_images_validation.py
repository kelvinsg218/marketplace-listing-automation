import pytest

from mla.core.enums import Marketplace
from mla.core.models import ProductImage, ProductMarketplaceData, ProductVariant
from mla.core.validation import validate_product
from mla.services.images import ImageError, read_image_info


def test_import_png_reads_dimensions_and_dedupes(ctx, png):
    source = png(640, 480)
    first = ctx.images.import_file(source)
    second = ctx.images.import_file(source)
    assert (first.width, first.height) == (640, 480)
    assert first.filename == second.filename
    assert len(list(ctx.paths.images.iterdir())) == 1


def test_rejects_wrong_extension_and_fake_image(ctx, tmp_path):
    gif = tmp_path / "a.gif"
    gif.write_bytes(b"GIF89a")
    with pytest.raises(ImageError):
        ctx.images.import_file(gif)
    fake = tmp_path / "fake.png"
    fake.write_bytes(b"this is not a png at all, just text" * 3)
    with pytest.raises(ImageError):
        ctx.images.import_file(fake)


def test_jpeg_and_webp_headers(qapp, tmp_path):
    from PySide6.QtGui import QColor, QImage

    image = QImage(1200, 900, QImage.Format.Format_RGB32)
    image.fill(QColor("#7b5cff"))
    for fmt in ("jpg", "webp"):
        target = tmp_path / f"x.{fmt}"
        if not image.save(str(target), fmt.upper()):
            pytest.skip(f"Qt sem plugin {fmt}")
        info = read_image_info(target)
        assert (info.width, info.height) == (1200, 900)


def test_marketplace_title_limit_only_when_enabled(complete_product):
    product = complete_product(title="T" * 80)
    assert validate_product(product).ready_for(Marketplace.SHOPEE)
    product.marketplace_data[Marketplace.MERCADO_LIVRE] = ProductMarketplaceData(Marketplace.MERCADO_LIVRE, enabled=True)
    report = validate_product(product)
    assert not report.ready_for(Marketplace.MERCADO_LIVRE)
    assert not report.catalog_errors()  # catalog itself is fine


def test_shopee_extra_images_are_a_warning(complete_product):
    product = complete_product()
    product.images = [ProductImage(filename=f"{i}.png", width=800, height=800) for i in range(10)]
    product.marketplace_data[Marketplace.SHOPEE] = ProductMarketplaceData(Marketplace.SHOPEE, enabled=True)
    report = validate_product(product)
    assert report.ready_for(Marketplace.SHOPEE)
    assert any("9 imagens" in w.message for w in report.warnings(Marketplace.SHOPEE))


def test_small_image_warns_and_missing_fields_error(complete_product):
    product = complete_product()
    product.images = [ProductImage(filename="a.png", width=300, height=300)]
    product.weight_g = None
    report = validate_product(product)
    assert any("pequena" in w.message for w in report.warnings())
    assert [i.field for i in report.catalog_errors()] == ["weight"]


def test_variant_rules(complete_product):
    product = complete_product(stock=0)
    product.variants = [ProductVariant(name="Azul", stock=0), ProductVariant(name="azul", stock=0)]
    messages = [i.message for i in validate_product(product).catalog_errors()]
    assert any("sem estoque" in m for m in messages)
    assert any("mesmo nome" in m for m in messages)
