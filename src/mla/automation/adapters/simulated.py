"""Adapter for the bundled local marketplace (resources/mock_marketplace).

It exercises every part of the pipeline — login wall, CAPTCHA, delayed
category attributes, multi-file upload, publish confirmation — without
touching a real marketplace.
"""
from __future__ import annotations

import unicodedata

from playwright.sync_api import TimeoutError as PlaywrightTimeout

from mla.automation.base import (
    AmbiguousStateError, BaseMarketplaceAdapter, ManualActionRequired, PublishResult, StepError,
)
from mla.config.paths import resource_path
from mla.core.enums import Marketplace


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().strip().lower()


class SimulatedMarketplaceAdapter(BaseMarketplaceAdapter):
    marketplace = Marketplace.SIMULATED
    extra_query = ""  # tests set e.g. "captcha=1" or "slow=1"

    @classmethod
    def base_url(cls) -> str:
        return resource_path("mock_marketplace").as_uri()

    @classmethod
    def start_url(cls) -> str:
        return f"{cls.base_url()}/sell.html"

    def _sell_url(self) -> str:
        return f"{self.base_url()}/sell.html" + (f"?{self.extra_query}" if self.extra_query else "")

    # -------------------------------------------------------------- session
    def ensure_logged_in(self) -> None:
        if "sell.html" not in self.page.url and "login.html" not in self.page.url:
            self.page.goto(self._sell_url())
        self.page.wait_for_load_state("domcontentloaded")
        if "login.html" in self.page.url:
            raise ManualActionRequired("Entre na sua conta no navegador aberto e depois clique em Continuar.")

    def open_form(self) -> None:
        # Idempotent: a retry after a manual action must not reload the page the human just fixed.
        if "sell.html" in self.page.url and self.page.locator("#form-root").is_visible():
            self.check_blockers()
            return
        self.page.goto(self._sell_url())
        if "login.html" in self.page.url:
            raise ManualActionRequired("A sessão expirou. Entre novamente no navegador e clique em Continuar.")
        self.check_blockers()
        self.page.locator("#form-root").wait_for(state="visible", timeout=self.timeout_ms)

    def check_blockers(self) -> None:
        if self.page.locator("#captcha").is_visible():
            raise ManualActionRequired("O marketplace pediu uma verificação. Resolva no navegador e clique em Continuar.")

    # -------------------------------------------------------------- steps
    def select_category(self) -> None:
        select = self.page.locator("#category")
        options = select.locator("option").evaluate_all(
            "els => els.map(e => ({value: e.value, label: e.textContent.trim()}))")
        wanted = self.payload.category_id or self.payload.category
        choice = next((o["value"] for o in options if o["value"] and o["value"] == wanted), None)
        if choice is None:
            choice = next((o["value"] for o in options if o["value"] and _fold(o["label"]) == _fold(wanted)), None)
        if choice is None:
            self.log.warning(f"Categoria '{wanted}' não existe neste marketplace; usando 'Outros'. "
                             "Defina a categoria do marketplace na aba Marketplaces do produto.")
            choice = "outros"
        select.select_option(choice)
        self.page.locator('#attributes[data-ready="1"]').wait_for(state="attached", timeout=self.timeout_ms)

    def fill_attributes(self) -> None:
        known = {_fold(k): v for k, v in self.payload.attributes.items()}
        fields = self.page.locator("#attributes input")
        for index in range(fields.count()):
            field = fields.nth(index)
            name = field.get_attribute("data-label") or ""
            required = field.get_attribute("data-required") == "true"
            value = known.get(_fold(name), "")
            if value:
                field.fill(value)
            elif required:
                raise StepError(f"A categoria exige o atributo '{name}', que não está no cadastro. "
                                "Informe em Produto > Marketplaces > Atributos da categoria.", retryable=False)

    def fill_title(self) -> None:
        self.page.locator("#title").fill(self.payload.title)
        if self.page.locator("#title").input_value() != self.payload.title:
            raise StepError("O campo de título não aceitou o texto completo (limite de caracteres?).",
                            retryable=False)

    def upload_images(self) -> None:
        missing = [p for p in self.payload.images if not p.exists()]
        if missing:
            raise StepError(f"Imagem não encontrada no disco: {missing[0].name}", retryable=False)
        self.page.locator("#images").set_input_files([str(p) for p in self.payload.images])
        expected = len(self.payload.images)
        self.page.wait_for_function(
            f"document.querySelectorAll('#image-list li').length >= {expected}", timeout=self.timeout_ms)

    def fill_description(self) -> None:
        self.page.locator("#description").fill(self.payload.description)

    def fill_price(self) -> None:
        self.page.locator("#price").fill(self.payload.price_text)

    def fill_stock(self) -> None:
        self.page.locator("#stock").fill(str(self.payload.stock))

    def fill_logistics(self) -> None:
        cm = lambda mm: f"{mm // 10},{mm % 10}"  # noqa: E731
        self.page.locator("#weight").fill(str(self.payload.weight_g))
        self.page.locator("#length").fill(cm(self.payload.length_mm))
        self.page.locator("#width").fill(cm(self.payload.width_mm))
        self.page.locator("#height").fill(cm(self.payload.height_mm))
        self.page.locator("#condition").select_option(self.payload.condition)
        if self.payload.listing_type:
            self.page.locator("#listing_type").select_option(label=self.payload.listing_type)

    # -------------------------------------------------------------- review / publish
    def read_back(self) -> dict[str, str]:
        value = lambda selector: self.page.locator(selector).input_value()  # noqa: E731
        return {
            "title": value("#title"),
            "price": value("#price"),
            "stock": value("#stock"),
            "description": value("#description"),
            "images": str(self.page.locator("#image-list li").count()),
            "category": self.page.locator("#category option:checked").inner_text(),
        }

    def publish(self) -> None:
        self.check_blockers()
        self.page.locator("#publish").click()

    def confirm_publication(self) -> PublishResult:
        try:
            self.page.wait_for_url("**/listing.html?id=*", timeout=self.timeout_ms)
            listing_id = self.page.locator("#listing-id")
            listing_id.wait_for(state="visible", timeout=self.timeout_ms)
            external_id = listing_id.inner_text().strip()
        except PlaywrightTimeout as exc:
            errors = self.page.locator("#errors li")
            if "sell.html" in self.page.url and errors.count():
                raise StepError("O marketplace recusou o anúncio: " + "; ".join(errors.all_inner_texts()),
                                retryable=False) from exc
            raise AmbiguousStateError("Não foi possível confirmar a publicação. Confira no marketplace se o "
                                      "anúncio foi criado antes de reexecutar.") from exc
        if not external_id:
            raise AmbiguousStateError("A página de confirmação não mostrou o código do anúncio.")
        return PublishResult(external_id=external_id, url=self.page.url)
