from __future__ import annotations

import copy
import os
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from mla.core.enums import CatalogStatus, CommercialStatus, Condition, Marketplace, Verification
from mla.core.models import Compatibility, Product, ProductMarketplaceData, ProductVariant
from mla.core.units import ParseError, format_money, parse_money_strict
from mla.core.validation import MARKETPLACE_RULES, derive_status
from mla.services.catalog import CatalogError
from mla.services.compatibility import CompatibilityError
from mla.services.files import FileStoreError
from mla.ui.icons import pixmap
from mla.ui.theme import T
from mla.ui.widgets.common import StatusChip, button, clear_layout, divider, format_when, inform, label, set_prop
from mla.ui.widgets.image_gallery import ImageGallery

LISTING_TYPES = {Marketplace.MERCADO_LIVRE: ["", "Clássico", "Premium"]}
# tabs: 0 Básico, 1 Descrição, 2 Técnico, 3 Imagens, 4 Comercial, 5 Logística, 6 Compatibilidade, 7 Marketplaces
FIELD_TAB = {"internal_name": 0, "sku": 0, "title": 0, "category": 0, "brand": 0, "model": 0, "gtin": 0,
             "manufacturer_code": 0, "commercial_status": 0, "description": 1, "images": 3, "price": 4,
             "promo_price": 4, "stock": 4, "variants": 4, "weight": 5, "dimensions": 5, "compatibility": 6}
TAB_PRICE = 4


def _field(caption: str, widget: QWidget, hint: str = "") -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(5)
    title = QLabel(caption)
    title.setBuddy(widget)
    title.setProperty("role", "muted")
    layout.addWidget(title)
    layout.addWidget(widget)
    if hint:
        layout.addWidget(label(hint, role="hint", wrap=True))
    return box


def _scroll(content: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(content)
    return area


def _form_page() -> tuple[QWidget, QGridLayout]:
    page = QWidget()
    grid = QGridLayout(page)
    grid.setContentsMargins(4, 18, 12, 18)
    grid.setHorizontalSpacing(16)
    grid.setVerticalSpacing(16)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    return page, grid


def _parse_attributes(text: str) -> dict[str, str]:
    result = {}
    for part in text.replace("\n", ";").split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key.strip():
                result[key.strip()] = value.strip()
    return result


def _format_attributes(attrs: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in attrs.items())


class _MarketplaceSection(QFrame):
    def __init__(self, marketplace: Marketplace, on_change):
        super().__init__()
        self.marketplace = marketplace
        self.setObjectName("panel")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 16)
        layout.setSpacing(12)
        self.enabled = QCheckBox(f"Anunciar no {marketplace.label}")
        self.enabled.setStyleSheet("font-weight: 600;")
        layout.addWidget(self.enabled)
        if marketplace is Marketplace.SIMULATED:
            layout.addWidget(label("Marketplace local para testar a automação sem publicar nada de verdade.",
                                   role="hint", wrap=True))
        self.details = QWidget()
        grid = QGridLayout(self.details)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        self.price = QLineEdit()
        self.price.setPlaceholderText("Usar preço padrão")
        grid.addWidget(_field("Preço neste marketplace (R$)", self.price), 0, 0)
        self.category_id = QLineEdit()
        self.category_id.setPlaceholderText("Ex.: código ou caminho da categoria")
        grid.addWidget(_field("Categoria no marketplace", self.category_id), 0, 1)
        if marketplace in LISTING_TYPES:
            self.listing_type = QComboBox()
            self.listing_type.addItems(LISTING_TYPES[marketplace])
            self.listing_type.setItemText(0, "Escolher na hora da revisão")
        else:
            self.listing_type = QLineEdit()
            self.listing_type.setPlaceholderText("Opcional")
        grid.addWidget(_field("Tipo de anúncio", self.listing_type), 1, 0)
        self.attributes = QPlainTextEdit()
        self.attributes.setPlaceholderText("Modelo=X1; Cor=Preto; Voltagem=Bivolt")
        self.attributes.setFixedHeight(64)
        grid.addWidget(_field("Atributos da categoria", self.attributes,
                              "Os atributos obrigatórios variam por categoria e são conferidos no formulário "
                              "do marketplace. Registre aqui os valores que você já conhece."), 1, 1)
        layout.addWidget(self.details)
        self.enabled.toggled.connect(self.details.setEnabled)
        for signal in (self.enabled.toggled, self.price.textChanged, self.category_id.textChanged,
                       self.attributes.textChanged):
            signal.connect(on_change)
        self.details.setEnabled(False)

    def load(self, data: ProductMarketplaceData | None) -> None:
        data = data or ProductMarketplaceData(self.marketplace)
        self.enabled.setChecked(data.enabled)
        self.details.setEnabled(data.enabled)
        self.price.setText(format_money(data.price_cents, symbol=False))
        self.category_id.setText(data.category_id)
        if isinstance(self.listing_type, QComboBox):
            index = self.listing_type.findText(data.listing_type)
            self.listing_type.setCurrentIndex(max(0, index))
        else:
            self.listing_type.setText(data.listing_type)
        self.attributes.setPlainText(_format_attributes(data.attributes))

    def collect(self) -> ProductMarketplaceData:
        if isinstance(self.listing_type, QComboBox):
            listing_type = self.listing_type.currentText() if self.listing_type.currentIndex() > 0 else ""
        else:
            listing_type = self.listing_type.text().strip()
        try:
            price = parse_money_strict(self.price.text())
            set_prop(self.price, "invalid", False)
        except ParseError:
            price = None
            set_prop(self.price, "invalid", True)
        return ProductMarketplaceData(
            marketplace=self.marketplace, enabled=self.enabled.isChecked(), price_cents=price,
            category_id=self.category_id.text().strip(), listing_type=listing_type,
            attributes=_parse_attributes(self.attributes.toPlainText()))


