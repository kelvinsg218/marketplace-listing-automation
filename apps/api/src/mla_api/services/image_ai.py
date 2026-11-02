"""Estúdio de IA: pluggable image-editing providers.

No provider is configured by default and nothing is simulated: without configuration the API answers that AI editing
depends on setup. A provider receives the image bytes and the prompt and returns new image bytes; the result becomes
a NEW pending version (the original is never changed). Sending images to an external service requires explicit
consent in the request and is audited. Keys come from environment variables, never from the client.
"""
from __future__ import annotations

from typing import Protocol


class ImageEditError(RuntimeError):
    pass


class ImageEditProvider(Protocol):
    name: str
    external: bool          # True = images leave the MLA servers (needs consent)
    max_prompt: int

    def edit(self, image: bytes, content_type: str, prompt: str) -> bytes: ...


def provider_from_settings(settings) -> ImageEditProvider | None:
    """Real providers are added here when credentials and terms are approved (D-033). None exists yet."""
    name = (getattr(settings, "image_ai_provider", "") or "").strip().lower()
    if not name or name == "none":
        return None
    raise ImageEditError(f"Provedor de IA de imagem desconhecido: {name!r}. Nenhum provedor real está integrado ainda.")
