"""Estúdio de IA: pluggable image-editing providers.

No provider is configured by default and nothing is simulated: without configuration the API answers that AI editing
depends on setup. A provider receives the image bytes and the prompt and returns new image bytes plus what the call
cost; the result becomes a NEW pending version (the original is never changed). Sending images to an external service
requires explicit consent in the request and is audited. Keys come from environment variables, never from the client.
Paid providers need two switches (key + MLA_IMAGE_AI_ENABLED) and run under the budget in services/ai_budget.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

# Sent before every user prompt: the studio may improve a photo, never change the product (D-035).
PRESERVE_PRODUCT = ("Edit only the photograph, never the product. Keep the product exactly as it is: shape, "
                    "proportions, colors, materials, logos, printed text, labels, quantity, parts and accessories. "
                    "Do not add, remove or alter product features or text. Allowed changes: background, lighting, "
                    "shadows, framing, cleanliness of the scene. User request: ")


class ImageEditError(RuntimeError):
    def __init__(self, message: str, *, charged_usd: float | None = 0.0):
        super().__init__(message)
        self.charged_usd = charged_usd  # what the failed call cost; None = unknown (the reservation is kept)


@dataclass
class EditResult:
    data: bytes
    cost_usd: float | None = 0.0  # None = the provider did not report usage (the reservation is kept)
    usage: dict = field(default_factory=dict)
    model: str = ""


class ImageEditProvider(Protocol):
    name: str
    external: bool          # True = images leave the MLA servers (needs consent)
    paid: bool              # True = calls are charged to the installation (budget applies)
    max_prompt: int

    def edit(self, image: bytes, content_type: str, prompt: str, *, safety_id: str = "") -> EditResult: ...


@dataclass
class ProviderSetup:
    provider: ImageEditProvider | None
    message: str | None  # why it is unavailable (shown to the user), None when ready


def provider_from_settings(settings) -> ProviderSetup:
    name = (getattr(settings, "image_ai_provider", "") or "").strip().lower()
    if not name or name == "none":
        return ProviderSetup(None, "A edição por IA depende da configuração de um provedor (MLA_IMAGE_AI_PROVIDER). "
                                   "Nenhum provedor está configurado; nada é simulado.")
    if name != "openai":
        raise ImageEditError(f"Provedor de IA de imagem desconhecido: {name!r}. Integrado: 'openai'.")
    if not settings.openai_api_key.get_secret_value().strip():
        return ProviderSetup(None, "Provedor OpenAI selecionado, mas a chave (MLA_OPENAI_API_KEY) não foi configurada "
                                   "no servidor. Nenhuma chamada é feita.")
    if not settings.image_ai_enabled:
        return ProviderSetup(None, "Provedor OpenAI configurado, mas desativado (MLA_IMAGE_AI_ENABLED=false). "
                                   "Nenhuma chamada paga é feita até que o uso seja autorizado.")
    from mla_api.services.openai_images import OpenAIImageProvider
    return ProviderSetup(OpenAIImageProvider(settings.openai_api_key.get_secret_value().strip(),
                                             settings.openai_image_model, settings.openai_image_quality), None)
