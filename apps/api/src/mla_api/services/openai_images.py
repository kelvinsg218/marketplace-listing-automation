"""OpenAI Image API provider for the Estúdio de IA: POST /v1/images/edits with the ORIGINAL product photo.

Sources (checked 2026-11-02): developers.openai.com/api/docs/guides/image-generation (edits endpoint, multipart
fields, quality low|medium|high for gpt-image-2, `input_fidelity` must be omitted for gpt-image-2, b64_json result,
cost measured from the response `usage`) and developers.openai.com/api/docs/pricing (USD per 1M tokens below).
One image per call (no `n`, no batch edits). The key is sent only in the Authorization header from the server.
"""
from __future__ import annotations

import base64
import json
import secrets
import urllib.error
import urllib.request
from typing import Callable

from mla_api.services.image_ai import PRESERVE_PRODUCT, EditResult, ImageEditError

ENDPOINT = "https://api.openai.com/v1/images/edits"
TIMEOUT = 180
# USD per 1M tokens: (text input, image input, image output). Unknown models are refused, never guessed.
PRICES = {
    "gpt-image-2": (5.00, 8.00, 30.00),
    "gpt-image-1.5": (5.00, 8.00, 32.00),
    "gpt-image-1-mini": (2.00, 2.50, 8.00),
}
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

# transport(url, headers, body, timeout) -> (status, response bytes); tests inject a fake, so no real call is made.
Transport = Callable[[str, dict, bytes, int], tuple[int, bytes]]


def _urllib_transport(url: str, headers: dict, body: bytes, timeout: int) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def cost_usd(model: str, usage: dict) -> float | None:
    """Cost of one call from its `usage`; None when the response has no usage (caller keeps the reservation)."""
    if not usage or "output_tokens" not in usage:
        return None
    text_in, image_in, image_out = PRICES[model]
    details = usage.get("input_tokens_details") or {}
    if "image_tokens" in details or "text_tokens" in details:
        tin, iin = int(details.get("text_tokens", 0)), int(details.get("image_tokens", 0))
    else:  # no breakdown: bill every input token at the (higher) image rate
        tin, iin = 0, int(usage.get("input_tokens", 0))
    return (tin * text_in + iin * image_in + int(usage["output_tokens"]) * image_out) / 1_000_000


def _multipart(fields: dict[str, str], file_field: str, filename: str, ctype: str, data: bytes) -> tuple[bytes, str]:
    boundary = "mla" + secrets.token_hex(16)
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n".encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class OpenAIImageProvider:
    name = "openai"
    external = True
    paid = True
    max_prompt = 1000  # the user's part; the preservation instruction is added on top

    def __init__(self, api_key: str, model: str = "gpt-image-2", quality: str = "medium",
                 transport: Transport | None = None):
        if model not in PRICES:
            raise ImageEditError(f"Modelo {model!r} sem preço cadastrado; não é usado (atualize PRICES com a fonte).")
        self._key, self.model, self.quality = api_key, model, quality
        self._transport = transport or _urllib_transport

    def edit(self, image: bytes, content_type: str, prompt: str, *, safety_id: str = "") -> EditResult:
        if content_type not in EXT:
            raise ImageEditError("Formato não aceito pelo provedor (use PNG, JPG ou WEBP).", charged_usd=0.0)
        fields = {"model": self.model, "prompt": PRESERVE_PRODUCT + prompt, "quality": self.quality,
                  "output_format": "png"}
        if safety_id:
            fields["safety_identifier"] = safety_id
        body, ctype = _multipart(fields, "image", f"original.{EXT[content_type]}", content_type, image)
        headers = {"Authorization": f"Bearer {self._key}", "Content-Type": ctype}
        try:
            status, raw = self._transport(ENDPOINT, headers, body, TIMEOUT)
        except (OSError, TimeoutError) as exc:  # network/timeout: the request may have been processed
            raise ImageEditError(f"Sem resposta do provedor ({type(exc).__name__}).", charged_usd=None) from None
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            payload = {}
        if status != 200:
            err = (payload.get("error") or {}) if isinstance(payload, dict) else {}
            message = str(err.get("message") or f"HTTP {status}")[:300]
            # Authentication, permission and rate-limit refusals happen before any generation; others are unknown.
            charged = 0.0 if status in (401, 403, 429) else None
            code = f" [{err['code']}]" if err.get("code") else ""
            raise ImageEditError(f"{message}{code}", charged_usd=charged)
        try:
            data = base64.b64decode(payload["data"][0]["b64_json"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise ImageEditError("Resposta do provedor sem imagem.", charged_usd=None) from None
        usage = payload.get("usage") or {}
        return EditResult(data=data, cost_usd=cost_usd(self.model, usage), usage=usage, model=self.model)