class ProductEditor(QDialog):
    def __init__(self, ctx, product: Product | None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.product = copy.deepcopy(product) if product else Product(internal_name="", sku="")
        self.is_new = product is None
        self.setWindowTitle("Novo produto" if self.is_new else f"Editar {product.internal_name}")
        self.resize(1120, 760)
        self.setMinimumSize(960, 640)
        self._loading = True
        self._money_error = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(28, 22, 0, 0)
        body.setSpacing(0)
        outer.addLayout(body, 1)

        main = QVBoxLayout()
        main.setSpacing(10)
        head = QHBoxLayout()
        self.heading = label("Novo produto" if self.is_new else self.product.internal_name, object_name="pageTitle")
        head.addWidget(self.heading, 1)
        self.chip = StatusChip(CatalogStatus.DRAFT)
        head.addWidget(self.chip)
        main.addLayout(head)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        main.addWidget(self.tabs, 1)
        body.addLayout(main, 1)

        self._build_basic()
        self._build_description()
        self._build_technical()
        self._build_images()
        self._build_commercial()
        self._build_logistics()
        self._build_compatibility()
        self._build_marketplaces()
        if not self.is_new:
            self._build_history()

        body.addSpacing(24)
        body.addWidget(self._build_side())

        footer = QFrame()
        footer.setObjectName("editorFooter")
        footer.setStyleSheet(f"QFrame#editorFooter {{ background: {T.surface}; border-top: 1px solid {T.line}; }}")
        foot = QHBoxLayout(footer)
        foot.setContentsMargins(28, 12, 28, 12)
        self.footer_hint = label("Você pode salvar um produto incompleto e terminar depois.", role="hint")
        foot.addWidget(self.footer_hint, 1)
        foot.addWidget(button("Cancelar", "ghost", None, self.reject))
        self.save_btn = button("Salvar produto", "primary", "check", self._save)
        self.save_btn.setDefault(True)
        foot.addWidget(self.save_btn)
        outer.addWidget(footer)
        QShortcut(QKeySequence("Ctrl+S"), self, activated=self._save)

        self._load()
        self._loading = False
        self._revalidate_timer = QTimer(self, singleShot=True, interval=200, timeout=self._revalidate)
        self._revalidate()

    # ------------------------------------------------------------------ tabs
    def _build_basic(self) -> None:
        page, grid = _form_page()
        self.internal_name = QLineEdit()
        self.internal_name.setPlaceholderText("Como você identifica o produto no dia a dia")
        grid.addWidget(_field("Nome interno *", self.internal_name), 0, 0)
        self.sku = QLineEdit()
        self.sku.setPlaceholderText("Ex.: SUP-MON-001")
        grid.addWidget(_field("SKU *", self.sku, "Código único do produto, sem espaços."), 0, 1)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Título que o comprador verá no anúncio")
        self.title_counter = label("", role="hint")
        title_box = _field("Título do anúncio", self.title_edit)
        title_box.layout().addWidget(self.title_counter)
        grid.addWidget(title_box, 1, 0, 1, 2)
        self.commercial_name = QLineEdit()
        self.commercial_name.setPlaceholderText("Nome usado na loja ou no catálogo do fornecedor")
        grid.addWidget(_field("Nome comercial", self.commercial_name), 2, 0)
        self.commercial_status = QComboBox()
        for status in CommercialStatus:
            self.commercial_status.addItem(status.label, status)
        grid.addWidget(_field("Situação comercial", self.commercial_status), 2, 1)
        self.category = QLineEdit()
        grid.addWidget(_field("Categoria", self.category), 3, 0)
        self.subcategory = QLineEdit()
        grid.addWidget(_field("Subcategoria", self.subcategory), 3, 1)
        self.brand = QLineEdit()
        grid.addWidget(_field("Marca", self.brand), 4, 0)
        self.model = QLineEdit()
        grid.addWidget(_field("Modelo", self.model), 4, 1)
        self.manufacturer_code = QLineEdit()
        self.manufacturer_code.setPlaceholderText("Part number / código do fabricante")
        grid.addWidget(_field("Código do fabricante", self.manufacturer_code), 5, 0)
        self.gtin = QLineEdit()
        self.gtin.setPlaceholderText("EAN/GTIN com 8, 12, 13 ou 14 dígitos")
        grid.addWidget(_field("GTIN/EAN", self.gtin, "Opcional; o dígito verificador é conferido."), 5, 1)
        self.supplier = QLineEdit()
        grid.addWidget(_field("Fornecedor", self.supplier), 6, 0)
        self.condition = QComboBox()
        for condition in Condition:
            self.condition.addItem(condition.label, condition)
        grid.addWidget(_field("Condição", self.condition), 6, 1)
        grid.setRowStretch(7, 1)
        self.tabs.addTab(_scroll(page), "Básico")

    def _build_description(self) -> None:
        page, grid = _form_page()
        self.description = QPlainTextEdit()
        self.description.setMinimumHeight(180)
        self.description.setPlaceholderText("Descreva o produto: para que serve, diferenciais, como usar.")
        grid.addWidget(_field("Descrição completa", self.description), 0, 0, 1, 2)
        self.features = QPlainTextEdit()
        self.features.setFixedHeight(96)
        self.features.setPlaceholderText("Uma característica por linha")
        grid.addWidget(_field("Características", self.features), 1, 0, 1, 2)
        self.material = QLineEdit()
        grid.addWidget(_field("Material", self.material), 2, 0)
        self.warranty = QLineEdit()
        self.warranty.setPlaceholderText("Ex.: 90 dias contra defeitos de fabricação")
        grid.addWidget(_field("Garantia", self.warranty), 2, 1)
        self.package_contents = QPlainTextEdit()
        self.package_contents.setFixedHeight(72)
        self.package_contents.setPlaceholderText("Ex.: 1 suporte, 4 parafusos, manual")
        grid.addWidget(_field("Conteúdo da embalagem", self.package_contents), 3, 0, 1, 2)
        grid.setRowStretch(4, 1)
        self.tabs.addTab(_scroll(page), "Descrição")

    def _build_images(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 18, 12, 18)
        self.gallery = ImageGallery(self.ctx.images)
        layout.addWidget(self.gallery, 1)
        self.gallery.changed.connect(self._schedule)
        extras = QHBoxLayout()
        extras.setSpacing(16)
        files_box = QVBoxLayout()
        files_box.addWidget(label("Arquivos técnicos", object_name="sectionTitle"))
        self.files_list = QListWidget()
        self.files_list.setMaximumHeight(110)
        self.files_list.itemDoubleClicked.connect(self._open_file)
        files_box.addWidget(self.files_list)
        files_row = QHBoxLayout()
        files_row.addWidget(button("Anexar arquivo…", "ghost", "plus", self._add_files))
        files_row.addWidget(button("Remover", "ghost", "trash-2", self._remove_file))
        files_row.addStretch(1)
        files_box.addLayout(files_row)
        extras.addLayout(files_box, 1)
        pending_box = QVBoxLayout()
        pending_box.addWidget(label("Mídias pendentes", object_name="sectionTitle"))
        self.pending_list = QListWidget()
        self.pending_list.setMaximumHeight(110)
        self.pending_list.setToolTip("Citadas na importação e não encontradas. Importe as fotos (pasta ou ZIP) "
                                     "com o mesmo nome para ligar automaticamente.")
        pending_box.addWidget(self.pending_list)
        pending_row = QHBoxLayout()
        pending_row.addWidget(button("Dispensar selecionada", "ghost", "x", self._dismiss_pending))
        pending_row.addStretch(1)
        pending_box.addLayout(pending_row)
        extras.addLayout(pending_box, 1)
        layout.addLayout(extras)
        self.tabs.addTab(page, "Imagens")

    def _build_technical(self) -> None:
        page, grid = _form_page()
        self.technical_description = QPlainTextEdit()
        self.technical_description.setMinimumHeight(110)
        self.technical_description.setPlaceholderText("Ficha técnica: medidas, normas, composição, aplicação.")
        grid.addWidget(_field("Descrição técnica", self.technical_description), 0, 0, 1, 2)
        self.color = QLineEdit()
        grid.addWidget(_field("Cor", self.color), 1, 0)
        self.manufacturer_refs = QLineEdit()
        self.manufacturer_refs.setPlaceholderText("Códigos equivalentes ou de referência do fabricante")
        grid.addWidget(_field("Referências de fabricante", self.manufacturer_refs), 1, 1)
        self.specs = _kv_table("Especificação", "Valor")
        grid.addWidget(_field("Especificações adicionais", self.specs, "Uma por linha (ex.: Voltagem = 12 V)."), 2, 0)
        self.custom_attributes = _kv_table("Atributo", "Valor")
        grid.addWidget(_field("Atributos personalizados", self.custom_attributes,
                              "Dados próprios da empresa (ex.: Linha = Premium)."), 2, 1)
        kv_row = QHBoxLayout()
        kv_row.addWidget(button("Adicionar especificação", "ghost", "plus", lambda: _kv_add(self.specs)))
        kv_row.addWidget(button("Adicionar atributo", "ghost", "plus", lambda: _kv_add(self.custom_attributes)))
        kv_row.addStretch(1)
        kv_holder = QWidget()
        kv_holder.setLayout(kv_row)
        kv_row.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(kv_holder, 3, 0, 1, 2)
        self.internal_notes = QPlainTextEdit()
        self.internal_notes.setFixedHeight(70)
        self.internal_notes.setPlaceholderText("Não aparecem em anúncios.")
        grid.addWidget(_field("Observações internas", self.internal_notes), 4, 0, 1, 2)
        self.original_description = QPlainTextEdit()
        self.original_description.setReadOnly(True)
        self.original_description.setFixedHeight(70)
        self.original_box = _field("Descrição original (como veio da base do cliente)", self.original_description)
        grid.addWidget(self.original_box, 5, 0, 1, 2)
        self.source_label = label("", role="hint")
        grid.addWidget(self.source_label, 6, 0, 1, 2)
        grid.setRowStretch(7, 1)
        self.tabs.addTab(_scroll(page), "Técnico")

    def _build_compatibility(self) -> None:
        from mla.ui.pages.compatibility import compat_table
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 18, 12, 18)
        layout.setSpacing(10)
        layout.addWidget(label("Veículos, aparelhos ou equipamentos com que este produto funciona. Cadastre só "
                               "informações com fonte; fontes externas ficam como não verificadas.",
                               role="muted", wrap=True))
        self.compat_table = compat_table(["Marca", "Modelo", "Versão", "Anos", "Referência", "Origem",
                                          "Verificação"])
        compat_header = self.compat_table.horizontalHeader()
        compat_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col, width in ((0, 90), (2, 80), (3, 110), (4, 90), (5, 140), (6, 150)):
            compat_header.resizeSection(col, width)
        self.compat_table.doubleClicked.connect(lambda _i: self._edit_compat())
        layout.addWidget(self.compat_table, 1)
        row = QHBoxLayout()
        row.addWidget(button("Adicionar compatibilidade", "secondary", "plus", self._add_compat))
        row.addWidget(button("Editar", "ghost", "pencil", self._edit_compat))
        row.addWidget(button("Confirmar", "ghost", "badge-check", self._confirm_compat))
        row.addWidget(button("Remover", "ghost", "trash-2", self._remove_compat))
        row.addStretch(1)
        layout.addLayout(row)
        self.tabs.addTab(page, "Compatibilidade")

    def _build_history(self) -> None:
        """Read-only list of every recorded field change: when, what, before, after and where it came from."""
        from mla.ui.pages.compatibility import compat_table
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 18, 12, 18)
        layout.setSpacing(10)
        layout.addWidget(label("Alterações gravadas neste produto, da mais recente para a mais antiga, com a origem "
                               "(edição manual, importação ou edição em lote).", role="muted", wrap=True))
        table = compat_table(["Quando", "Campo", "Antes", "Depois", "Origem"])
        header = table.horizontalHeader()
        for col, width in ((0, 105), (1, 160), (2, 150), (3, 150)):
            header.resizeSection(col, width)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        records = self.ctx.catalog.history(self.product.id)
        table.setRowCount(len(records))
        for r, record in enumerate(records):
            for c, text in enumerate((format_when(record.created_at), record.label, record.old or "(vazio)",
                                      record.new or "(vazio)", record.source)):
                item = QTableWidgetItem(text.replace("\n", " "))
                item.setToolTip(text if len(text) > 30 else "")
                table.setItem(r, c, item)
        layout.addWidget(table, 1)
        if not records:
            layout.addWidget(label("Nenhuma alteração registrada ainda (o histórico começa nesta versão do MLA).",
                                   role="hint"))
        self.tabs.addTab(page, "Histórico")

    def _build_commercial(self) -> None:
        page, grid = _form_page()
        self.price = QLineEdit()
        self.price.setPlaceholderText("0,00")
        grid.addWidget(_field("Preço de venda (R$)", self.price), 0, 0)
        self.stock = QSpinBox()
        self.stock.setRange(0, 1_000_000)
        self.stock.setGroupSeparatorShown(True)
        grid.addWidget(_field("Estoque", self.stock, "Com variações, o estoque é a soma das variações."), 0, 1)
        self.cost = QLineEdit()
        self.cost.setPlaceholderText("0,00")
        grid.addWidget(_field("Preço de custo (R$)", self.cost), 1, 0)
        self.promo_price = QLineEdit()
        self.promo_price.setPlaceholderText("Opcional")
        grid.addWidget(_field("Preço promocional (R$)", self.promo_price), 1, 1)
        self.min_stock = QSpinBox()
        self.min_stock.setRange(-1, 1_000_000)
        self.min_stock.setSpecialValueText("Não informado")
        grid.addWidget(_field("Estoque mínimo", self.min_stock), 2, 0)
        self.unit = QLineEdit()
        self.unit.setPlaceholderText("Ex.: un, par, kit, cx, m")
        grid.addWidget(_field("Unidade de medida", self.unit), 2, 1)
        grid.addWidget(label("Variações", object_name="sectionTitle"), 3, 0)
        self.variants = QTableWidget(0, 5)
        self.variants.setHorizontalHeaderLabels(["Nome", "Atributos (Chave=Valor; …)", "SKU", "Preço (R$)", "Estoque"])
        self.variants.verticalHeader().setVisible(False)
        self.variants.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.variants.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col, width in ((0, 150), (2, 130), (3, 100), (4, 80)):
            header.resizeSection(col, width)
        self.variants.setMinimumHeight(180)
        self.variants.itemChanged.connect(self._schedule)
        grid.addWidget(self.variants, 4, 0, 1, 2)
        row = QHBoxLayout()
        row.addWidget(button("Adicionar variação", "secondary", "plus", self._add_variant))
        row.addWidget(button("Remover selecionadas", "ghost", "trash-2", self._remove_variants))
        row.addStretch(1)
        holder = QWidget()
        holder.setLayout(row)
        grid.addWidget(holder, 5, 0, 1, 2)
        grid.setRowStretch(6, 1)
        self.tabs.addTab(_scroll(page), "Comercial")

    def _build_logistics(self) -> None:
        page, grid = _form_page()
        self.weight = QSpinBox()
        self.weight.setRange(0, 1_000_000)
        self.weight.setSuffix(" g")
        self.weight.setSpecialValueText("Não informado")
        grid.addWidget(_field("Peso com embalagem", self.weight), 0, 0)
        self.availability = QSpinBox()
        self.availability.setRange(-1, 365)
        self.availability.setSpecialValueText("Não informado")
        self.availability.setSuffix(" dias")
        grid.addWidget(_field("Prazo de disponibilidade", self.availability,
                              "Dias para postar após a venda (0 = pronta entrega)."), 0, 1)
        dims = QHBoxLayout()
        self.length, self.width, self.height = QDoubleSpinBox(), QDoubleSpinBox(), QDoubleSpinBox()
        for caption, spin in (("Comprimento", self.length), ("Largura", self.width), ("Altura", self.height)):
            spin.setRange(0, 10_000)
            spin.setDecimals(1)
            spin.setSuffix(" cm")
            spin.setSpecialValueText("—")
            dims.addWidget(_field(caption, spin))
        holder = QWidget()
        holder.setLayout(dims)
        dims.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(holder, 1, 0, 1, 2)
        self.package_type = QLineEdit()
        self.package_type.setPlaceholderText("Ex.: caixa de papelão, envelope")
        grid.addWidget(_field("Embalagem", self.package_type), 2, 0)
        self.shipping_notes = QPlainTextEdit()
        self.shipping_notes.setFixedHeight(80)
        grid.addWidget(_field("Informações de envio", self.shipping_notes), 3, 0, 1, 2)
        grid.setRowStretch(4, 1)
        self.tabs.addTab(_scroll(page), "Logística")

    def _build_marketplaces(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 18, 12, 18)
        layout.setSpacing(14)
        self.sections: dict[Marketplace, _MarketplaceSection] = {}
        for marketplace in (Marketplace.MERCADO_LIVRE, Marketplace.SHOPEE, Marketplace.SIMULATED):
            section = _MarketplaceSection(marketplace, self._schedule)
            self.sections[marketplace] = section
            layout.addWidget(section)
        layout.addStretch(1)
        self.tabs.addTab(_scroll(page), "Marketplaces")

    def _build_side(self) -> QWidget:
        side = QFrame()
        side.setFixedWidth(320)
        side.setStyleSheet(f"QFrame#side {{ background: {T.surface}; border-left: 1px solid {T.line}; }}")
        side.setObjectName("side")
        layout = QVBoxLayout(side)
        layout.setContentsMargins(20, 22, 20, 20)
        layout.setSpacing(10)
        layout.addWidget(label("Checagem do anúncio", object_name="sectionTitle"))
        self.side_summary = label("", role="muted", wrap=True)
        layout.addWidget(self.side_summary)
        layout.addWidget(divider())
        self.issue_box = QVBoxLayout()
        self.issue_box.setSpacing(8)
        issues = QWidget()
        issues.setLayout(self.issue_box)
        layout.addWidget(_scroll(issues), 1)
        layout.addWidget(divider())
        layout.addWidget(label("Por marketplace", role="muted"))
        self.market_box = QVBoxLayout()
        self.market_box.setSpacing(6)
        layout.addLayout(self.market_box)
        return side

    # ------------------------------------------------------------------ data in/out
    def _load(self) -> None:
        p = self.product
        self.internal_name.setText(p.internal_name)
        self.sku.setText(p.sku)
        self.title_edit.setText(p.title)
        self.category.setText(p.category)
        self.subcategory.setText(p.subcategory)
        self.brand.setText(p.brand)
        self.model.setText(p.model)
        self.condition.setCurrentIndex(self.condition.findData(p.condition))
        self.commercial_name.setText(p.commercial_name)
        self.commercial_status.setCurrentIndex(self.commercial_status.findData(p.commercial_status))
        self.manufacturer_code.setText(p.manufacturer_code)
        self.gtin.setText(p.gtin)
        self.supplier.setText(p.supplier)
        self.cost.setText(format_money(p.cost_cents, symbol=False))
        self.promo_price.setText(format_money(p.promo_price_cents, symbol=False))
        self.min_stock.setValue(-1 if p.min_stock is None else p.min_stock)
        self.unit.setText(p.unit)
        self.technical_description.setPlainText(p.technical_description)
        self.color.setText(p.color)
        self.manufacturer_refs.setText(p.manufacturer_refs)
        _kv_fill(self.specs, p.specs)
        _kv_fill(self.custom_attributes, p.custom_attributes)
        self.internal_notes.setPlainText(p.internal_notes)
        self.original_description.setPlainText(p.original_description)
        self.original_box.setVisible(bool(p.original_description))
        self.source_label.setText(f"Origem do cadastro: {p.source}" if p.source else "")
        self._fill_files()
        self.compat_items = self.ctx.compatibility.list_for_product(p.id) if p.id else []
        self._fill_compat()
        self.description.setPlainText(p.description)
        self.features.setPlainText(p.features)
        self.material.setText(p.material)
        self.warranty.setText(p.warranty)
        self.package_contents.setPlainText(p.package_contents)
        self.gallery.set_images(p.images)
        self.price.setText(format_money(p.price_cents, symbol=False))
        self.stock.setValue(p.stock)
        for variant in p.variants:
            self._add_variant(variant)
        self.weight.setValue(p.weight_g or 0)
        self.availability.setValue(-1 if p.availability_days is None else p.availability_days)
        self.length.setValue((p.length_mm or 0) / 10)
        self.width.setValue((p.width_mm or 0) / 10)
        self.height.setValue((p.height_mm or 0) / 10)
        self.package_type.setText(p.package_type)
        self.shipping_notes.setPlainText(p.shipping_notes)
        for marketplace, section in self.sections.items():
            section.load(p.marketplace_data.get(marketplace))
        for widget in (self.internal_name, self.sku, self.title_edit, self.category, self.subcategory, self.brand,
                       self.model, self.material, self.warranty, self.price, self.package_type, self.gtin, self.cost,
                       self.promo_price, self.commercial_name, self.manufacturer_code, self.supplier, self.unit,
                       self.color, self.manufacturer_refs):
            widget.textChanged.connect(self._schedule)
        self.commercial_status.currentIndexChanged.connect(self._schedule)
        self.min_stock.valueChanged.connect(self._schedule)
        self.technical_description.textChanged.connect(self._schedule)
        for widget in (self.description, self.features, self.package_contents, self.shipping_notes):
            widget.textChanged.connect(self._schedule)
        for widget in (self.stock, self.weight, self.availability):
            widget.valueChanged.connect(self._schedule)
        for widget in (self.length, self.width, self.height):
            widget.valueChanged.connect(self._schedule)
        self.condition.currentIndexChanged.connect(self._schedule)

    def _collect(self) -> Product:
        p = self.product
        p.internal_name = self.internal_name.text()
        p.sku = self.sku.text().strip()
        p.title = self.title_edit.text()
        p.category = self.category.text().strip()
        p.subcategory = self.subcategory.text().strip()
        p.brand = self.brand.text().strip()
        p.model = self.model.text().strip()
        p.condition = Condition(self.condition.currentData())
        p.commercial_name = self.commercial_name.text().strip()
        p.commercial_status = CommercialStatus(self.commercial_status.currentData())
        p.manufacturer_code = self.manufacturer_code.text().strip()
        p.gtin = self.gtin.text().strip()
        p.supplier = self.supplier.text().strip()
        p.unit = self.unit.text().strip()
        p.min_stock = None if self.min_stock.value() < 0 else self.min_stock.value()
        p.technical_description = self.technical_description.toPlainText()
        p.color = self.color.text().strip()
        p.manufacturer_refs = self.manufacturer_refs.text().strip()
        p.specs = _kv_collect(self.specs)
        p.custom_attributes = _kv_collect(self.custom_attributes)
        p.internal_notes = self.internal_notes.toPlainText()
        p.description = self.description.toPlainText()
        p.features = self.features.toPlainText()
        p.material = self.material.text().strip()
        p.warranty = self.warranty.text().strip()
        p.package_contents = self.package_contents.toPlainText()
        p.images = self.gallery.images()
        self._money_error = False
        for widget, attr in ((self.price, "price_cents"), (self.cost, "cost_cents"),
                             (self.promo_price, "promo_price_cents")):
            try:
                setattr(p, attr, parse_money_strict(widget.text()))
                set_prop(widget, "invalid", False)
            except ParseError:
                setattr(p, attr, None)
                self._money_error = True
                set_prop(widget, "invalid", True)
        p.stock = self.stock.value()
        p.variants = self._collect_variants()
        if p.variants:
            p.stock = sum(v.stock for v in p.variants)
        p.weight_g = self.weight.value() or None
        p.availability_days = None if self.availability.value() < 0 else self.availability.value()
        p.length_mm = round(self.length.value() * 10) or None
        p.width_mm = round(self.width.value() * 10) or None
        p.height_mm = round(self.height.value() * 10) or None
        p.package_type = self.package_type.text().strip()
        p.shipping_notes = self.shipping_notes.toPlainText()
        p.marketplace_data = {m: s.collect() for m, s in self.sections.items()}
        return p

    # ------------------------------------------------------------------ variants
    def _add_variant(self, variant: ProductVariant | None = None) -> None:
        variant = variant if isinstance(variant, ProductVariant) else ProductVariant(name="")
        self.variants.blockSignals(True)
        row = self.variants.rowCount()
        self.variants.insertRow(row)
        values = [variant.name, _format_attributes(variant.attributes), variant.sku or "",
                  format_money(variant.price_cents, symbol=False), str(variant.stock)]
        for col, value in enumerate(values):
            self.variants.setItem(row, col, QTableWidgetItem(value))
        self.variants.blockSignals(False)
        self._schedule()

    def _remove_variants(self) -> None:
        for row in sorted({i.row() for i in self.variants.selectedIndexes()}, reverse=True):
            self.variants.removeRow(row)
        self._schedule()

    def _collect_variants(self) -> list[ProductVariant]:
        result = []
        for row in range(self.variants.rowCount()):
            cell = lambda c: (self.variants.item(row, c).text().strip() if self.variants.item(row, c) else "")
            if not any(cell(c) for c in range(5)):
                continue
            try:
                price = parse_money_strict(cell(3))
            except ParseError:
                price = None
                self._money_error = True
            stock_text = cell(4)
            result.append(ProductVariant(
                name=cell(0), attributes=_parse_attributes(cell(1)), sku=cell(2) or None, price_cents=price,
                stock=int(stock_text) if stock_text.isdigit() else 0))
        return result

    # ------------------------------------------------------------------ validation
    def _schedule(self, *_args) -> None:
        if not self._loading:
            self._revalidate_timer.start()

    def _revalidate(self) -> None:
        product = self._collect()
        report = self.ctx.catalog.validate(product)
        status = derive_status(product, report)
        self.chip.set_status(status)
        limits = [(m, MARKETPLACE_RULES[m].max_title) for m in product.enabled_marketplaces()
                  if MARKETPLACE_RULES[m].max_title]
        length = len(product.title.strip())
        if limits:
            strictest = min(limits, key=lambda x: x[1])
            over = length > strictest[1]
            self.title_counter.setText(f"{length}/{strictest[1]} caracteres (limite do {strictest[0].label})")
            self.title_counter.setStyleSheet(f"color: {T.danger if over else T.text_3};")
        else:
            self.title_counter.setText(f"{length} caracteres")
            self.title_counter.setStyleSheet("")
        for widget, fields in ((self.internal_name, "internal_name"), (self.sku, "sku"), (self.title_edit, "title")):
            set_prop(widget, "invalid", any(i.severity == "error" for i in report.for_field(fields))
                     and bool(widget.text()))
        self._fill_side(report, product, status)

    def _fill_side(self, report, product, status) -> None:
        clear_layout(self.issue_box)
        errors = report.catalog_errors()
        warnings = report.warnings()
        if self._money_error:
            errors = [*errors]
            self.issue_box.addWidget(self._issue_row("Valor em reais em formato inválido. Use, por exemplo, 129,90.",
                                                     "error", "price"))
        if status is CatalogStatus.READY:
            self.side_summary.setText("Cadastro completo. No Catálogo, use Preparar anúncios para escolher o "
                                      "marketplace e a conta.")
        else:
            self.side_summary.setText(f"{len(errors)} item(ns) para completar antes de anunciar.")
        for issue in errors:
            self.issue_box.addWidget(self._issue_row(issue.message, "error", issue.field))
        for issue in warnings:
            prefix = f"{issue.marketplace.label}: " if issue.marketplace else ""
            self.issue_box.addWidget(self._issue_row(prefix + issue.message, "warning", issue.field))
        if not errors and not warnings and not self._money_error:
            self.issue_box.addWidget(self._issue_row("Nenhuma pendência no cadastro.", "ok", ""))
        self.issue_box.addStretch(1)
        clear_layout(self.market_box)
        enabled = product.enabled_marketplaces()
        if not enabled:
            self.market_box.addWidget(label("Nenhum marketplace ativado (aba Marketplaces).", role="hint", wrap=True))
        for marketplace in enabled:
            ok = report.ready_for(marketplace)
            row = QHBoxLayout()
            row.addWidget(label(marketplace.label), 1)
            mp_errors = [i for i in report.errors(marketplace) if i.marketplace]
            chip = StatusChip(text="Pronto" if ok else (mp_errors[0].message[:28] + "…" if mp_errors else "Pendente"),
                              tone="success" if ok else "warning")
            if mp_errors:
                chip.setToolTip("\n".join(i.message for i in mp_errors))
            row.addWidget(chip)
            self.market_box.addLayout(row)

    def _issue_row(self, text: str, severity: str, field: str) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        glyph = QLabel()
        name, color = {"error": ("circle-x", T.danger), "warning": ("triangle-alert", T.warning),
                       "ok": ("circle-check", T.success)}[severity]
        glyph.setPixmap(pixmap(name, color, 16))
        glyph.setFixedWidth(18)
        glyph.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(glyph, 0, Qt.AlignmentFlag.AlignTop)
        text_label = label(text, wrap=True)
        text_label.setCursor(Qt.CursorShape.PointingHandCursor)
        tab = FIELD_TAB.get(field)
        if tab is not None:
            text_label.mousePressEvent = lambda _e, t=tab: self.tabs.setCurrentIndex(t)
            text_label.setToolTip("Ir para o campo")
        layout.addWidget(text_label, 1)
        return row

    # ------------------------------------------------------------------ save
    def _save(self) -> None:
        product = self._collect()
        if self._money_error:
            self.tabs.setCurrentIndex(TAB_PRICE)
            self.price.setFocus()
            return
        try:
            self.ctx.catalog.save(product)
        except CatalogError as exc:
            inform(self, "Não foi possível salvar", str(exc), error=True)
            self.tabs.setCurrentIndex(0)
            return
        try:
            self.ctx.compatibility.replace_for_product(product.id, self.compat_items)
        except CompatibilityError as exc:
            inform(self, "Produto salvo, compatibilidades não", f"O produto foi salvo, mas as compatibilidades "
                   f"não: {exc}", error=True)
            self.tabs.setCurrentIndex(FIELD_TAB["compatibility"])
            return
        self.accept()

    # ------------------------------------------------------------------ files and pending media
    def _fill_files(self) -> None:
        self.files_list.clear()
        for item in self.product.files:
            entry = QListWidgetItem(item.original_name or item.filename)
            entry.setToolTip("Clique duas vezes para abrir")
            self.files_list.addItem(entry)
        self.pending_list.clear()
        for missing in self.product.missing_media:
            self.pending_list.addItem(QListWidgetItem(f"{missing.reference}   {missing.origin}".strip()))

    def _add_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Anexar arquivos técnicos", "",
                                                "Documentos (*.pdf *.txt *.csv *.xlsx *.docx *.dwg *.dxf *.step *.stp);;"
                                                "Todos os arquivos (*.*)")
        for path in paths:
            try:
                stored = self.ctx.files.import_file(Path(path))
            except FileStoreError as exc:
                inform(self, "Arquivo não anexado", str(exc), error=True)
                continue
            if stored.sha256 not in {f.sha256 for f in self.product.files}:
                self.product.files.append(stored)
        self._fill_files()

    def _remove_file(self) -> None:
        row = self.files_list.currentRow()
        if 0 <= row < len(self.product.files):
            del self.product.files[row]
            self._fill_files()

    def _open_file(self, _item=None) -> None:
        row = self.files_list.currentRow()
        if 0 <= row < len(self.product.files):
            path = self.ctx.files.path_for(self.product.files[row].filename)
            if path.exists() and path.suffix.lower() in (".pdf", ".txt", ".csv", ".xlsx", ".docx", ".jpg", ".png"):
                os.startfile(path)  # opened by the user's default program; MLA never runs files itself

    def _dismiss_pending(self) -> None:
        row = self.pending_list.currentRow()
        if 0 <= row < len(self.product.missing_media):
            del self.product.missing_media[row]
            self._fill_files()
            self._schedule()

    # ------------------------------------------------------------------ compatibility (saved with the product)
    def _fill_compat(self) -> None:
        from mla.ui.pages.compatibility import fill_compat_row
        self.compat_table.setRowCount(len(self.compat_items))
        for row, item in enumerate(self.compat_items):
            fill_compat_row(self.compat_table, row, item, with_product=False)
        self.tabs.setTabText(FIELD_TAB["compatibility"], f"Compatibilidade ({len(self.compat_items)})"
                             if self.compat_items else "Compatibilidade")

    def _compat_row(self) -> int:
        rows = self.compat_table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def _add_compat(self) -> None:
        from mla.ui.pages.compatibility import CompatibilityDialog
        dialog = CompatibilityDialog(self.ctx, Compatibility(self.product.id, "", verification=Verification.CONFIRMED,
                                                             sku=self.sku.text(),
                                                             product_name=self.internal_name.text()), parent=self)
        if dialog.exec():
            self.compat_items.append(dialog.collect())
            self._fill_compat()

    def _edit_compat(self) -> None:
        from mla.ui.pages.compatibility import CompatibilityDialog
        row = self._compat_row()
        if row < 0:
            return
        dialog = CompatibilityDialog(self.ctx, copy.deepcopy(self.compat_items[row]), parent=self)
        if dialog.exec():
            self.compat_items[row] = dialog.collect()
            self._fill_compat()

    def _confirm_compat(self) -> None:
        for index in self.compat_table.selectionModel().selectedRows():
            self.compat_items[index.row()].verification = Verification.CONFIRMED
        self._fill_compat()

    def _remove_compat(self) -> None:
        for row in sorted({i.row() for i in self.compat_table.selectionModel().selectedRows()}, reverse=True):
            del self.compat_items[row]
        self._fill_compat()


def _kv_table(key_caption: str, value_caption: str) -> QTableWidget:
    table = QTableWidget(0, 2)
    table.setHorizontalHeaderLabels([key_caption, value_caption])
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().resizeSection(0, 150)
    table.setMinimumHeight(150)
    return table


def _kv_add(table: QTableWidget, key: str = "", value: str = "") -> None:
    row = table.rowCount()
    table.insertRow(row)
    table.setItem(row, 0, QTableWidgetItem(key))
    table.setItem(row, 1, QTableWidgetItem(value))


def _kv_fill(table: QTableWidget, data: dict[str, str]) -> None:
    table.setRowCount(0)
    for key, value in data.items():
        _kv_add(table, key, value)


def _kv_collect(table: QTableWidget) -> dict[str, str]:
    result = {}
    for row in range(table.rowCount()):
        key = table.item(row, 0).text().strip() if table.item(row, 0) else ""
        value = table.item(row, 1).text().strip() if table.item(row, 1) else ""
        if key and value:
            result[key] = value
    return result
