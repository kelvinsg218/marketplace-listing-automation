from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout, QWidget

from mla.core.enums import CatalogStatus, ItemStatus, ListingStatus, Marketplace
from mla.ui.pages.base import Page
from mla.ui.theme import T
from mla.ui.widgets.common import Panel, StatusChip, button, clear_layout, divider, format_when, label, plural
from mla.ui.widgets.pipeline import PipelineRail, Stage

_DAYS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


class DashboardPage(Page):
    key = "dashboard"
    title = "Visão geral"

    def __init__(self, ctx, navigate, parent=None):
        super().__init__(ctx, navigate, parent)
        self.header.add_action(button("Novo grupo", "secondary", "layers",
                                      lambda: self.navigate("groups", new=True)))
        self.header.add_action(button("Executar fila", "secondary", "play",
                                      lambda: self.navigate("automations")))
        self.header.add_action(button("Novo produto", "primary", "plus",
                                      lambda: self.navigate("products", new=True)))

        rail_panel = Panel(margins=20)
        self.rail = PipelineRail()
        self.rail.stageClicked.connect(self._open_stage)
        rail_panel.add(self.rail)
        self.root.addWidget(rail_panel)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(16)
        self.recent_panel = Panel("Atividade recente")
        self.recent_panel.header.addWidget(button("Ver histórico", "ghost", None, lambda: self.navigate("history")))
        self.recent_box = QVBoxLayout()
        self.recent_box.setSpacing(0)
        self.recent_panel.body.addLayout(self.recent_box)
        self.recent_panel.body.addStretch(1)
        grid.addWidget(self.recent_panel, 0, 0, 2, 1)

        self.attention_panel = Panel("Precisa de você")
        self.attention_box = QVBoxLayout()
        self.attention_box.setSpacing(8)
        self.attention_panel.body.addLayout(self.attention_box)
        grid.addWidget(self.attention_panel, 0, 1)

        self.market_panel = Panel("Por marketplace")
        self.market_box = QVBoxLayout()
        self.market_box.setSpacing(14)
        self.market_panel.body.addLayout(self.market_box)
        self.market_panel.body.addStretch(1)
        grid.addWidget(self.market_panel, 1, 1)
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        self.root.addLayout(grid, 1)

    # ------------------------------------------------------------------ refresh
    def refresh(self) -> None:
        stats = self.ctx.dashboard.stats()
        now = datetime.now()
        self.header.set_subtitle(f"{plural(stats.total_products, 'produto', 'produtos')} no catálogo. "
                                 f"Atualizado {_DAYS[now.weekday()]} às {now:%H:%M}.")
        by_cat = stats.by_catalog_status
        listing_totals: dict[ListingStatus, int] = {}
        for per_status in stats.by_marketplace.values():
            for status, n in per_status.items():
                listing_totals[status] = listing_totals.get(status, 0) + n
        in_queue = listing_totals.get(ListingStatus.QUEUED, 0) + listing_totals.get(ListingStatus.RUNNING, 0)
        self.rail.set_tracks([
            ("Catálogo", [
                Stage("draft", "Rascunho", by_cat.get(CatalogStatus.DRAFT, 0), T.line_strong),
                Stage("incomplete", "Incompleto", by_cat.get(CatalogStatus.INCOMPLETE, 0), T.warning),
                Stage("ready", "Pronto", by_cat.get(CatalogStatus.READY, 0), "#5B49B8"),
            ]),
            ("Anúncios", [
                Stage("queued", "Na fila", in_queue, T.violet),
                Stage("review", "Aguardando revisão", listing_totals.get(ListingStatus.AWAITING_REVIEW, 0), T.violet_hi),
                Stage("published", "Publicado", listing_totals.get(ListingStatus.PUBLISHED, 0), T.success),
                Stage("failed", "Falha", listing_totals.get(ListingStatus.FAILED, 0), T.danger),
            ]),
        ])
        self._fill_recent(stats.recent)
        self._fill_attention(stats)
        self._fill_marketplaces(stats.by_marketplace)

    def _fill_recent(self, items) -> None:
        clear_layout(self.recent_box)
        if not items:
            self.recent_box.addWidget(label(
                "Nenhuma execução ainda. Cadastre um produto pronto e use Executar para preparar o primeiro anúncio.",
                role="muted", wrap=True))
            return
        for index, item in enumerate(items):
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 10, 0, 10)
            line.setSpacing(12)
            text = QVBoxLayout()
            text.setSpacing(2)
            text.addWidget(label(item.product_name or "(produto excluído)"))
            text.addWidget(label(f"{item.marketplace.label}, {item.account_label}", role="hint"))
            line.addLayout(text, 1)
            line.addWidget(label(format_when(item.finished_at or item.started_at or item.created_at), role="hint"))
            line.addWidget(StatusChip(item.status), 0, Qt.AlignmentFlag.AlignVCenter)
            self.recent_box.addWidget(row)
            if index < len(items) - 1:
                self.recent_box.addWidget(divider())

    def _fill_attention(self, stats) -> None:
        clear_layout(self.attention_box)
        entries = []
        if stats.awaiting_review:
            entries.append(("Revisar anúncios preenchidos", stats.awaiting_review, "warning",
                            lambda: self.navigate("automations")))
        if stats.failures:
            entries.append(("Execuções com falha", stats.failures, "danger",
                            lambda: self.navigate("history", status=ItemStatus.FAILED)))
        incomplete = stats.by_catalog_status.get(CatalogStatus.INCOMPLETE, 0)
        if incomplete:
            entries.append(("Produtos incompletos", incomplete, "warning",
                            lambda: self.navigate("products", status=CatalogStatus.INCOMPLETE)))
        if stats.active_jobs:
            entries.append(("Automações ativas", stats.active_jobs, "violet", lambda: self.navigate("automations")))
        if not entries:
            self.attention_box.addWidget(label("Nada pendente agora.", role="muted"))
            return
        for text, count, tone, action in entries:
            row = QHBoxLayout()
            row.addWidget(StatusChip(text=str(count), tone=tone))
            row.addWidget(label(text), 1)
            row.addWidget(button("Abrir", "ghost", None, action))
            self.attention_box.addLayout(row)

    def _fill_marketplaces(self, by_marketplace) -> None:
        clear_layout(self.market_box)
        for marketplace in (Marketplace.MERCADO_LIVRE, Marketplace.SHOPEE, Marketplace.SIMULATED):
            counts = by_marketplace.get(marketplace, {})
            total = sum(counts.values())
            published = counts.get(ListingStatus.PUBLISHED, 0)
            block = QVBoxLayout()
            block.setSpacing(6)
            head = QHBoxLayout()
            head.addWidget(label(marketplace.label), 1)
            head.addWidget(label(f"{published} de {total} publicados" if total else "sem anúncios", role="hint"))
            block.addLayout(head)
            bar = QProgressBar()
            bar.setMaximum(max(total, 1))
            bar.setValue(published)
            bar.setFixedHeight(6)
            bar.setAccessibleName(f"{marketplace.label}: {published} de {total} publicados")
            block.addWidget(bar)
            failed = counts.get(ListingStatus.FAILED, 0)
            pending = total - published - failed - counts.get(ListingStatus.CANCELLED, 0)
            if total:
                block.addWidget(label(f"{pending} em andamento, {failed} com falha", role="hint"))
            self.market_box.addLayout(block)

    def _open_stage(self, key: str) -> None:
        mapping = {
            "draft": ("products", {"status": CatalogStatus.DRAFT}),
            "incomplete": ("products", {"status": CatalogStatus.INCOMPLETE}),
            "ready": ("products", {"status": CatalogStatus.READY}),
            "queued": ("automations", {}),
            "review": ("automations", {}),
            "published": ("history", {"status": ItemStatus.PUBLISHED}),
            "failed": ("history", {"status": ItemStatus.FAILED}),
        }
        page, kwargs = mapping[key]
        self.navigate(page, **kwargs)
