"""Base for marketplaces whose real seller form is not integrated yet.

No selectors are guessed: every step raises NotSupportedYet with an
explanation, and the queue refuses to enqueue these marketplaces while
`implemented` is False. Manual login in the dedicated profile already works.
"""
from __future__ import annotations

from mla.automation.base import BaseMarketplaceAdapter, NotSupportedYet, PublishResult


class PendingIntegrationAdapter(BaseMarketplaceAdapter):
    implemented = False
    pending_message = "Integração ainda não implementada."

    def _pending(self):
        raise NotSupportedYet(self.pending_message)

    def ensure_logged_in(self) -> None:
        self._pending()

    def open_form(self) -> None:
        self._pending()

    def select_category(self) -> None:
        self._pending()

    def fill_attributes(self) -> None:
        self._pending()

    def fill_title(self) -> None:
        self._pending()

    def upload_images(self) -> None:
        self._pending()

    def fill_description(self) -> None:
        self._pending()

    def fill_price(self) -> None:
        self._pending()

    def fill_stock(self) -> None:
        self._pending()

    def fill_logistics(self) -> None:
        self._pending()

    def read_back(self) -> dict[str, str]:
        self._pending()
        return {}

    def publish(self) -> None:
        self._pending()

    def confirm_publication(self) -> PublishResult:
        self._pending()
        raise AssertionError  # unreachable
