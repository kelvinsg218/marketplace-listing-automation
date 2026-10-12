"""Contract every marketplace adapter implements.

An adapter only knows how to drive one marketplace's web forms. Ordering,
retries, review, persistence and logging belong to the ExecutionManager.
Adapters must:
  * use explicit waits on robust selectors (ids, labels, roles) — never coordinates;
  * raise ManualActionRequired on login walls, CAPTCHAs or blocks (never bypass them);
  * raise AmbiguousStateError when they cannot tell whether an action took effect.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from mla.core.enums import Marketplace

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from mla.automation.execution_logger import ExecutionLogger


class AutomationError(Exception):
    """Base class for adapter failures."""


class StepError(AutomationError):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class ManualActionRequired(AutomationError):
    """A person must act in the browser (login, CAPTCHA, verification)."""


class AmbiguousStateError(AutomationError):
    """We cannot tell whether the marketplace applied an action (e.g. publish)."""


class NotSupportedYet(AutomationError):
    """The adapter exists but this marketplace's real form is not integrated yet."""


@dataclass
class ListingPayload:
    product_id: int
    sku: str
    title: str
    category: str
    category_id: str
    listing_type: str
    condition: str
    description: str
    price_cents: int
    stock: int
    weight_g: int
    length_mm: int
    width_mm: int
    height_mm: int
    images: list[Path]
    attributes: dict[str, str] = field(default_factory=dict)
    brand: str = ""
    model: str = ""

    @property
    def price_text(self) -> str:
        whole, cents = divmod(self.price_cents, 100)
        return f"{whole},{cents:02d}"


@dataclass
class PublishResult:
    external_id: str
    url: str


# Ordered form-filling steps; the executor calls them in this order.
FORM_STEPS: list[tuple[str, str]] = [
    ("category", "select_category"),
    ("attributes", "fill_attributes"),
    ("title", "fill_title"),
    ("images", "upload_images"),
    ("description", "fill_description"),
    ("price", "fill_price"),
    ("stock", "fill_stock"),
    ("logistics", "fill_logistics"),
]


class BaseMarketplaceAdapter(ABC):
    marketplace: Marketplace
    implemented: bool = True
    home_url: str = ""

    def __init__(self, page: "Page", payload: ListingPayload, log: "ExecutionLogger", timeout_ms: int = 30_000):
        self.page = page
        self.payload = payload
        self.log = log
        self.timeout_ms = timeout_ms

    @classmethod
    def start_url(cls) -> str:
        """Page opened for manual login in the dedicated profile."""
        return cls.home_url

    # -- session
    @abstractmethod
    def ensure_logged_in(self) -> None:
        """Navigate as needed; raise ManualActionRequired if the user must log in."""

    @abstractmethod
    def open_form(self) -> None: ...

    def check_blockers(self) -> None:
        """Raise ManualActionRequired if a CAPTCHA/verification is visible. Default: nothing."""

    # -- form steps
    @abstractmethod
    def select_category(self) -> None: ...

    @abstractmethod
    def fill_attributes(self) -> None: ...

    @abstractmethod
    def fill_title(self) -> None: ...

    @abstractmethod
    def upload_images(self) -> None: ...

    @abstractmethod
    def fill_description(self) -> None: ...

    @abstractmethod
    def fill_price(self) -> None: ...

    @abstractmethod
    def fill_stock(self) -> None: ...

    @abstractmethod
    def fill_logistics(self) -> None: ...

    # -- review and publish
    @abstractmethod
    def read_back(self) -> dict[str, str]:
        """Values currently in the form, for the human review and FormValidator."""

    @abstractmethod
    def publish(self) -> None:
        """Click the marketplace's publish button. Called only after human approval."""

    @abstractmethod
    def confirm_publication(self) -> PublishResult:
        """Wait for proof of publication or raise AmbiguousStateError."""
